# DUSt3R知识蒸馏最终方案

> **版本**: Final v1.0  
> **日期**: 2025-12-31  
> **基于**: DUSt3R完整架构文档（已验证）  
> **状态**: ✅ 可执行

---

## 一、Teacher架构（基准）

| 组件 | 配置 | 参数量 |
|------|------|--------|
| **Encoder** | ViT-Large: 24层, 1024维, 16头 | ~300M |
| **Decoder** | ViT-Base × 2（独立权重）: 12层, 768维, 12头 | ~200M |
| **DPT输出头** | 多尺度特征融合 | ~71M |
| **总计** | | **~571M** |

**关键点**：
- 两个独立的Decoder blocks（`dec_blocks`和`dec_blocks2`，使用`deepcopy`）
- 使用RoPE位置编码（不是可学习位置编码）
- 不使用CLS token
- Decoder有cross-attention机制

---

## 二、Student架构设计（最终决定）

### 2.1 架构原则：**完全对齐Teacher结构**

Student必须与Teacher保持相同的架构结构：
- ✅ 两个独立Decoder blocks（与Teacher对齐）
- ✅ Cross-attention机制（与Teacher对齐）
- ✅ RoPE位置编码（与Teacher对齐）
- ✅ DPT输出头（与Teacher对齐）
- ❌ 不使用CLS token（与Teacher对齐）

### 2.2 Student-S配置（推荐配置，先验证）

| 组件 | Teacher | Student-S | 压缩比 |
|------|---------|-----------|--------|
| **Encoder层数** | 24 | **17** | 71% |
| **Encoder维度** | 1024 | **720** | 70% |
| **Encoder头数** | 16 | **12** | 75% |
| **Decoder层数** | 12×2 | **8×2** | 67% |
| **Decoder维度** | 768 | **540** | 70% |
| **Decoder头数** | 12 | **9** | 75% |
| **FFN比例** | 4.0 | **4.0** | 相同 |
| **预期参数量** | 571M | **~184M** | **68%压缩** |

**验证**：
- Encoder: 720 % 12 = 0 ✓
- Decoder: 540 % 9 = 0 ✓

### 2.3 Student-L配置（备选，如果Student-S精度不够）

| 组件 | Teacher | Student-L |
|------|---------|-----------|
| **Encoder层数** | 24 | **20** |
| **Encoder维度** | 1024 | **832** |
| **Encoder头数** | 16 | **13** |
| **Decoder层数** | 12×2 | **10×2** |
| **Decoder维度** | 768 | **640** |
| **Decoder头数** | 12 | **10** |
| **预期参数量** | 571M | **~240M** |

**验证**：
- Encoder: 832 % 13 = 0 ✓
- Decoder: 640 % 10 = 0 ✓

---

## 三、蒸馏损失函数（最终决定）

### 3.1 核心原则

**❌ 不使用KL散度**（3D点云不是概率分布）  
**✅ 使用L2距离（欧几里得距离）**（与DUSt3R的Regr3D损失一致）

### 3.2 损失函数公式

```python
L_total = α · L_task + β · L_distill + γ · L_conf
```

### 3.3 各组件实现

#### 3.3.1 任务损失 (L_task)

```python
# 使用Teacher输出作为"软标签"
L_task = Regr3D_Loss(
    student_pts3d,
    teacher_pts3d.detach(),
    norm_mode='avg_dis'
)
```

#### 3.3.2 蒸馏损失 (L_distill) - **核心**

```python
def Regr3D_Loss(pred_pts, target_pts, norm_mode='avg_dis'):
    """
    与DUSt3R的Regr3D损失完全一致
    """
    # 1. 归一化点云（按平均距离，对齐到view1坐标系）
    pred_norm = normalize_pointcloud(pred_pts, norm_mode)
    target_norm = normalize_pointcloud(target_pts, norm_mode)
    
    # 2. 计算欧几里得距离（L2范数）
    # pred_pts: (B, H, W, 3), target_pts: (B, H, W, 3)
    loss = torch.norm(pred_norm - target_norm, dim=-1)  # (B, H, W)
    loss = loss.mean()  # 平均所有像素
    
    return loss

L_distill = Regr3D_Loss(
    student_pts3d,
    teacher_pts3d.detach(),
    norm_mode='avg_dis'
)
```

