# DUSt3R知识蒸馏完整规划方案

> **基于**: DUSt3R完整架构文档  
> **创建日期**: 2025-12-31  
> **目标**: 从DUSt3R Teacher模型蒸馏到轻量化Student模型

---

## 一、Teacher架构（基准）

### 1.1 完整配置

| 组件 | 配置 | 数值 |
|------|------|------|
| **Encoder** | ViT-Large | 24层, 1024维, 16头, FFN=4096 |
| **Decoder** | ViT-Base | 12层, 768维, 12头, FFN=3072 |
| **Decoder数量** | 两个独立Decoder | dec_blocks + dec_blocks2 (deepcopy) |
| **输出头** | DPT | 多尺度特征融合 |
| **位置编码** | RoPE | 继承自CroCo预训练 |
| **参数量** | 总计 | ~571M |

### 1.2 输出格式

```python
teacher_output = {
    'pts3d': torch.Tensor,        # Shape: (B, H, W, 3) - 3D点云
    'conf': torch.Tensor,         # Shape: (B, H, W, 1) - 置信度
    'pts3d_in_other_view': ...,   # 第二个view的点云
    'conf_in_other_view': ...,    # 第二个view的置信度
}
```

### 1.3 训练损失函数（Teacher使用）

```python
# DUSt3R原始训练损失
ConfLoss(
    Regr3D(L21, norm_mode='avg_dis'),
    alpha=0.2
)

# 其中：
# - Regr3D: 3D点云的欧几里得距离损失（L2范数）
# - L21: torch.norm(a - b, dim=-1) - 欧几里得距离
# - ConfLoss: 置信度加权损失
```

---

## 二、Student架构设计

### 2.1 设计原则

1. **比例缩减**: 按比例缩减Teacher的层数、维度、头数
2. **保持整除**: 确保 `dim % num_heads == 0`
3. **结构对齐**: 保持与Teacher相同的架构结构（Encoder+Decoder+DPT）
4. **参数量目标**: 目标压缩至46M左右（约92%压缩率）

### 2.1.1 Student架构必须与Teacher对齐

**关键要求**：
- ✅ **必须有Encoder + Decoder + DPT输出头**（与Teacher相同）
- ✅ **必须有两个独立的Decoder**（dec_blocks和dec_blocks2，与Teacher对齐）
- ✅ **Decoder必须有cross-attention机制**（与Teacher对齐）
- ✅ **必须使用RoPE位置编码**（与Teacher对齐）
- ✅ **不使用CLS token**（Teacher不使用CLS token）
- ✅ **输出格式必须一致**：pts3d (B, H, W, 3) + conf (B, H, W, 1)

**⚠️ 当前代码的问题**：

| 组件 | Teacher (正确) | 当前Student代码 (错误) | 应该有的Student |
|------|----------------|----------------------|----------------|
| **Encoder数量** | 1个（共享） | ✅ 1个 | ✅ 1个（共享） |
| **Decoder数量** | 2个独立（dec_blocks + dec_blocks2） | ❌ 1个 | ✅ 2个独立 |
| **CLS token** | ❌ 不使用 | ❌ 使用了 | ✅ 不使用 |
| **位置编码** | RoPE（在每个Block内） | ❌ 可学习位置编码 | ✅ RoPE |
| **Cross-Attention** | ✅ 有（DecoderBlock中） | ❌ 没有 | ✅ 必须有 |
| **输出头** | DPT（多尺度融合） | ❌ Linear头 | ✅ DPT |
| **输出格式** | pts3d (B,H,W,3) + conf (B,H,W,1) | ✅ 相似 | ✅ 必须一致 |
| **前向流程** | 两个view分别处理，cross-attention | ❌ 简单相加 | ✅ 与Teacher对齐 |

**因此，Student架构需要完全重新设计，以匹配Teacher的结构！**

**修正要求**：
1. 删除CLS token相关代码
2. 实现两个独立的Decoder blocks（使用deepcopy）
3. 在DecoderBlock中添加cross-attention机制
4. 实现DPT输出头（或至少使用适配Student维度的DPT）
5. 使用RoPE位置编码（继承自CroCo或重新实现）

