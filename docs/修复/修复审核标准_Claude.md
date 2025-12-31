# DUSt3R 蒸馏代码修复审核标准

> **创建日期**: 2025-12-31  
> **用途**: 作为审核Cursor修改的验收标准  
> **审核人**: Claude  
> **执行人**: Cursor

---

## 一、架构基准（必须严格对齐）

### 1.1 Teacher架构（不可更改的参考基准）

```
DUSt3R_ViTLarge_BaseDecoder_512_dpt (~571M 参数)
│
├── Encoder: ViT-Large
│   ├── 层数: 24
│   ├── 维度: 1024
│   ├── 头数: 16
│   ├── FFN比例: 4.0 (即 4096)
│   └── 位置编码: RoPE100 (非可学习)
│
├── Decoder: ViT-Base × 2 (独立，deepcopy)
│   ├── 层数: 12 × 2
│   ├── 维度: 768
│   ├── 头数: 12
│   ├── FFN比例: 4.0 (即 3072)
│   ├── 包含: Self-Attention + Cross-Attention
│   └── 位置编码: RoPE100
│
├── 输出头: DPT (多尺度特征融合)
│   ├── 从Decoder多层提取特征
│   └── 输出: pts3d (B,H,W,3) + conf (B,H,W,1)
│
└── 特点:
    ├── ❌ 不使用CLS token
    ├── ✅ 使用RoPE位置编码
    ├── ✅ 两个独立Decoder通过Cross-Attention交互
    └── ✅ DPT多尺度输出头
```

### 1.2 目标Student架构（Student-S，必须实现）

```
Student-S (~184M 参数，压缩率 ~68%)
│
├── Encoder: ViT缩减版
│   ├── 层数: 17 (Teacher的71%)
│   ├── 维度: 720 (Teacher的70%)
│   ├── 头数: 12 (720/12=60 ✓整除)
│   ├── FFN比例: 4.0
│   └── 位置编码: RoPE100 (与Teacher一致)
│
├── Decoder: 缩减版 × 2 (独立，deepcopy)
│   ├── 层数: 8 × 2 (Teacher的67%)
│   ├── 维度: 540 (Teacher的70%)
│   ├── 头数: 9 (540/9=60 ✓整除)
│   ├── FFN比例: 4.0
│   ├── 包含: Self-Attention + Cross-Attention
│   └── 位置编码: RoPE100
│
├── 输出头: DPT或简化版DPT
│   └── 输出格式必须与Teacher一致: pts3d + conf
│
└── 必须保持的特性:
    ├── ❌ 不使用CLS token
    ├── ✅ 使用RoPE位置编码
    ├── ✅ 两个独立Decoder (deepcopy)
    ├── ✅ Cross-Attention机制
    └── ✅ 输出格式与Teacher对齐
```

### 1.3 维度整除验证表

| 组件 | 维度 | 头数 | head_dim | 验证 |
|------|------|------|----------|------|
| Student Encoder | 720 | 12 | 60 | ✅ 720%12=0 |
| Student Decoder | 540 | 9 | 60 | ✅ 540%9=0 |
| Teacher Encoder | 1024 | 16 | 64 | ✅ 参考 |
| Teacher Decoder | 768 | 12 | 64 | ✅ 参考 |

---

## 二、损失函数要求（核心修改点）

### 2.1 正确的损失函数

```python
# ✅ 正确实现
L_total = α · L_task + β · L_distill + γ · L_conf

其中:
- L_task: 使用Regr3D (L2距离 + normalize_pointcloud)
- L_distill: Student vs Teacher的L2距离 (带归一化)
- L_conf: 置信度对齐损失 (MSE)
```

### 2.2 必须删除的代码

```python
# ❌ 必须删除 (KL散度相关)
s_log_prob = F.log_softmax(s_flat / self.temperature, dim=-1)
t_prob = F.softmax(t_flat / self.temperature, dim=-1)
losses['kd'] = F.kl_div(...)
```

### 2.3 必须添加的导入

```python
# ✅ 必须导入
from dust3r.utils.geometry import normalize_pointcloud
from dust3r.losses import L21  # 可选，用于参考
```

### 2.4 正确的蒸馏损失实现