**关键点**：
- ✅ 使用欧几里得距离（不是KL散度）
- ✅ 需要归一化（norm_mode='avg_dis'）
- ✅ Teacher输出使用`.detach()`防止梯度泄露

#### 3.3.3 置信度对齐损失 (L_conf) - 可选

```python
if 'conf' in student_output and 'conf' in teacher_output:
    L_conf = F.mse_loss(student_conf, teacher_conf.detach())
else:
    L_conf = 0.0
```

### 3.4 损失权重设置

| 阶段 | α (L_task) | β (L_distill) | γ (L_conf) |
|------|------------|---------------|------------|
| **前期 (0-70% epochs)** | 1.0 | 0.5 | 0.0 |
| **后期 (70-100% epochs)** | 0.8 | 1.0 | 0.1 |

**课程式蒸馏策略**：
- 前期：主要学习基本3D重建能力（L_task为主）
- 后期：强化对齐Teacher的精确输出（L_distill为主）

---

## 四、完整训练流程

### 4.1 数据准备

**必须使用完整7-Scenes数据集**（7个场景，不是只有heads）

```bash
python scripts/prepare_7scenes.py \
    --output datasets/7scenes \
    --scenes heads chess fire office pumpkin redkitchen stairs
```

### 4.2 Teacher模型加载

```python
from dust3r.model import AsymmetricCroCo3DStereo

teacher = AsymmetricCroCo3DStereo.from_pretrained(
    'naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt'
)
teacher.eval()  # 必须设置为eval模式
for param in teacher.parameters():
    param.requires_grad = False  # 冻结所有参数
```

### 4.3 Student模型创建（需要重新实现）

**⚠️ 注意**：当前`scripts/models/__init__.py`的实现不符合要求，需要重新实现！

**应该实现的Student模型结构**：

```python
class DUSt3RStudent(nn.Module):
    """
    Student模型 - 与Teacher结构完全对齐
    """
    def __init__(self, config: StudentConfig):
        super().__init__()
        self.config = config
        
        # 1. Patch Embedding（无CLS token）
        self.patch_embed = PatchEmbedDust3R(
            img_size=config.img_size,
            patch_size=16,
            embed_dim=config.encoder_dim
        )
        
        # 2. Encoder（使用RoPE，无CLS token，无可学习位置编码）
        self.encoder = StudentEncoder(
            layers=config.encoder_layers,
            dim=config.encoder_dim,
            heads=config.encoder_heads,
            pos_embed='RoPE100'  # 与Teacher对齐
        )
        
        # 3. Decoder投影
        self.decoder_embed = nn.Linear(
            config.encoder_dim, 
            config.decoder_dim
        )
        
        # 4. 两个独立Decoder（使用deepcopy）
        self.dec_blocks = nn.ModuleList([
            DecoderBlock(
                dim=config.decoder_dim,
                num_heads=config.decoder_heads,
                cross_attention=True  # 必须有cross-attention
            )
            for _ in range(config.decoder_layers)
        ])
        self.dec_blocks2 = deepcopy(self.dec_blocks)  # 第二个Decoder
        self.dec_norm = nn.LayerNorm(config.decoder_dim)
        
        # 5. DPT输出头（两个独立头）
        self.dpt_head1 = DPTOutputAdapter(...)  # 适配Student维度
        self.dpt_head2 = DPTOutputAdapter(...)
        
    def forward(self, view1, view2):
        """
        前向传播 - 与Teacher完全对齐
        """
        # 1. 编码两张图像（共享Encoder）
        enc_feat1, enc_pos1 = self.encoder(view1['img'])
        enc_feat2, enc_pos2 = self.encoder(view2['img'])
        
        # 2. Decoder投影
        dec_feat1 = self.decoder_embed(enc_feat1)
        dec_feat2 = self.decoder_embed(enc_feat2)
        
        # 3. Decoder处理（两个独立Decoder，通过cross-attention交换信息）
        dec_out1 = dec_feat1
        dec_out2 = dec_feat2
        
        for blk1, blk2 in zip(self.dec_blocks, self.dec_blocks2):
            # Decoder1: view1的特征，cross-attention到view2
            dec_out1, _ = blk1(dec_out1, dec_out2, enc_pos1, enc_pos2)
            # Decoder2: view2的特征，cross-attention到view1
            dec_out2, _ = blk2(dec_out2, dec_out1, enc_pos2, enc_pos1)
        
        dec_out1 = self.dec_norm(dec_out1)
        dec_out2 = self.dec_norm(dec_out2)
        
        # 4. DPT输出头
        output1 = self.dpt_head1(dec_out1, enc_feat1, ...)
        output2 = self.dpt_head2(dec_out2, enc_feat2, ...)
        
        return output1, output2
```