### 2.2 推荐Student配置（基于30%缩减）

#### Student-S (Small, -30%)

| 组件 | Teacher | Student-S | 缩减率 |
|------|---------|-----------|--------|
| **Encoder** | 24层, 1024维, 16头 | **17层, 720维, 12头** | -29% / -30% / -25% |
| **Decoder** | 12层, 768维, 12头 | **8层, 540维, 9头** | -33% / -30% / -25% |
| **FFN比例** | 4.0 | 4.0 | 保持一致 |
| **Decoder数量** | 2个独立 | 2个独立 | 保持一致 |
| **输出头** | DPT | DPT | 保持一致 |

**计算验证**:
- Encoder: 720 % 12 = 0 ✓
- Decoder: 540 % 9 = 0 ✓
- 预期参数量: ~46M

#### Student-M (Medium, -20%)

| 组件 | Teacher | Student-M | 缩减率 |
|------|---------|-----------|--------|
| **Encoder** | 24层, 1024维, 16头 | **19层, 816维, 13头** | -21% / -20% / -19% |
| **Decoder** | 12层, 768维, 12头 | **10层, 624维, 10头** | -17% / -19% / -17% |

**计算验证**:
- Encoder: 816 % 13 = 10.77... ✗ → 调整为 **819维, 13头** (819 % 13 = 0) ✓
- Decoder: 624 % 10 = 62.4... ✗ → 调整为 **620维, 10头** (620 % 10 = 0) ✓

#### Student-L (Large, -10%)

| 组件 | Teacher | Student-L | 缩减率 |
|------|---------|-----------|--------|
| **Encoder** | 24层, 1024维, 16头 | **22层, 928维, 15头** | -8% / -9% / -6% |
| **Decoder** | 12层, 768维, 12头 | **11层, 696维, 11头** | -8% / -9% / -8% |

**计算验证**:
- Encoder: 928 % 15 = 13.87... ✗ → 调整为 **930维, 15头** (930 % 15 = 0) ✓
- Decoder: 696 % 11 = 63.27... ✗ → 调整为 **693维, 11头** (693 % 11 = 0) ✓

### 2.3 Student完整架构结构

#### 2.3.1 整体架构图

```
DUSt3RStudent (与Teacher结构完全对齐)
│
├── [1] Patch Embedding
│   └── PatchEmbed(img_size, patch_size=16, embed_dim=encoder_dim)
│       └── 输出: (B, N, encoder_dim) - N = (H/P) × (W/P)
│
├── [2] Encoder (ViT架构，缩减版)
│   ├── RoPE位置编码（在每个Block内应用，不使用可学习位置编码）
│   ├── encoder_layers × TransformerBlock
│   │   ├── LayerNorm
│   │   ├── MultiHeadAttention (self-attention)
│   │   ├── LayerNorm
│   │   └── FFN (mlp_ratio=4)
│   └── LayerNorm (最终)
│       └── 输出: (B, N, encoder_dim)
│
├── [3] Decoder投影层
│   └── Linear(encoder_dim → decoder_dim)
│       └── 输出: (B, N, decoder_dim)
│
├── [4] Decoder (两个独立Decoder，与Teacher对齐)
│   │
│   ├── Decoder1 (dec_blocks) - 处理view1
│   │   └── decoder_layers × DecoderBlock
│   │       ├── LayerNorm + Self-Attention (view1内部)
│   │       ├── LayerNorm + Cross-Attention (view1 → view2)
│   │       └── LayerNorm + FFN
│   │           └── 输出1: (B, N, decoder_dim)
│   │
│   └── Decoder2 (dec_blocks2) - 处理view2
│       └── decoder_layers × DecoderBlock
│           ├── LayerNorm + Self-Attention (view2内部)
│           ├── LayerNorm + Cross-Attention (view2 → view1)
│           └── LayerNorm + FFN
│               └── 输出2: (B, N, decoder_dim)
│
└── [5] DPT输出头 (两个独立头)
    │
    ├── DPT Head 1 (downstream_head1)
    │   ├── 从Encoder的多个层提取特征（hooks）
    │   ├── RefineNet融合多尺度特征
    │   └── 输出1: pts3d1 (B, H, W, 3) + conf1 (B, H, W, 1)
    │
    └── DPT Head 2 (downstream_head2)
        ├── 从Encoder的多个层提取特征（hooks）
        ├── RefineNet融合多尺度特征
        └── 输出2: pts3d2 (B, H, W, 3) + conf2 (B, H, W, 1)
```

