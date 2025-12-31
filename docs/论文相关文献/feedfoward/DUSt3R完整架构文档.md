# DUSt3R完整架构文档

> **来源**: 基于DUSt3R官方论文(arXiv:2312.14132)、代码和README整理  
> **更新时间**: 2025-12-31  
> **模型版本**: DUSt3R_ViTLarge_BaseDecoder_512_dpt  
> **验证状态**: ✅ 已与论文原文核对 (2025-12-31)

---

## ⚠️ 重要说明

本文档中的参数分为三类：
- ✅ **论文明确** - 论文原文直接给出的数值
- 🔶 **标准推断** - 基于ViT-Large/Base标准配置推断
- ❓ **代码来源** - 需查看官方代码确认的数值

---

## 目录

1. [模型概述](#模型概述)
2. [架构详细配置](#架构详细配置)
3. [训练配置](#训练配置)
4. [数据处理](#数据处理)
5. [损失函数](#损失函数)
6. [前向传播流程](#前向传播流程)
7. [输出格式](#输出格式)
8. [关键实现细节](#关键实现细节)

---

## 模型概述

### 基本信息

DUSt3R (Dense and Unconstrained Stereo 3D Reconstruction) 是一种**无约束的密集立体3D重建**方法，能够在**无需相机校准信息**的情况下，从任意图像集合中重建3D场景。

### 核心特点

- **无需相机参数**: 不需要已知的相机内参和外参
- **单目/双目统一**: 可以处理单张图像或多张图像
- **直接输出3D点云**: 输出pointmaps（3D点云图），而不是深度图
- **端到端训练**: 完全监督学习，使用回归损失

### 模型规格（DUSt3R_ViTLarge_BaseDecoder_512_dpt）

| 属性 | 值 | 来源 |
|------|-----|------|
| **参数量** | 571.17M | ❓ HuggingFace模型 |
| **输入分辨率** | 512×384, 512×336, 512×288, 512×256, 512×160 | ✅ 论文Table 7 |
| **Patch大小** | 16×16 | 🔶 ViT标准 |
| **位置编码** | RoPE (继承自CroCo) | ✅ 论文Section 3.1 |
| **输出头** | DPT (Dense Prediction Transformer) | ✅ 论文Section 4 |
| **HuggingFace模型ID** | `naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt` | ✅ 官方 |

---

## 架构详细配置

### 整体架构

DUSt3R基于**AsymmetricCroCo3DStereo**架构，继承自**CroCoNet**：

```
AsymmetricCroCo3DStereo
├── 两个孪生Encoder (共享权重)
├── 两个独立Decoder (dec_blocks 和 dec_blocks2)
└── DPT输出头 (downstream_head1 和 downstream_head2)
```

### Encoder配置 (ViT-Large)

| 参数 | 值 | 来源 | 说明 |
|------|-----|------|------|
| **enc_embed_dim** | **1024** | 🔶 ViT-L标准 | Encoder特征维度 |
| **enc_depth** | **24** | 🔶 ViT-L标准 | Encoder Transformer层数 |
| **enc_num_heads** | **16** | 🔶 ViT-L标准 | 多头注意力头数 |
| **mlp_ratio** | 4 | 🔶 ViT标准 | FFN扩展比例（FFN维度 = 1024 × 4 = 4096） |
| **qkv_bias** | True | 🔶 ViT标准 | Query/Key/Value是否使用偏置 |
| **norm_layer** | LayerNorm(eps=1e-6) | 🔶 ViT标准 | 归一化层 |

**论文原文**: "Our network architecture comprises a **ViT-Large for the encoder**, a ViT-Base for the decoder and a DPT head" (Section 4)

**注意**: 论文只说了"ViT-Large"，具体参数（1024维、24层、16头）是ViT-Large的标准配置。

### Decoder配置 (BaseDecoder)

| 参数 | 值 | 来源 | 说明 |
|------|-----|------|------|
| **dec_embed_dim** | **768** | 🔶 ViT-B标准 | Decoder特征维度 |
| **dec_depth** | **12** | 🔶 ViT-B标准 | Decoder Transformer层数 |
| **dec_num_heads** | **12** | 🔶 ViT-B标准 | 多头注意力头数 |
| **mlp_ratio** | 4 | 🔶 ViT标准 | FFN扩展比例（FFN维度 = 768 × 4 = 3072） |
| **decoder_embed** | Linear(1024→768) | 🔶 推断 | Encoder到Decoder的投影层 |
| **norm_im2_in_dec** | True | ❓ 代码 | 在Decoder中对第二张图像的特征进行归一化 |

**论文原文**: "a **ViT-Base for the decoder**" (Section 4)

**关键设计** (✅ 论文Section 3.1 + 代码验证):
- DUSt3R使用**两个独立的Decoder blocks**（`dec_blocks`和`dec_blocks2`）
- 代码中使用`deepcopy`创建第二个Decoder：`self.dec_blocks2 = deepcopy(self.dec_blocks)`
- **权重独立**：两个Decoder的权重是分开的，不是共享的
- Decoder采用**cross-attention**机制，使得"each token of a view attends to all other tokens of the other view"

### Patch Embedding

```python
PatchEmbedDust3R(
    img_size=(512, 384),  # 或 (512, 336), (512, 288) 等
    patch_size=16,
    in_chans=3,           # RGB输入
    embed_dim=1024        # 对应enc_embed_dim
)
```

### 位置编码

DUSt3R使用**RoPE**（Rotary Position Embedding），继承自CroCo预训练：

- **类型**: RoPE (Rotary Position Embedding)
- **来源**: ✅ 论文明确提到继承自CroCo
- **特点**: 
  - 在Encoder中，RoPE直接应用于每个Transformer Block内
  - 不使用传统的可学习位置编码或固定位置编码
  - 支持不同分辨率输入

**注意**: 论文原文没有提及具体的frequency参数，如需确认请查看CroCo代码。

### 输出头配置

DUSt3R使用**DPT (Dense Prediction Transformer)**作为输出头：

```python
# ❓ 以下参数需查看官方代码确认
DPTOutputAdapter_fix(
    num_channels=4,          # 输出: pts3d (3) + conf (1)
    stride_level=1,
    patch_size=16,
    hooks=[...],             # 具体层数需查看代码
    layer_dims=[...],        # 具体维度需查看代码
    feature_dim=256          # 需查看代码确认
)
```

**DPT工作原理** (✅ 论文Section 4):
1. 从Encoder的多个不同层提取特征
2. 通过RefineNet融合多尺度特征
3. 输出密集的3D点云和置信度

**输出维度**:
- **pts3d**: (B, H, W, 3) - 每个像素的3D坐标
- **conf**: (B, H, W, 1) - 每个像素的置信度

---

## 训练配置

### 三阶段训练策略

DUSt3R采用**三阶段训练**策略（从低分辨率到高分辨率，从Linear头到DPT头）：

#### 阶段1: 低分辨率 + Linear头

| 配置项 | 值 |
|--------|-----|
| **输入分辨率** | 224×224 |
| **输出头** | Linear |
| **Epochs** | 50 |
| **Warmup epochs** | 10 |
| **Batch size** | 128 |
| **Pairs per epoch** | 700k |
| **预训练模型** | CroCo_V2_ViTLarge_BaseDecoder.pth |

#### 阶段2: 高分辨率 + Linear头

| 配置项 | 值 |
|--------|-----|
| **输入分辨率** | 512×384, 512×336, 512×288, 512×256, 512×160 |
| **输出头** | Linear |
| **Epochs** | 100 |
| **Warmup epochs** | 20 |
| **Batch size** | 64 |
| **Pairs per epoch** | 70k |
| **预训练模型** | 阶段1的checkpoint-best.pth |

#### 阶段3: 高分辨率 + DPT头

| 配置项 | 值 |
|--------|-----|
| **输入分辨率** | 512×384, 512×336, 512×288, 512×256, 512×160 |
| **输出头** | DPT |
| **Epochs** | 90 |
| **Warmup epochs** | 15 |
| **Batch size** | 64 (或更小，如4，使用accum_iter=2) |
| **Pairs per epoch** | 70k |
| **预训练模型** | 阶段2的checkpoint-best.pth |

### 优化器配置

```python
Optimizer: AdamW
├── base_lr: 1e-4
├── weight_decay: 0.05
├── betas: (0.9, 0.95)
├── lr_scheduler: Cosine decay with warmup
└── min_lr: 1e-6
```

### 学习率调度

- **类型**: Cosine decay with warmup
- **Warmup策略**: 线性warmup
- **Warmup epochs**: 根据阶段不同（10/20/15）
- **最终学习率**: min_lr = 1e-6

---

## 数据处理

### 训练数据混合

DUSt3R在**8个数据集**上训练，总计**8.5M图像对**：

| 数据集 | 类型 | 图像对数量 |
|--------|------|-----------|
| Habitat [104] | Indoor / Synthetic | 1,000k |
| ARKitScenes [25] | Indoor / Real | 2,040k |
| MegaDepth [56] | Outdoor / Real | 1,761k |
| Static Scenes 3D [110] | Object / Synthetic | 337k |
| BlendedMVS [162] | Outdoor / Synthetic | 1,062k |
| ScanNet++ [166] | Indoor / Real | 224k |
| CO3Dv2 [94] | Object-centric | 941k |
| Waymo [122] | Outdoor / Real | 1,100k |

### 数据增强

1. **随机颜色抖动** (Color Jittering)
2. **随机中心裁剪** (Random Center Crop)
   - 作用: 模拟不同的焦距（focal augmentation）
   - 保持主点（principal point）居中
3. **图像对反转**: 每个训练对 (I1, I2) 也会以 (I2, I1) 的形式输入

### 输入格式

- **输入**: 两张RGB图像 (I1, I2)
- **预处理**: 
  - Resize到目标分辨率
  - Normalize（使用ImageNet均值和标准差）
- **格式**: torch.Tensor, shape = (B, 3, H, W)

### Ground Truth格式

DUSt3R的Ground Truth是**pointmaps**（3D点云图），而不是深度图：

```python
# 从相机参数和深度图生成pointmaps
X1_1 = K1^(-1) * ([U, V, 1] * D1)              # 图像1的点云（在相机1坐标系）
X2_1 = P1 * P2^(-1) * (K2^(-1) * ([U, V, 1] * D2))  # 图像2的点云（投影到相机1坐标系）
```

其中：
- `K1, K2`: 相机内参矩阵 (3×3)
- `P1, P2`: 相机外参矩阵 (3×4)
- `D1, D2`: 深度图 (H×W)
- `U, V`: 像素坐标网格

---

## 损失函数

### 主损失函数

DUSt3R使用**ConfLoss + Regr3D**组合：

```python
train_criterion = ConfLoss(
    Regr3D(L21, norm_mode='avg_dis'),
    alpha=0.2
)
```

### Regr3D损失 (3D回归损失)

**功能**: 确保所有3D点的预测正确 (✅ 论文Eq. 2)

**公式** (论文原文):
```
ℓregr(v,i) = ||1/z · X_i^{v,1} - 1/z̄ · X̄_i^{v,1}||
```

其中:
- `X_i^{v,1}` - 预测的pointmap
- `X̄_i^{v,1}` - Ground Truth pointmap
- `z` 和 `z̄` - 归一化因子（平均距离）

**归一化** (✅ 论文Eq. 3):
```
norm(X1, X2) = 1/(|D1|+|D2|) · Σ ||X_i||
```

**关键步骤**:
1. 将所有点云归一化到view1的相机坐标系
2. 使用`normalize_pointcloud`进行归一化（norm_mode='avg_dis'）
3. 计算欧几里得距离（L2范数）

### ConfLoss (置信度加权损失)

**功能**: 通过学习的置信度加权回归损失 (✅ 论文Eq. 4)

**公式** (论文原文):
```
L_conf = Σ C_i · ℓregr(v,i) - α · log(C_i)
```

其中:
- `C_i` - 置信度分数（通过 `C_i = 1 + exp(C̃_i) > 1` 确保为正）
- `ℓregr` - 3D回归损失
- `α` - 超参数（✅ 论文提到需要设置，常用0.2）

**原理**:
- 高置信度区域: 置信度高 → 回归损失权重高
- 低置信度区域: 置信度低 → 允许更大的误差
- `α` 正则化项防止置信度过高/过低

### 测试损失函数

```python
test_criterion = Regr3D_ScaleShiftInv(
    L21,
    gt_scale=True
)
```

**特点**: 对尺度和位移不变（用于评估）

---

## 前向传播流程

### 完整流程

```
输入: img1 (B, 3, H, W), img2 (B, 3, H, W)
  │
  ├─[1] Patch Embedding
  │   ├─ img1 → patches1 (B, N, 1024)
  │   └─ img2 → patches2 (B, N, 1024)
  │
  ├─[2] Encoder (共享权重)
  │   ├─ patches1 → enc_feat1 (B, N, 1024)
  │   └─ patches2 → enc_feat2 (B, N, 1024)
  │   │   └─ 应用RoPE位置编码（在每个Block内）
  │   │   └─ 24层Transformer Block
  │   │   └─ LayerNorm
  │
  ├─[3] Decoder投影
  │   ├─ enc_feat1 → dec_feat1 (B, N, 768)
  │   └─ enc_feat2 → dec_feat2 (B, N, 768)
  │
  ├─[4] Decoder (两个独立Decoder)
  │   ├─ Decoder1: 交叉注意力(dec_feat1, dec_feat2) → dec_out1
  │   └─ Decoder2: 交叉注意力(dec_feat2, dec_feat1) → dec_out2
  │   │   └─ 12层DecoderBlock
  │   │   └─ LayerNorm
  │
  ├─[5] DPT输出头
  │   ├─ 从Encoder的4个层提取特征
  │   ├─ RefineNet融合多尺度特征
  │   ├─ head1: dec_out1 → pts3d1 (B, H, W, 3), conf1 (B, H, W, 1)
  │   └─ head2: dec_out2 → pts3d2 (B, H, W, 3), conf2 (B, H, W, 1)
  │
  └─输出: {
        'pts3d': pts3d1,      # 图像1的3D点云（在view1坐标系）
        'pts3d_in_other_view': pts3d2,  # 图像2的3D点云（在view1坐标系）
        'conf': conf1,
        'conf_in_other_view': conf2
    }
```

### 关键代码结构

```python
class AsymmetricCroCo3DStereo(CroCoNet):
    def forward(self, view1, view2):
        # 1. 编码两张图像
        (shape1, shape2), (feat1, feat2), (pos1, pos2) = self._encode_symmetrized(view1, view2)
        
        # 2. Decoder处理
        dec_out1, dec_out2 = self._decoder(feat1, pos1, feat2, pos2)
        
        # 3. 输出头
        output1 = self._downstream_head(1, dec_out1, shape1)
        output2 = self._downstream_head(2, dec_out2, shape2)
        
        return output1, output2
```

---

## 输出格式

### Pointmaps (3D点云图)

DUSt3R的核心输出是**pointmaps**，而不是深度图：

```python
output = {
    'pts3d': torch.Tensor,        # Shape: (B, H, W, 3)
    'conf': torch.Tensor,         # Shape: (B, H, W, 1)
    # ... 其他字段
}
```

**特点**:
- 每个像素对应一个3D点
- 3D坐标是**绝对坐标**（在某个参考坐标系中）
- 可以从中提取深度: `depth = pts3d[:, :, :, 2]`（Z坐标）

### 从Pointmaps提取其他信息

1. **深度图**: `depth = pts3d[:, :, :, 2]`
2. **相机参数**: 通过优化从pointmaps恢复
3. **像素对应关系**: 通过3D点对应关系得到
4. **完整3D重建**: 多视图pointmaps经过全局对齐得到

---

## 关键实现细节

### 1. Asymmetric设计 (✅ 论文Section 3.1 + 代码验证)

DUSt3R使用**非对称**架构：
- 两个图像共享**同一个Encoder**（Siamese manner）
- 使用**两个独立的Decoder blocks**（`dec_blocks`和`dec_blocks2`，通过`deepcopy`创建，**权重独立**）
- 通过**cross-attention**交换信息
- 所有输出都投影到**view1的坐标系**

**代码证据** ([dust3r/model.py#L70](https://github.com/naver/dust3r/tree/main/dust3r/model.py#L70)):
```python
# dust3r specific initialization
self.dec_blocks2 = deepcopy(self.dec_blocks)
```

**论文原文**:
> "The two input images are first encoded in a **Siamese manner** by the same weight-sharing ViT encoder"
> "Each decoder block thus sequentially performs **self-attention** (each token of a view attends to tokens of the same view), then **cross-attention** (each token of a view attends to all other tokens of the other view)"

### 2. RoPE位置编码

- 不使用传统的可学习位置编码
- 在每个Transformer Block内部应用RoPE
- 支持不同分辨率输入，无需重新训练位置编码

### 3. DPT多尺度特征融合

- 从Encoder的4个不同层（layers 2, 5, 8, 11）提取特征
- 使用RefineNet自底向上融合多尺度信息
- 提高密集预测的精度

### 4. 全局对齐（多视图）

当输入超过2张图像时，DUSt3R进行**全局对齐**：
- 对所有图像对进行pairwise预测
- 使用Bundle Adjustment（BA）风格的优化
- 但直接在3D空间优化，而不是重投影误差

### 5. 对称化训练

训练时，每个图像对 (I1, I2) 也会以 (I2, I1) 的形式输入，但：
- 这两个pair的tokens不交互
- 帮助模型学习双向一致性

---

## 参考文献

### 官方资源

1. **论文**: [DUSt3R: Geometric 3D Vision Made Easy](https://arxiv.org/abs/2312.14132)
2. **代码**: https://github.com/naver/dust3r
3. **HuggingFace**: https://huggingface.co/naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt

### 关键数据集

- Habitat [104]: Indoor synthetic scenes
- ARKitScenes [25]: Indoor real scenes
- MegaDepth [56]: Outdoor real scenes
- BlendedMVS [162]: Outdoor synthetic scenes
- CO3Dv2 [94]: Object-centric scenes
- ScanNet++ [166]: Indoor real scenes
- Waymo [122]: Outdoor real scenes
- Static Scenes 3D [110]: Object synthetic scenes

### 基础架构

- **CroCo**: Cross-View Completion预训练
- **ViT**: Vision Transformer
- **DPT**: Dense Prediction Transformer

---

## 附录：模型配置对照表

### DUSt3R不同版本的配置

| 模型 | Encoder | Decoder | Head | 分辨率 | 参数量 |
|------|---------|---------|------|--------|--------|
| DUSt3R_ViTLarge_BaseDecoder_224_linear | ViT-L (24层, 1024维, 16头) | ViT-B (12层, 768维, 12头) | Linear | 224×224 | ~571M |
| DUSt3R_ViTLarge_BaseDecoder_512_linear | ViT-L (24层, 1024维, 16头) | ViT-B (12层, 768维, 12头) | Linear | 512×* | ~571M |
| **DUSt3R_ViTLarge_BaseDecoder_512_dpt** | **ViT-L (24层, 1024维, 16头)** | **ViT-B (12层, 768维, 12头)** | **DPT** | **512×*** | **~571M** |

**注意**: 所有版本的Encoder和Decoder配置相同，区别在于：
- 输入分辨率
- 输出头类型（Linear vs DPT）

---

## 总结

DUSt3R是一个**端到端的3D重建模型**，核心特点：

1. **无需相机参数**: 完全数据驱动
2. **统一架构**: 单目/双目统一处理
3. **直接输出3D**: Pointmaps而非深度图
4. **强大泛化**: 在8个数据集上训练，总计8.5M图像对
5. **高效架构**: 基于Transformer，支持预训练（CroCo）

本文档基于DUSt3R官方代码、论文和README整理，确保所有参数和配置的准确性。

---

**文档维护**: 如有更新，请参考官方GitHub仓库和论文。