### 4.4 训练循环

```python
for epoch in range(max_epochs):
    # 1. 更新课程式蒸馏权重
    progress = epoch / max_epochs
    if progress > 0.7:
        # 后期：增加蒸馏权重
        beta = 0.5 + (progress - 0.7) / 0.3 * 0.5  # 0.5 → 1.0
        alpha = 1.0 - (progress - 0.7) / 0.3 * 0.2  # 1.0 → 0.8
        criterion.update_weights(alpha=alpha, beta=beta)
    
    for batch in train_loader:
        img1, img2 = batch['img1'], batch['img2']
        
        # 2. Teacher前向（无梯度）
        with torch.no_grad():
            teacher_out1, teacher_out2 = teacher(
                {'img': img1}, 
                {'img': img2}
            )
            teacher_pts3d = teacher_out1['pts3d']  # (B, H, W, 3)
            teacher_conf = teacher_out1.get('conf')  # (B, H, W, 1)
        
        # 3. Student前向（有梯度）
        student_out1, student_out2 = student(
            {'img': img1},
            {'img': img2}
        )
        student_pts3d = student_out1['pts3d']
        student_conf = student_out1.get('conf')
        
        # 4. 计算损失
        losses = criterion(
            student_output={
                'pts3d': student_pts3d,
                'conf': student_conf
            },
            teacher_output={
                'pts3d': teacher_pts3d,
                'conf': teacher_conf
            }
        )
        
        # 5. 反向传播（只更新Student）
        optimizer.zero_grad()
        losses['total'].backward()
        torch.nn.utils.clip_grad_norm_(student.parameters(), max_norm=1.0)
        optimizer.step()
```

---

## 五、超参数配置（最终决定）

```yaml
# expconfigs/distill.yaml

experiment:
  name: "K-only_distill_final"
  
  # Student架构 - Student-S配置
  student:
    config:
      encoder_layers: 17
      encoder_heads: 12
      encoder_dim: 720
      encoder_ffn_ratio: 4.0
      decoder_layers: 8
      decoder_heads: 9
      decoder_dim: 540
      decoder_ffn_ratio: 4.0
      patch_size: 16
      img_size: [512, 384]
  
  # Teacher模型
  teacher:
    weights: null  # 从HuggingFace加载
    eval_fp16: true
  
  # 蒸馏损失
  distill:
    alpha_task_init: 1.0      # 前期L_task权重
    alpha_task_final: 0.8     # 后期L_task权重
    beta_distill_init: 0.5    # 前期L_distill权重
    beta_distill_final: 1.0   # 后期L_distill权重
    gamma_conf_init: 0.0      # 前期L_conf权重
    gamma_conf_final: 0.1     # 后期L_conf权重
    curriculum_pct: 0.7       # 70%处切换权重
  
  # 优化器
  optim:
    optimizer: "AdamW"
    lr: 2e-4
    weight_decay: 0.01
    betas: [0.9, 0.999]
    sched: "cosine"
    warmup_epochs: 5
    min_lr: 1e-6
  
  # 训练
  run:
    max_epochs: 30
    batch_size: 4  # 根据GPU显存调整
    accum_iter: 2  # 梯度累积
    early_stop_patience: 10
    grad_clip: 1.0
  
  # 数据
  data:
    train_pairs: "datasets/train_pairs.lst"  # 完整7-Scenes数据集
    val_pairs: "datasets/val_pairs.lst"
    img_size: [512, 384]
```