#### 2.3.2 详细组件说明

**1. Patch Embedding**
```python
class PatchEmbed:
    - patch_size: 16 (与Teacher相同)
    - embed_dim: encoder_dim (根据Student配置)
    - 输出: (B, N, encoder_dim) - N = (H/16) × (W/16)
```

**2. Encoder (ViT-Like)**
```python
class StudentEncoder:
    - layers: encoder_layers (如17层，相比Teacher的24层)
    - dim: encoder_dim (如720，相比Teacher的1024)
    - heads: encoder_heads (如12，相比Teacher的16)
    - FFN: encoder_dim * 4 (mlp_ratio=4，与Teacher相同)
    - 位置编码: RoPE（与Teacher相同，不使用CLS token）
    - 输出: (B, N, encoder_dim)
```

**3. Decoder投影**
```python
decoder_embed = Linear(encoder_dim → decoder_dim)
# 例如: Linear(720 → 540)
```

**4. Decoder Block（关键：必须有cross-attention）**
```python
class DecoderBlock:
    def forward(self, x, y, xpos, ypos):
        # x: 当前view的特征
        # y: 另一个view的特征（用于cross-attention）
        
        # 1. Self-attention (x内部)
        x = x + self.self_attn(self.norm1(x), xpos)
        
        # 2. Cross-attention (x ← y)
        x = x + self.cross_attn(self.norm2(x), y, ypos)
        
        # 3. FFN
        x = x + self.ffn(self.norm3(x))
        
        return x, y
```

**5. DPT输出头**
```python
class DPTOutputAdapter:
    - 从Encoder的多个层提取特征（如layers [2, 5, 8, 11]）
    - 使用RefineNet融合多尺度特征
    - 输出: pts3d (B, H, W, 3) + conf (B, H, W, 1)
```

#### 2.3.3 前向传播流程

```python
def forward(self, view1, view2):
    # view1 = {'img': img1}, view2 = {'img': img2}
    
    # 1. 编码两张图像（共享Encoder）
    enc_feat1, enc_pos1 = self.encoder(view1['img'])  # (B, N, encoder_dim)
    enc_feat2, enc_pos2 = self.encoder(view2['img'])
    
    # 2. Decoder投影
    dec_feat1 = self.decoder_embed(enc_feat1)  # (B, N, decoder_dim)
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
    output1 = self.dpt_head1(dec_out1, enc_feat1, ...)  # pts3d1 + conf1
    output2 = self.dpt_head2(dec_out2, enc_feat2, ...)  # pts3d2 + conf2
    
    return output1, output2  # 每个包含 {'pts3d': ..., 'conf': ...}
```

### 2.4 Student架构关键点总结

1. **必须保持两个独立Decoder**: 与Teacher架构对齐（使用deepcopy创建dec_blocks2）
2. **必须有Cross-Attention**: DecoderBlock中必须有cross-attention机制
3. **DPT输出头**: 需要适配Student的Encoder维度（hooks层数可能需要调整）
4. **RoPE位置编码**: 继承相同的RoPE配置（不使用可学习位置编码）
5. **不使用CLS token**: 与Teacher对齐
6. **输出格式对齐**: pts3d (B, H, W, 3) + conf (B, H, W, 1)

---

## 三、蒸馏损失函数设计

### 3.1 核心原则

**DUSt3R是回归任务（3D点云），不是分类任务**，因此：
- ❌ **不应该使用KL散度**（KL散度适用于概率分布）
- ✅ **应该使用回归损失**（MSE/L1/欧几里得距离）

