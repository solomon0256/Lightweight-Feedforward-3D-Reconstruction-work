# DUSt3R Baseline 测试完整结果

> **最后更新**: 2025-12-26  
> **模型**: DUSt3R_ViTLarge_BaseDecoder_512_dpt  
> **数据集**: 7-Scenes heads  
> **环境**: RTX 4070 / Windows 11 / PyTorch 2.1

---

## 📊 结果总览

| 类别 | 核心指标 | 数值 | 论文参考 | 状态 |
|------|----------|------|----------|:----:|
| **VisLoc** | median_pos_error | **1.85 cm** | 2 cm | ✅ 超越 |
| **VisLoc** | median_angular_error | **1.55°** | 1.37° | ✅ 接近 |
| **深度** | AbsRel | 0.1168 | - | ✅ |
| **深度** | δ<1.25 | 0.8995 | - | ✅ |
| **模型** | Parameters | 571.17M | - | ✅ |
| **延迟** | Latency P50 | 353ms | - | ✅ |
| **显存** | VRAM Peak | 2.76GB | - | ✅ |

---

## 1️⃣ 模型本体信息

| 指标 | 值 | 单位 |
|------|-----|------|
| **params_total** | 571,166,720 | |
| **params_encoder** | 306,533,376 | |
| **params_decoder** | 264,633,344 | |
| **params_trainable** | 571,166,720 | |
| **MACs** | 464,700,000,000 | |
| **FLOPs** | 929,400,000,000 | |

### 模型配置
```yaml
model_name: DUSt3R_ViTLarge_BaseDecoder_512_dpt
input_resolution: [512, 384]
encoder: ViT-Large
decoder: BaseDecoder + DPT Head
precision: FP32
```

---

## 2️⃣ 显存占用

| 指标 | 值 | 条件 |
|------|-----|------|
| **vram_baseline** | 1.23 GB | 模型加载后 |
| **vram_peak** | 2.76 GB | 推理时峰值 |
| **vram_delta** | 1.53 GB | 推理增量 |

### 测试条件
- 输入分辨率: 512×384
- 图像对数量: 1 pair
- Batch size: 1
- CUDA: 12.1

---

## 3️⃣ 推理延迟

| 指标 | 值 (ms) | 说明 |
|------|---------|------|
| **t_pair_min** | 341 | 最小延迟 |
| **t_pair_p50** | 353 | 中位延迟 |
| **t_pair_p95** | 378 | 95分位延迟 |
| **t_pair_max** | 401 | 最大延迟 |
| **t_pair_mean** | 355 | 平均延迟 |
| **t_pair_std** | 12 | 标准差 |
| **throughput** | 2.82 | pairs/秒 |

### 测试条件
- 预热: 10 iterations
- 测量: 100 iterations
- 输入分辨率: 512×384

---

## 4️⃣ 深度估计精度

> 数据集: 7-Scenes heads (30 pairs)

| 指标 | 值 | 描述 |
|------|-----|------|
| **absrel** | 0.1168 | 平均绝对相对误差 |
| **sqrel** | 0.0359 | 平均平方相对误差 |
| **rmse** | 0.1446 m | 均方根误差 |
| **rmse_log** | 0.1652 | 对数均方根误差 |
| **delta1** | 0.8995 | δ < 1.25 |
| **delta2** | 0.9633 | δ < 1.25² |
| **delta3** | 0.9778 | δ < 1.25³ |
| **si_log** | 0.1611 | 尺度不变对数误差 |

### 计算公式
```
AbsRel = mean(|d_pred - d_gt| / d_gt)
SqRel = mean((d_pred - d_gt)² / d_gt)
RMSE = sqrt(mean((d_pred - d_gt)²))
RMSE_log = sqrt(mean((log(d_pred) - log(d_gt))²))
δ_n = % of pixels where max(d_pred/d_gt, d_gt/d_pred) < 1.25^n
SI_log = sqrt(mean((log(d_pred) - log(d_gt))² - (mean(log(d_pred) - log(d_gt)))²))
```

---

## 5️⃣ 位姿估计精度 - VisLoc (Visual Localization)

> 数据集: 7-Scenes heads (1000 query frames)  
> 方法: PnP with poselib  
> Pairs: pose_based_top20.txt (基于位姿距离)

| 指标 | 值 | 论文参考 |
|------|-----|----------|
| **median_pos_error** | 1.85 cm | 2 cm |
| **median_angular_error** | 1.55° | 1.37° |
| **acc@0.1m,1deg** | 32.10% | - |
| **acc@0.25m,2deg** | 59.80% | - |
| **acc@0.5m,5deg** | 77.60% | - |
| **acc@5m,10deg** | 78.70% | - |

### 关键配置
```yaml
pnp_mode: poselib
reprojection_error_diag_ratio: 0.008
topk: 1  # 使用top-1匹配帧
pairsfile: pose_based_top20  # 基于位姿生成的pairs
```

### 复现关键点
1. ⚠️ **必须使用基于位姿的pairs文件**，不能用顺序匹配
2. ⚠️ Pose方向: 7-scenes是cam2world，kapture需要world2cam（求逆）
3. ✅ 内参: fx=fy=525 (RGB相机)

---

## 6️⃣ 位姿估计精度 - Pairwise

> 数据集: 7-Scenes heads (30 pairs)  
> 方法: 从3D点云直接恢复相对位姿

| 指标 | 值 | 描述 |
|------|-----|------|
| **RRE** | 6.06° | 相对旋转误差 |
| **RTE** | 6.83 cm | 相对平移误差 |

---

## 7️⃣ 能耗指标

| 指标 | 值 | 状态 |
|------|-----|:----:|
| power_idle | - | ⏳ 待测 |
| power_inference | - | ⏳ 待测 |
| energy_per_pair | - | ⏳ 待测 |
| energy_per_frame | - | ⏳ 待测 |
| thermal_throttling | - | ⏳ 待测 |

---

## 📁 相关文件

| 文件 | 路径 | 说明 |
|------|------|------|
| JSON结果 | [logs/baseline_complete.json](../logs/baseline_complete.json) | 机器可读格式 |
| 深度指标 | [logs/depth_metrics_complete.json](../logs/depth_metrics_complete.json) | 详细深度评测 |
| VisLoc指南 | [docs/DUSt3R_7Scenes_Visloc_复现指南.md](DUSt3R_7Scenes_Visloc_复现指南.md) | 完整复现步骤 |
| 实验日志 | [outputs/visloc_7scenes_experiment_log.md](../outputs/visloc_7scenes_experiment_log.md) | 详细实验记录 |

---

## ✅ 验证状态

| 检查项 | 状态 | 说明 |
|--------|:----:|------|
| VisLoc达到论文水平 | ✅ | 1.85cm vs 论文2cm |
| 深度指标完整(8项) | ✅ | 含absrel, sqrel, rmse, rmse_log, δ1/2/3, si_log |
| 延迟测量完整 | ✅ | 含min/p50/p95/max/mean/std |
| 显存测量完整 | ✅ | 含baseline/peak/delta |
| 模型参数统计 | ✅ | 含total/encoder/decoder |

---

## 🔜 下一步：P/Q/K 轻量化

Baseline已完整，可以开始轻量化实验：

| 方向 | 说明 | 目标 |
|------|------|------|
| **P (Pruning)** | 结构化剪枝 | 减少参数50%+ |
| **Q (Quantization)** | INT8/INT4量化 | 减少延迟2-4× |
| **K (Knowledge Distill)** | 知识蒸馏 | 训练小模型 |

---

*文档生成时间: 2025-12-26*