```python
def Regr3D_Loss(pred_pts, target_pts, norm_mode='avg_dis'):
    """
    DUSt3R风格的3D回归损失
    
    Args:
        pred_pts: Student输出 (B, H, W, 3)
        target_pts: Teacher输出 (B, H, W, 3)
        norm_mode: 归一化模式 ('avg_dis' 推荐)
    
    Returns:
        loss: 标量损失值
    """
    # 归一化点云
    pred_norm = normalize_pointcloud(pred_pts, None, norm_mode)
    target_norm = normalize_pointcloud(target_pts, None, norm_mode)
    
    # L2距离
    loss = torch.norm(pred_norm - target_norm, dim=-1).mean()
    return loss
```

---

## 三、Student架构修改验收标准

### 3.1 必须实现的组件

| 组件 | 当前状态 | 目标状态 | 验收标准 |
|------|----------|----------|----------|
| Decoder数量 | 1个 | 2个独立 | `dec_blocks2 = deepcopy(dec_blocks)` |
| Cross-Attention | 无 | 有 | DecoderBlock包含`cross_attn`层 |
| CLS Token | 有 | 无 | 删除`cls_token`相关代码 |
| 位置编码 | 可学习 | RoPE | 使用`RoPE2D`或等效实现 |
| 输出头 | Linear | DPT | 使用`create_dpt_head`或简化版 |

### 3.2 DecoderBlock结构验收

```python
# ✅ 正确的DecoderBlock结构
class DecoderBlock(nn.Module):
    def __init__(self, dim, num_heads, mlp_ratio=4., rope=None, ...):
        self.norm1 = nn.LayerNorm(dim)
        self.attn = Attention(dim, num_heads, rope=rope)      # self-attention
        self.norm2 = nn.LayerNorm(dim)
        self.cross_attn = CrossAttention(dim, num_heads, rope=rope)  # ✅ 必须有
        self.norm3 = nn.LayerNorm(dim)
        self.mlp = Mlp(dim, int(dim * mlp_ratio))
    
    def forward(self, x, y, xpos, ypos):
        # x: 当前view, y: 另一个view
        x = x + self.attn(self.norm1(x), xpos)                    # self-attn
        x = x + self.cross_attn(self.norm2(x), y, y, xpos, ypos)  # cross-attn ✅
        x = x + self.mlp(self.norm3(x))
        return x, y
```

### 3.3 前向传播流程验收

```python
# ✅ 正确的前向传播
def forward(self, view1, view2):
    # 1. 编码 (共享Encoder)
    feat1, pos1 = self.encoder(view1['img'])  # (B, N, enc_dim)
    feat2, pos2 = self.encoder(view2['img'])
    
    # 2. Decoder投影
    dec_feat1 = self.decoder_embed(feat1)  # (B, N, dec_dim)
    dec_feat2 = self.decoder_embed(feat2)
    
    # 3. 双Decoder处理 (通过Cross-Attention交互)
    for blk1, blk2 in zip(self.dec_blocks, self.dec_blocks2):
        dec_feat1, _ = blk1(dec_feat1, dec_feat2, pos1, pos2)
        dec_feat2, _ = blk2(dec_feat2, dec_feat1, pos2, pos1)
    
    # 4. 输出头
    output1 = self.head1(dec_feat1)  # pts3d + conf
    output2 = self.head2(dec_feat2)
    
    return output1, output2
```

---

## 四、配置文件修改验收

### 4.1 distill.yaml必须修改项

```yaml
# ✅ 正确配置
student:
  arch: "dust3r_student_s"
  student_config:
    encoder_layers: 17    # Teacher: 24
    encoder_dim: 720      # Teacher: 1024
    encoder_heads: 12     # Teacher: 16
    decoder_layers: 8     # Teacher: 12
    decoder_dim: 540      # Teacher: 768
    decoder_heads: 9      # Teacher: 12

distill:
  enable: true
  # ❌ 删除: kd_temperature
  beta_distill: [0.5, 0.7]   # 蒸馏损失权重
  gamma_conf: [0.0, 0.1]     # 置信度损失权重
  norm_mode: 'avg_dis'       # 归一化模式
```

### 4.2 必须删除的配置

```yaml
# ❌ 必须删除
kd_temperature: [3, 5]  # KL温度 - 不再使用
```

---

## 五、问题检查清单

### 5.1 P0问题验收（必须全部通过）