### 3.2 推荐损失函数组合

```python
L_total = α · L_task + β · L_distill + γ · L_conf

其中：
- L_task: Student输出 vs GT（可选，如果有GT）
- L_distill: Student输出 vs Teacher输出（核心蒸馏损失）
- L_conf: 置信度对齐损失
```

#### 3.2.1 任务损失 (L_task)

```python
# 方案1: 如果有GT，使用GT
if gt is not None:
    L_task = L21(student_pts3d, gt_pts3d)
else:
    # 方案2: 没有GT时，使用Teacher输出作为"软标签"
    L_task = L21(student_pts3d, teacher_pts3d.detach())
```

#### 3.2.2 蒸馏损失 (L_distill) - **核心**

```python
# 使用DUSt3R的Regr3D损失（欧几里得距离）
L_distill = Regr3D_Loss(
    student_pts3d, 
    teacher_pts3d.detach(),
    norm_mode='avg_dis'  # 归一化到view1坐标系
)

# 实现：
def Regr3D_Loss(pred_pts, gt_pts, norm_mode='avg_dis'):
    # 1. 归一化点云（按平均距离）
    pred_norm = normalize_pointcloud(pred_pts, norm_mode)
    gt_norm = normalize_pointcloud(gt_pts, norm_mode)
    
    # 2. 计算欧几里得距离（L2范数）
    loss = torch.norm(pred_norm - gt_norm, dim=-1).mean()
    return loss
```

#### 3.2.3 置信度对齐损失 (L_conf) - **可选**

```python
# 如果Student也输出置信度，对齐Teacher的置信度
if 'conf' in student_output and 'conf' in teacher_output:
    L_conf = F.mse_loss(student_conf, teacher_conf.detach())
else:
    L_conf = 0
```

### 3.3 损失权重建议

| 阶段 | α (L_task) | β (L_distill) | γ (L_conf) |
|------|------------|---------------|------------|
| **前期 (0-70% epochs)** | 1.0 | 0.5 | 0.0 |
| **后期 (70-100% epochs)** | 0.8 | 1.0 | 0.1 |

**课程式蒸馏策略**:
- 前期：主要学习基本3D重建能力
- 后期：强化对齐Teacher的精确输出

---

## 四、蒸馏训练流程

### 4.1 数据准备

#### 4.1.1 数据集要求

- **完整7-Scenes数据集**（7个场景，不是只有heads）
- **训练/验证/测试划分**
- **图像对格式**: 每对包含两张图像和对应的GT pointmaps（如果有）

#### 4.1.2 数据预处理

```python
# 与Teacher训练时相同
- 输入分辨率: 512×384 (或其他Teacher支持的分辨率)
- 数据增强: ColorJitter + RandomCenterCrop
- Normalize: ImageNet均值和标准差
```

### 4.2 Teacher模型加载

```python
from dust3r.model import AsymmetricCroCo3DStereo

teacher = AsymmetricCroCo3DStereo.from_pretrained(
    'naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt'
)
teacher.eval()  # 重要：设置为eval模式
for param in teacher.parameters():
    param.requires_grad = False  # 冻结所有参数
```

### 4.3 Student模型创建

```python
from scripts.models import DUSt3RStudent, StudentConfig

# 使用Student-S配置
config = StudentConfig(
    encoder_layers=17,
    encoder_heads=12,
    encoder_dim=720,
    decoder_layers=8,
    decoder_heads=9,
    decoder_dim=540,
    patch_size=16,
    img_size=(512, 384),
)

student = DUSt3RStudent(config=config)
```

### 4.4 训练循环（每个epoch）