---

## 六、验证清单

### 6.1 架构验证

- [ ] Student Encoder层数 < Teacher (17 < 24)
- [ ] Student Encoder维度 < Teacher (720 < 1024)
- [ ] Student Decoder层数 < Teacher (8 < 12)
- [ ] Student Decoder维度 < Teacher (540 < 768)
- [ ] 所有维度能被头数整除
- [ ] Student有两个独立Decoder（与Teacher对齐）
- [ ] Student使用RoPE位置编码（与Teacher对齐）
- [ ] Student不使用CLS token（与Teacher对齐）
- [ ] Student有Cross-attention机制（与Teacher对齐）
- [ ] Student使用DPT输出头（与Teacher对齐）

### 6.2 损失函数验证

- [ ] ❌ 不使用KL散度
- [ ] ✅ 使用L2距离（欧几里得距离）
- [ ] ✅ 损失计算包括归一化步骤（norm_mode='avg_dis'）
- [ ] ✅ Teacher输出使用`.detach()`

### 6.3 训练流程验证

- [ ] Teacher设置为`eval()`模式
- [ ] Teacher所有参数`requires_grad=False`
- [ ] Student输出格式与Teacher一致（pts3d + conf）
- [ ] 验证集使用完整7-Scenes数据集（7个场景）

---

## 七、预期结果

### 7.1 参数量

| 模型 | 参数量 | 压缩率 |
|------|--------|--------|
| Teacher | 571M | - |
| Student-S | ~184M | 68% |
| Student-L（备选） | ~240M | 58% |

### 7.2 性能目标

| 指标 | 目标 |
|------|------|
| **精度损失** | ≤ 1% (相对于Teacher) |
| **推理速度** | 提升3-5倍 |
| **显存占用** | 减少60-70% |

---

## 八、实施步骤

### Phase 1: 修正损失函数（立即）

1. 修改`scripts/train_distill.py`中的`DistillationLoss`类
2. 删除KL散度相关代码
3. 实现`Regr3D_Loss`函数（使用L2距离）

### Phase 2: 重新实现Student模型（立即）

1. 重新实现`DUSt3RStudent`类
2. 确保有两个独立Decoder
3. 实现Cross-attention机制
4. 集成RoPE位置编码
5. 实现DPT输出头（或至少使用适配Student维度的输出头）

### Phase 3: 数据准备（立即）

1. 准备完整7-Scenes数据集（7个场景）
2. 生成训练/验证pairs列表

### Phase 4: 训练验证（后续）

1. 使用Student-S配置（184M）训练
2. 验证精度损失是否 ≤ 1%
3. 如果精度不够，切换到Student-L配置（240M）

---

## 九、关键代码修正点

### 9.1 损失函数修正（scripts/train_distill.py）

**删除**：
```python
# ❌ 删除这部分
s_log_prob = F.log_softmax(s_flat / self.temperature, dim=-1)
t_prob = F.softmax(t_flat / self.temperature, dim=-1)
losses['kd'] = F.kl_div(s_log_prob, t_prob.detach(), ...)
```

**替换为**：
```python
# ✅ 使用L2距离
losses['distill'] = Regr3D_Loss(
    student_pts3d,
    teacher_pts3d.detach(),
    norm_mode='avg_dis'
)
```

### 9.2 Student架构修正（scripts/models/__init__.py）

**需要完全重写**，确保：
1. 两个独立Decoder blocks
2. Cross-attention机制
3. RoPE位置编码
4. 不使用CLS token
5. DPT输出头

---

## 十、总结

**最终方案**：

1. **损失函数**：使用L2距离（欧几里得距离），与DUSt3R的Regr3D一致
2. **Student架构**：完全对齐Teacher（两个独立Decoder、Cross-attention、RoPE、DPT）
3. **参数量配置**：Student-S（184M，68%压缩），不够再用Student-L（240M）
4. **课程式蒸馏**：前70%以任务损失为主，后30%以蒸馏损失为主

**这是最终确定的、可执行的方案！**