| ID | 问题 | 验收方法 |
|----|------|----------|
| P0-1 | KL散度→L2距离 | 搜索`kl_div`应无结果 |
| P0-2 | 1→2个Decoder | 搜索`dec_blocks2`应存在 |
| P0-3 | 添加Cross-Attention | 搜索`cross_attn`应存在 |
| P0-4 | 可学习→RoPE | 搜索`pos_embed = nn.Parameter`应无结果 |
| P0-5 | 删除CLS Token | 搜索`cls_token`应无结果 |
| P0-6 | Linear→DPT | 搜索`create_dpt_head`或DPT相关 |
| P0-7 | 修正前向流程 | 验证双Decoder交互逻辑 |
| P0-8 | 导入依赖 | 搜索`normalize_pointcloud`导入 |

### 5.2 P1问题验收（建议通过）

| ID | 问题 | 验收方法 |
|----|------|----------|
| P1-1 | 任务损失归一化 | 搜索`Regr3D_Loss`使用 |
| P1-2 | L_conf实现 | 搜索`conf`损失计算 |
| P1-3 | Teacher冻结 | 搜索`requires_grad = False` |
| P1-4 | 删除温度配置 | YAML中无`kd_temperature` |
| P1-5 | Student配置更新 | YAML中encoder_layers=17 |
| P1-6 | 配置注释修正 | 注释显示正确的Teacher值 |

---

## 六、依赖可用性确认

### 6.1 已确认可用的DUSt3R依赖

| 依赖 | 导入路径 | 用途 |
|------|----------|------|
| `normalize_pointcloud` | `dust3r.utils.geometry` | 点云归一化 |
| `L21` | `dust3r.losses` | 欧几里得距离 |
| `Regr3D` | `dust3r.losses` | 3D回归损失 |
| `ConfLoss` | `dust3r.losses` | 置信度加权 |
| `create_dpt_head` | `dust3r.heads.dpt_head` | DPT输出头 |

### 6.2 已确认可用的CroCo依赖

| 依赖 | 导入路径 | 用途 |
|------|----------|------|
| `RoPE2D` | `croco.models.pos_embed` | 2D旋转位置编码 |
| `cuRoPE2D` | `croco.models.curope` | CUDA加速RoPE |
| `DecoderBlock` | `croco.models.blocks` | Decoder块（含cross-attn） |
| `CrossAttention` | `croco.models.blocks` | 跨视图注意力 |
| `Attention` | `croco.models.blocks` | 自注意力 |

---

## 七、审核流程

### 7.1 每次修改的审核步骤

1. **阅读修改日志**: 查看`docs/修复/`目录下的修改记录
2. **对照检查清单**: 逐项验证P0/P1问题是否解决
3. **架构验证**: 确认Student架构与目标一致
4. **损失函数验证**: 确认使用L2距离+归一化
5. **配置验证**: 确认YAML配置正确
6. **代码搜索验证**: 使用grep搜索关键词确认

### 7.2 审核结果分类

| 结果 | 说明 | 后续动作 |
|------|------|----------|
| ✅ 通过 | 修改符合要求 | 确认合并 |
| ⚠️ 部分通过 | 大部分正确，有小问题 | 指出问题，继续修改 |
| ❌ 不通过 | 存在重大偏差 | 详细说明问题，重新修改 |

---

## 八、最终验收标准

### 8.1 代码可运行性

```bash
# 必须能通过的测试
python -c "from scripts.models import create_student_model; m = create_student_model(); print(m)"
python scripts/train_distill.py --dry-run --max-epochs 1
```

### 8.2 架构正确性

```python
# Student模型必须包含
assert hasattr(model, 'dec_blocks')
assert hasattr(model, 'dec_blocks2')  # 两个独立Decoder
assert hasattr(model.dec_blocks[0], 'cross_attn')  # Cross-Attention
assert not hasattr(model, 'cls_token')  # 无CLS Token
```

### 8.3 损失函数正确性

```python
# 损失函数必须使用L2距离
assert 'normalize_pointcloud' in open('scripts/train_distill.py').read()
assert 'kl_div' not in open('scripts/train_distill.py').read()
```

---

**文档版本**: v1.0  
**创建时间**: 2025-12-31  
**用途**: Cursor修改的审核标准  
**审核人**: Claude