```python
for epoch in range(max_epochs):
    # 1. 更新课程式蒸馏权重
    if epoch / max_epochs > 0.7:
        # 后期：增加蒸馏权重
        beta = 0.5 + (epoch / max_epochs - 0.7) / 0.3 * 0.5  # 0.5 → 1.0
        criterion.update_beta(beta)
    
    for batch in train_loader:
        img1, img2, gt = batch
        
        # 2. Teacher前向（无梯度）
        with torch.no_grad():
            teacher_out1, teacher_out2 = teacher({'img': img1}, {'img': img2})
            teacher_pts3d = teacher_out1['pts3d']  # (B, H, W, 3)
            teacher_conf = teacher_out1.get('conf')  # (B, H, W, 1)
        
        # 3. Student前向（有梯度）
        student_out1, student_out2 = student(img1, img2)
        student_pts3d = student_out1['pts3d']
        student_conf = student_out1.get('conf')
        
        # 4. 计算损失
        losses = criterion(
            student_output={'pts3d': student_pts3d, 'conf': student_conf},
            teacher_output={'pts3d': teacher_pts3d, 'conf': teacher_conf},
            gt=gt  # 如果有GT
        )
        
        # 5. 反向传播（只更新Student）
        optimizer.zero_grad()
        losses['total'].backward()
        torch.nn.utils.clip_grad_norm_(student.parameters(), max_norm=1.0)
        optimizer.step()
```

### 4.5 验证流程

```python
@torch.no_grad()
def validate(student, val_loader, teacher):
    student.eval()
    total_loss = 0
    
    for batch in val_loader:
        img1, img2, gt = batch
        
        # Student预测
        student_out1, _ = student(img1, img2)
        student_pts3d = student_out1['pts3d']
        
        # Teacher预测（作为参考）
        teacher_out1, _ = teacher({'img': img1}, {'img': img2})
        teacher_pts3d = teacher_out1['pts3d']
        
        # 计算验证损失（Student vs Teacher，或vs GT）
        if gt is not None:
            val_loss = L21(student_pts3d, gt['pts3d'])
        else:
            val_loss = L21(student_pts3d, teacher_pts3d)
        
        total_loss += val_loss.item()
    
    return total_loss / len(val_loader)
```

---

## 五、关键问题修正

### 5.1 ❌ 当前代码的问题

#### 问题1: KL散度用于3D点云 - **必须修正**

**当前代码** (scripts/train_distill.py:177-185):
```python
# ❌ 错误：对3D点云使用softmax和KL散度
s_log_prob = F.log_softmax(s_flat / self.temperature, dim=-1)
t_prob = F.softmax(t_flat / self.temperature, dim=-1)
losses['kd'] = F.kl_div(s_log_prob, t_prob.detach(), ...)
```

**为什么错误**：
1. 3D点云是连续值，不是概率分布
2. 在58万维上做softmax数值不稳定
3. KL散度无法反映几何误差

**修正方案**（最终决定）:
```python
# ✅ 正确：使用欧几里得距离（与DUSt3R的Regr3D损失一致）
def Regr3D_Loss(pred_pts, target_pts, norm_mode='avg_dis'):
    # 归一化点云
    pred_norm = normalize_pointcloud(pred_pts, norm_mode)
    target_norm = normalize_pointcloud(target_pts, norm_mode)
    # 计算L2距离
    loss = torch.norm(pred_norm - target_norm, dim=-1).mean()
    return loss

losses['distill'] = Regr3D_Loss(
    student_pts3d,
    teacher_pts3d.detach(),
    norm_mode='avg_dis'
)
```

#### 问题2: Student架构配置错误

**当前代码** (scripts/models/__init__.py:21-23):
```python
# ❌ 错误：注释写的是"原版 12"，但Teacher实际是24层
encoder_layers: int = 10           # 原版 12  ← 错误！
encoder_dim: int = 640             # 原版 768 ← 错误！（Teacher是1024）
```

**修正**: 基于正确的Teacher配置（24层, 1024维）重新设计

#### 问题3: 损失函数不匹配

**当前**: 使用通用蒸馏损失（MSE + KL + Feature）
**应该**: 使用DUSt3R的Regr3D损失（欧几里得距离 + 归一化）

### 5.2 ✅ 修正方案

1. **重新设计Student架构**: 基于正确的Teacher配置（24/1024/16 → 17/720/12等）
2. **重写蒸馏损失**: 使用Regr3D风格的欧几里得距离损失
3. **对齐输出格式**: 确保Student和Teacher的输出格式一致（pts3d + conf）

---

## 六、完整训练配置

### 6.1 超参数设置

```yaml
# expconfigs/distill.yaml (修正版)

experiment:
  name: "K-only_distill_v3"
  
  # Student架构
  student:
    scale: "s"  # 's', 'm', 'l'
    config:
      encoder_layers: 17
      encoder_heads: 12
      encoder_dim: 720
      decoder_layers: 8
      decoder_heads: 9
      decoder_dim: 540
  
  # Teacher模型
  teacher:
    weights: null  # 从HuggingFace加载
    eval_fp16: true
  
  # 蒸馏损失
  distill:
    alpha_task: 1.0      # L_task权重
    beta_distill: 0.5    # L_distill权重（前期）
    beta_distill_final: 1.0  # L_distill权重（后期）
    gamma_conf: 0.0      # L_conf权重（前期）
    gamma_conf_final: 0.1    # L_conf权重（后期）
    curriculum_pct: 0.7  # 70%处切换权重
  
  # 优化器
  optim:
    lr: 2e-4
    weight_decay: 0.01
    sched: "cosine"
    warmup_epochs: 5
  
  # 训练
  run:
    max_epochs: 30
    batch_size: 8
    early_stop_patience: 10
    grad_clip: 1.0
  
  # 数据
  data:
    train_pairs: "datasets/train_pairs.lst"  # 7个场景的完整数据
    val_pairs: "datasets/val_pairs.lst"
    img_size: [512, 384]
```

### 6.2 训练命令

```bash
python scripts/train_distill.py \
    --config expconfigs/distill.yaml \
    --dry-run  # 先验证，再实际训练
```

---

## 七、验证清单

### 7.1 架构验证

- [ ] Student Encoder层数 < Teacher Encoder层数（24层）
- [ ] Student Encoder维度 < Teacher Encoder维度（1024维）
- [ ] Student Decoder层数 < Teacher Decoder层数（12层）
- [ ] Student Decoder维度 < Teacher Decoder维度（768维）
- [ ] 所有维度都能被头数整除
- [ ] Student有两个独立Decoder（与Teacher对齐）

### 7.2 损失函数验证

- [ ] 不使用KL散度（3D点云不是概率分布）
- [ ] 使用欧几里得距离（L2范数）作为蒸馏损失
- [ ] 损失计算包括归一化步骤（norm_mode='avg_dis'）
- [ ] Teacher输出使用`.detach()`防止梯度泄露

### 7.3 训练流程验证

- [ ] Teacher设置为`eval()`模式
- [ ] Teacher所有参数`requires_grad=False`
- [ ] Student输出格式与Teacher一致（pts3d + conf）
- [ ] 验证集使用完整7-Scenes数据集（不是只有heads）

---

## 八、预期结果

### 8.1 参数量

| 模型 | 参数量 | 压缩率 |
|------|--------|--------|
| Teacher | 571M | - |
| Student-S | ~46M | 92% |
| Student-M | ~85M | 85% |
| Student-L | ~150M | 74% |

### 8.2 性能目标

- **精度损失**: ≤ 1% (相对于Teacher)
- **推理速度**: 提升3-5倍
- **显存占用**: 减少70-80%

---

## 九、实施步骤

1. **修正Student架构配置** - 基于正确的Teacher配置重新设计
2. **重写蒸馏损失函数** - 使用Regr3D风格的欧几里得距离
3. **更新训练代码** - 确保流程正确（Teacher冻结、Student更新）
4. **验证数据完整性** - 确保使用完整7-Scenes数据集
5. **运行验证实验** - 小规模验证架构和损失函数
6. **完整训练** - 执行完整蒸馏训练

---

## 十、参考资料

- DUSt3R完整架构文档: `docs/DUSt3R完整架构文档.md`
- DUSt3R论文: arXiv:2312.14132
- DUSt3R代码: https://github.com/naver/dust3r
- 当前实现: `scripts/train_distill.py`, `scripts/models/__init__.py`

---

**下一步**: 根据此规划方案，修正代码实现。

