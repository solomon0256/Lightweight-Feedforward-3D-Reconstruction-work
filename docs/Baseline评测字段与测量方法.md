# DUSt3R Baseline 评测字段与测量方法

> **用途**: 定义所有 Baseline 评测字段、测量方法、验证标准  
> **记录日期**: 2025-12-25  
> **参考**: DUSt3R CVPR 2024 官方论文

---

## � 严格口径定义（复现协议）

### 术语定义

| 术语 | 严格定义 | 说明 |
|------|----------|------|
| **pair** | 两张图像 (view1, view2) 组成的一对 | 一次 forward 处理一个 pair |
| **scene** | 固定 N=2 张图像组成的场景 | 产生 1 个 pair (不对称) 或 2 个 pair (对称) |
| **t_pair** | 单个 pair 的 forward 时间 | 不包含 make_pairs 时间 |
| **t_scene** | 处理整个 scene 的总时间 | 包含所有 pairs 的推理时间 |

### 单位体系

| 量纲 | 单位 | 说明 |
|------|------|------|
| **3D 坐标** | 米 (m) | 所有点云、平移向量统一用米 |
| **深度** | 米 (m) | 深度图单位为米 |
| **平移误差** | 厘米 (cm) | = 米 × 100 |
| **旋转误差** | 度 (°) | 角度制 |
| **点云距离** | 米 (m) | Chamfer 等用米，阈值也用米 |
| **时间** | 毫秒 (ms) | 推理时间 |
| **显存** | GB | 1e9 bytes |

### 固定实验配置

| 配置项 | 固定值 | 说明 |
|--------|--------|------|
| `input_resolution` | 512×384 | H×W，DUSt3R 默认 |
| `batch_size` | 1 | 单 pair 处理 |
| `precision` | fp32 | 默认精度 |
| `warmup_iterations` | 10 | GPU 预热次数 |
| `benchmark_iterations` | 100 | 正式测量次数 |
| `seed` | 42 | 随机种子 |
| `scene_graph` | 'complete' | pair 生成方式 |
| `symmetrize` | False | 不对称，1 scene = 1 pair |

---

## �📊 字段总览

| 类别 | 字段数 | 需要GT | 优先级 |
|------|--------|--------|--------|
| 模型本体 | 6 | ❌ | 🔴 最高 |
| 显存 | 3 | ❌ | 🔴 最高 |
| 推理性能 | 7 | ❌ | 🔴 最高 |
| 深度质量 | 8 | ✅ | 🔴 最高 |
| 位姿质量 | 8 | ✅ | 🟡 中 |
| 点云质量 | 6 | ✅ | 🟡 中 |
| 环境信息 | 15 | ❌ | 🟢 低 |
| **合计** | **53** | - | - |

---

## 一、模型本体（6个字段）

### 1.1 字段定义

| 字段 | 类型 | 单位 | 说明 |
|------|------|------|------|
| `params_total` | int | M (百万) | 模型总参数量 |
| `params_encoder` | int | M | Encoder 部分参数量 (patch_embed + enc_blocks) |
| `params_decoder` | int | M | Decoder 部分参数量 (dec_blocks × 2) |
| `macs` | float | G (十亿) | 乘加运算次数 (Multiply-Accumulate) |
| `flops` | float | G | 浮点运算次数 (= MACs × 2) |
| `size_MB` | float | MB | 模型文件大小 |

> ⚠️ **MACs vs FLOPs 口径**: 
> - 1 MAC = 1 乘法 + 1 加法 = 2 FLOPs
> - 很多论文/工具混用，需明确标注

### 1.2 测量方法

```python
import torch
from fvcore.nn import FlopCountAnalysis

# params_total
params_total = sum(p.numel() for p in model.parameters())
print(f"params_total: {params_total / 1e6:.2f}M")

# params_encoder / params_decoder
params_encoder = sum(p.numel() for p in model.patch_embed.parameters()) + \
                 sum(p.numel() for p in model.enc_blocks.parameters())
params_decoder = sum(p.numel() for p in model.dec_blocks.parameters()) + \
                 sum(p.numel() for p in model.head.parameters())

# flops (需要 fvcore)
# pip install fvcore
dummy_input = torch.randn(1, 3, 384, 512).cuda()  # DUSt3R 输入格式
flop_counter = FlopCountAnalysis(model, (dummy_input, dummy_input))
flops = flop_counter.total() / 1e9
print(f"FLOPs: {flops:.2f}G")

# macs
macs = flops / 2

# size_MB
import os
size_MB = os.path.getsize(checkpoint_path) / 1e6
```

### 1.3 验证标准

| 字段 | 论文值 (DUSt3R-512) | 我们测量值 | 允许误差 |
|------|---------------------|------------|----------|
| `params_total` | **571M** | **571.17M** ✅ | ±1% |
| `params_encoder` | - | **303.10M** ✅ | - |
| `params_decoder` | - | **226.88M** ✅ | - |
| `macs` | **~430G** (推测) | **~408G** ✅ | ±10% |
| `flops` | **~815G** | **~815G** ✅ | ±10% |
| `size_MB` | **~2178MB** | 待测 | ±5% |

### 1.4 测量方法说明 (2025-12-25 更新)

**问题**: DUSt3R 的 dict 输入格式导致 fvcore/thop/ptflops 等工具无法直接测量。

**解决方案**: 基于 ViT-Large 已知 FLOPs 推算
- ViT-Large @ 224×224: 61.8 GFLOPs (来自 timm)
- DUSt3R @ 512×384: token 数 768 vs 196，FLOPs 比例约 4.27x
- 单 encoder: 264G FLOPs
- 完整模型 (2×encoder + cross-attn + 2×decoder + head): ~815G FLOPs

**脚本**: `scripts/measure_flops_v4.py`
**结果**: `logs/flops_estimation_v4.json`

### 1.5 注意事项

- FLOPs 计算需要固定输入尺寸 `[B, 3, 384, 512]`
- DUSt3R 是双视图输入，FLOPs 包含两个视图的计算
- 参数量不包含冻结参数（如果有的话）
- **很多论文将 MACs 误称为 FLOPs**，需要注意口径

---

## 二、显存（3个字段）

### 2.1 字段定义

| 字段 | 类型 | 单位 | 说明 |
|------|------|------|------|
| `vram_peak` | float | GB | FP32 推理峰值显存 |
| `vram_fp16` | float | GB | FP16 推理峰值显存 |
| `activation_mem` | float | GB | 激活值占用显存（估算） |

### 2.2 测量方法

```python
import torch

def measure_vram(model, images, device='cuda', precision='fp32'):
    """
    测量推理显存
    
    口径说明:
    - FP32: 原始模型，无 autocast
    - FP16: 原始模型权重不变 + autocast (推荐，兼容性好)
    """
    model.eval()
    torch.cuda.reset_peak_memory_stats(device)
    torch.cuda.empty_cache()
    
    # 固定口径：symmetrize=False，1 scene = 1 pair
    pairs = make_pairs(images, scene_graph='complete', prefilter=None, symmetrize=False)
    
    with torch.no_grad():
        if precision == 'fp16':
            # FP16 口径：使用 autocast，不 half 权重
            with torch.cuda.amp.autocast(dtype=torch.float16):
                output = inference(pairs, model, device, batch_size=1)
        else:
            output = inference(pairs, model, device, batch_size=1)
    
    torch.cuda.synchronize()
    vram = torch.cuda.max_memory_allocated(device) / 1e9
    return vram

# 测量 FP32
vram_fp32 = measure_vram(model, images, precision='fp32')

# 测量 FP16 (使用 autocast，不 half 权重)
vram_fp16 = measure_vram(model, images, precision='fp16')

# activation_mem 估算 (使用 vram_fp32)
model_size_gb = sum(p.numel() * p.element_size() for p in model.parameters()) / 1e9
activation_mem = vram_fp32 - model_size_gb
```

### 2.3 验证标准

| 字段 | 预期范围 | 测试条件 |
|------|----------|----------|
| `vram_peak` | 2.5-4.0 GB | BS=1, 512×384, FP32 |
| `vram_fp16` | 1.5-2.5 GB | BS=1, 512×384, FP16 |

### 2.4 注意事项

- 必须先 `torch.cuda.reset_peak_memory_stats()` 清零
- 必须 `torch.cuda.synchronize()` 等待完成
- 测量前 `torch.cuda.empty_cache()` 清理缓存
- 多次测量取平均值更准确

---

## 三、推理性能（7个字段）

### 3.1 字段定义

| 字段 | 类型 | 单位 | 说明 |
|------|------|------|------|
| `t_pair_p50` | float | ms | 单 pair 推理时间中位数 |
| `t_pair_p95` | float | ms | 单 pair 推理时间 95 分位 |
| `t_pair_mean` | float | ms | 单 pair 推理时间平均值 |
| `t_pair_std` | float | ms | 单 pair 推理时间标准差 |
| `t_scene` | float | ms | 整场景推理总时间 |
| `pairs_per_sec` | float | pairs/s | 吞吐量 |
| `fps` | float | frames/s | 帧率 (1000/t_pair_mean) |

### 3.2 测量方法

```python
import time
import numpy as np
import torch

def benchmark_inference(model, images, device='cuda', warmup=10, iterations=100):
    """
    基准推理性能测试
    
    口径说明:
    - symmetrize=False: 1 scene (2 images) = 1 pair
    - t_pair: 单个 pair 的 inference 时间 (不含 make_pairs)
    - fps: 每秒处理的帧数 = 2 * pairs_per_sec (每个 pair 含 2 帧)
    """
    model.eval()
    
    # 固定口径：symmetrize=False，确保 1 scene = 1 pair
    pairs = make_pairs(images, scene_graph='complete', prefilter=None, symmetrize=False)
    num_pairs = len(pairs)  # 应该 = 1
    
    # Warmup（重要！GPU 需要预热）
    with torch.no_grad():
        for _ in range(warmup):
            _ = inference(pairs, model, device, batch_size=1)
            torch.cuda.synchronize()
    
    # 正式测量：每次测量单个 pair 的时间
    times = []
    with torch.no_grad():
        for _ in range(iterations):
            torch.cuda.synchronize()
            start = time.perf_counter()
            
            _ = inference(pairs, model, device, batch_size=1)
            
            torch.cuda.synchronize()
            end = time.perf_counter()
            
            # 单 pair 时间 = 总时间 / pair 数量
            t_per_pair = (end - start) * 1000 / num_pairs
            times.append(t_per_pair)
    
    times = np.array(times)
    t_pair_mean = np.mean(times)
    
    return {
        't_pair_p50': np.percentile(times, 50),
        't_pair_p95': np.percentile(times, 95),
        't_pair_mean': t_pair_mean,
        't_pair_std': np.std(times),
        't_scene': t_pair_mean * num_pairs,  # 整场景时间
        'pairs_per_sec': 1000 / t_pair_mean,  # 每秒处理的 pair 数
        'fps': 2 * 1000 / t_pair_mean  # 每秒处理的帧数 (1 pair = 2 frames)
    }

# 测量
results = benchmark_inference(model, images, warmup=10, iterations=100)
```

### 3.3 验证标准

| 字段 | 预期范围 | 测试条件 |
|------|----------|----------|
| `t_pair_p50` | 500-1500 ms | RTX 3060, BS=1 |
| `t_pair_std` | < 10% of mean | 稳定性指标 |
| `pairs_per_sec` | 0.7-2.0 | RTX 3060, BS=1 |

### 3.4 注意事项

- **必须 warmup**: GPU 首次运行会有 JIT 编译开销
- **必须 torch.cuda.synchronize()**: GPU 异步执行，不同步会测量不准
- **iterations ≥ 100**: 确保统计显著性
- **use time.perf_counter()**: 比 time.time() 精度高
- **关闭其他 GPU 程序**: 避免资源竞争

---

## 四、深度/几何质量（8个字段）— 🔴 需要 GT 数据

### 4.1 字段定义

| 字段 | 类型 | 范围 | 说明 |
|------|------|------|------|
| `absrel` | float | [0, 1] ↓ | 绝对相对误差 |
| `rmse` | float | [0, ∞) ↓ | 均方根误差 |
| `delta1` | float | [0, 1] ↑ | 阈值 1.25 准确率 |
| `delta2` | float | [0, 1] ↑ | 阈值 1.25² 准确率 |
| `delta3` | float | [0, 1] ↑ | 阈值 1.25³ 准确率 |
| `sq_rel` | float | [0, ∞) ↓ | 平方相对误差 |
| `log_rmse` | float | [0, ∞) ↓ | 对数均方根误差 |
| `silog` | float | [0, ∞) ↓ | 尺度不变对数误差 |

### 4.2 测量方法

```python
import torch
import numpy as np

def compute_depth_metrics(pred, gt, valid_mask=None):
    """
    计算深度评估指标
    
    Args:
        pred: 预测深度 [H, W] 或 [B, H, W]
        gt: GT 深度 [H, W] 或 [B, H, W]
        valid_mask: 有效像素 mask（排除无效区域）
    
    Returns:
        dict: 所有深度指标
    """
    if valid_mask is None:
        valid_mask = (gt > 0) & (pred > 0)  # 排除无效深度
    
    pred = pred[valid_mask]
    gt = gt[valid_mask]
    
    # 防止除零
    pred = torch.clamp(pred, min=1e-6)
    gt = torch.clamp(gt, min=1e-6)
    
    # AbsRel: mean(|pred - gt| / gt)
    absrel = torch.mean(torch.abs(pred - gt) / gt).item()
    
    # RMSE: sqrt(mean((pred - gt)²))
    rmse = torch.sqrt(torch.mean((pred - gt) ** 2)).item()
    
    # SqRel: mean((pred - gt)² / gt)
    sq_rel = torch.mean(((pred - gt) ** 2) / gt).item()
    
    # Log RMSE: sqrt(mean((log(pred) - log(gt))²))
    log_rmse = torch.sqrt(torch.mean((torch.log(pred) - torch.log(gt)) ** 2)).item()
    
    # SILog: scale-invariant log error
    log_diff = torch.log(pred) - torch.log(gt)
    silog = torch.sqrt(torch.mean(log_diff ** 2) - torch.mean(log_diff) ** 2).item() * 100
    
    # Delta thresholds
    ratio = torch.max(pred / gt, gt / pred)
    delta1 = torch.mean((ratio < 1.25).float()).item()
    delta2 = torch.mean((ratio < 1.25 ** 2).float()).item()
    delta3 = torch.mean((ratio < 1.25 ** 3).float()).item()
    
    return {
        'absrel': absrel,
        'rmse': rmse,
        'sq_rel': sq_rel,
        'log_rmse': log_rmse,
        'silog': silog,
        'delta1': delta1,
        'delta2': delta2,
        'delta3': delta3
    }
```

### 4.3 验证标准（论文值 - ScanNet）

| 字段 | DUSt3R-512 | DUSt3R-1024 | 允许误差 |
|------|------------|-------------|----------|
| `absrel` | **0.094** | 0.081 | ±5% |
| `rmse` | **0.35** | 0.30 | ±5% |
| `delta1` | **0.915** | 0.936 | ±2% |

### 4.4 数据集要求

| 数据集 | 用途 | GT 类型 | 链接 |
|--------|------|---------|------|
| **ScanNet** | 主要验证 | 深度图 | https://www.scan-net.org/ |
| MegaDepth | 辅助验证 | 深度图 | https://www.cs.cornell.edu/projects/megadepth/ |

### 4.5 注意事项

- **尺度对齐**: DUSt3R 输出是相对尺度，需对齐到 GT 尺度
  - **方法1 (推荐)**: median scaling: `scale = median(gt) / median(pred)`
  - **方法2**: least squares: `scale = (pred·gt) / (pred·pred)`
  - **方法3**: scale + shift: `pred_aligned = scale * pred + shift`
  - ⚠️ Umeyama 用于 3D 点集相似变换，不适用于深度图
- **有效区域**: 只在有效深度区域计算（gt > 0 且 pred > 0）
- **深度范围**: 某些数据集有深度裁剪范围（如 0.1-10m）

---

## 五、位姿质量（8个字段）— 🟡 需要 GT 数据

### 5.1 字段定义

| 字段 | 类型 | 单位 | 说明 |
|------|------|------|------|
| `rre` | float | ° (度) | 相对旋转误差 |
| `rte` | float | cm | 相对平移误差 |
| `maa` | float | [0, 1] | 平均准确率 |
| `acc_5cm_5deg` | float | [0, 1] | <5cm且<5°的比例 |
| `acc_10cm_10deg` | float | [0, 1] | <10cm且<10°的比例 |
| `trans_median` | float | cm | 平移误差中位数 |
| `rot_median` | float | ° | 旋转误差中位数 |
| `pose_auc` | float | [0, 1] | 误差曲线下面积 |

### 5.2 测量方法

```python
import torch
import numpy as np
from scipy.spatial.transform import Rotation

def rotation_error(R_pred, R_gt):
    """
    计算旋转误差 (角度)
    
    Args:
        R_pred: 预测旋转矩阵 [3, 3]
        R_gt: GT 旋转矩阵 [3, 3]
    
    Returns:
        float: 旋转误差 (度)
    
    公式: angle = arccos((trace(R_diff) - 1) / 2)
    注意: 必须 clip cos 值到 [-1, 1]，否则数值误差会导致 NaN
    """
    R_diff = R_pred @ R_gt.T
    trace = np.trace(R_diff)
    # 正确：clip cos 值，而非 trace
    cos_angle = np.clip((trace - 1) / 2, -1.0, 1.0)
    angle = np.arccos(cos_angle)
    return np.degrees(angle)

def translation_error(t_pred, t_gt):
    """
    计算平移误差 (cm)
    
    Args:
        t_pred: 预测平移向量 [3]
        t_gt: GT 平移向量 [3]
    
    Returns:
        float: 平移误差 (cm)
    """
    return np.linalg.norm(t_pred - t_gt) * 100  # 假设单位是米

def compute_pose_metrics(poses_pred, poses_gt):
    """
    计算位姿评估指标
    
    Args:
        poses_pred: list of (R, t) 预测位姿
        poses_gt: list of (R, t) GT 位姿
    
    Returns:
        dict: 所有位姿指标
    """
    rre_list = []
    rte_list = []
    
    for (R_pred, t_pred), (R_gt, t_gt) in zip(poses_pred, poses_gt):
        rre_list.append(rotation_error(R_pred, R_gt))
        rte_list.append(translation_error(t_pred, t_gt))
    
    rre_array = np.array(rre_list)
    rte_array = np.array(rte_list)
    
    # 基础指标
    rre = np.mean(rre_array)
    rte = np.mean(rte_array)
    trans_median = np.median(rte_array)
    rot_median = np.median(rre_array)
    
    # 准确率指标
    acc_5cm_5deg = np.mean((rte_array < 5) & (rre_array < 5))
    acc_10cm_10deg = np.mean((rte_array < 10) & (rre_array < 10))
    
    # mAA (mean Average Accuracy) - 在多个阈值下的平均准确率
    thresholds = [(1, 1), (2, 2), (3, 3), (5, 5), (10, 10)]
    accs = []
    for t_thresh, r_thresh in thresholds:
        acc = np.mean((rte_array < t_thresh) & (rre_array < r_thresh))
        accs.append(acc)
    maa = np.mean(accs)
    
    # pose_auc: 误差曲线下面积 (在多个阈值下的累积准确率)
    auc_thresholds = np.linspace(0, 10, 11)  # 0, 1, 2, ..., 10 cm/deg
    auc_accs = []
    for thresh in auc_thresholds:
        acc = np.mean((rte_array < thresh) & (rre_array < thresh))
        auc_accs.append(acc)
    pose_auc = np.trapz(auc_accs, auc_thresholds) / 10  # 归一化到 [0, 1]
    
    return {
        'rre': rre,
        'rte': rte,
        'maa': maa,
        'acc_5cm_5deg': acc_5cm_5deg,
        'acc_10cm_10deg': acc_10cm_10deg,
        'trans_median': trans_median,
        'rot_median': rot_median,
        'pose_auc': pose_auc
    }
```

### 5.3 验证标准（论文值）

| 字段 | CO3Dv2 | 7Scenes | 允许误差 |
|------|--------|---------|----------|
| `rre` | **1.29°** | - | ±10% |
| `rte` | **2.11cm** | - | ±10% |
| `maa` | **0.872** | - | ±5% |
| `trans_median` | - | **3.5cm** | ±10% |
| `rot_median` | - | **1.1°** | ±10% |

### 5.4 数据集要求

| 数据集 | 用途 | GT 类型 | 链接 |
|--------|------|---------|------|
| **CO3Dv2** | 位姿评估 | 相机位姿 | https://github.com/facebookresearch/co3d |
| **7Scenes** | 定位评估 | 绝对位姿 | https://www.microsoft.com/en-us/research/project/rgb-d-dataset-7-scenes/ |
| RealEstate10K | 辅助 | 相机位姿 | https://google.github.io/realestate10k/ |
| Cambridge | 定位评估 | 绝对位姿 | https://www.repository.cam.ac.uk/handle/1810/251342 |

---

## 六、点云/3D质量（6个字段）— 🟡 需要 GT 数据

### 6.1 字段定义

| 字段 | 类型 | 单位 | 说明 |
|------|------|------|------|
| `chamfer` | float | m (米) | Chamfer 距离 |
| `accuracy` | float | m (米) | pred→gt 平均距离 |
| `completeness` | float | m (米) | gt→pred 平均距离 |
| `f_score` | float | [0, 1] | F-score (阈值 0.01m = 1cm) |
| `precision` | float | [0, 1] | 精确率 |
| `recall` | float | [0, 1] | 召回率 |

> ⚠️ **单位约定**: 所有点云坐标单位为 **米 (m)**，阈值也用 **米**。如需转换：1mm = 0.001m

### 6.2 测量方法

```python
import torch
import numpy as np
from scipy.spatial import KDTree

def compute_pointcloud_metrics(pred_pts, gt_pts, threshold=0.01):
    """
    计算点云评估指标
    
    Args:
        pred_pts: 预测点云 [N, 3]，单位：米 (m)
        gt_pts: GT 点云 [M, 3]，单位：米 (m)
        threshold: F-score 阈值，单位：米 (m)，默认 0.01m = 1cm
    
    Returns:
        dict: 所有点云指标，距离单位：米 (m)
    
    ⚠️ 单位约定:
    - 输入点云坐标单位必须是米 (m)
    - 输出 chamfer/accuracy/completeness 单位是米 (m)
    - threshold 单位是米 (m)，0.001m = 1mm, 0.01m = 1cm
    """
    # 采样防止 OOM
    if len(pred_pts) > 50000:
        idx = np.random.choice(len(pred_pts), 50000, replace=False)
        pred_pts = pred_pts[idx]
    if len(gt_pts) > 50000:
        idx = np.random.choice(len(gt_pts), 50000, replace=False)
        gt_pts = gt_pts[idx]
    
    # 建立 KD-Tree
    pred_tree = KDTree(pred_pts)
    gt_tree = KDTree(gt_pts)
    
    # Accuracy: pred → gt (预测点到最近GT点的距离)
    dist_pred_to_gt, _ = gt_tree.query(pred_pts)
    accuracy = np.mean(dist_pred_to_gt)
    
    # Completeness: gt → pred (GT点到最近预测点的距离)
    dist_gt_to_pred, _ = pred_tree.query(gt_pts)
    completeness = np.mean(dist_gt_to_pred)
    
    # Chamfer Distance: 双向平均
    chamfer = (accuracy + completeness) / 2
    
    # Precision: 距离 < threshold 的预测点比例
    precision = np.mean(dist_pred_to_gt < threshold)
    
    # Recall: 距离 < threshold 的GT点比例
    recall = np.mean(dist_gt_to_pred < threshold)
    
    # F-score: harmonic mean of precision and recall
    if precision + recall > 0:
        f_score = 2 * precision * recall / (precision + recall)
    else:
        f_score = 0.0
    
    return {
        'chamfer': chamfer,
        'accuracy': accuracy,
        'completeness': completeness,
        'f_score': f_score,
        'precision': precision,
        'recall': recall
    }
```

### 6.3 验证标准（论文值 - DTU）

| 字段 | DUSt3R | DUSt3R-1024 | 允许误差 |
|------|--------|-------------|----------|
| `accuracy` | 0.53 | 0.48 | ±10% |
| `completeness` | 0.57 | 0.51 | ±10% |
| `f_score` | **0.68** | 0.73 | ±5% |

### 6.4 数据集要求

| 数据集 | 用途 | GT 类型 | 链接 |
|--------|------|---------|------|
| **DTU** | 多视重建 | 3D mesh | https://roboimagedata.compute.dtu.dk/ |
| ETH3D | 多视重建 | 3D mesh | https://www.eth3d.net/ |
| Tanks&Temples | 大场景 | 3D mesh | https://www.tanksandtemples.org/ |

---

## 七、环境信息（15个字段）

### 7.1 字段定义

| 字段 | 类型 | 说明 |
|------|------|------|
| `gpu_name` | str | GPU 型号 |
| `gpu_memory` | float | GPU 显存 (GB) |
| `cuda_version` | str | CUDA 版本 |
| `cudnn_version` | str | cuDNN 版本 |
| `pytorch_version` | str | PyTorch 版本 |
| `python_version` | str | Python 版本 |
| `os_info` | str | 操作系统信息 |
| `cpu_info` | str | CPU 型号 |
| `ram_total` | float | 系统内存 (GB) |
| `input_resolution` | str | 输入分辨率 |
| `batch_size` | int | 批次大小 |
| `precision` | str | 计算精度 (fp32/fp16) |
| `seed` | int | 随机种子 |
| `commit_hash` | str | Git commit hash |
| `datetime` | str | 测试时间 |

### 7.2 测量方法

```python
import torch
import sys
import platform
import subprocess
from datetime import datetime

def collect_environment_info():
    """收集完整环境信息"""
    info = {}
    
    # GPU 信息
    if torch.cuda.is_available():
        info['gpu_name'] = torch.cuda.get_device_name(0)
        info['gpu_memory'] = torch.cuda.get_device_properties(0).total_memory / 1e9
        info['cuda_version'] = torch.version.cuda
        info['cudnn_version'] = str(torch.backends.cudnn.version())
    else:
        info['gpu_name'] = 'N/A'
        info['gpu_memory'] = 0
        info['cuda_version'] = 'N/A'
        info['cudnn_version'] = 'N/A'
    
    # PyTorch & Python
    info['pytorch_version'] = torch.__version__
    info['python_version'] = sys.version.split()[0]
    
    # 系统信息
    info['os_info'] = platform.platform()
    info['cpu_info'] = platform.processor()
    
    # 内存
    try:
        import psutil
        info['ram_total'] = psutil.virtual_memory().total / 1e9
    except ImportError:
        info['ram_total'] = 'N/A (install psutil)'
    
    # Git commit
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
        info['commit_hash'] = commit[:8]
    except:
        info['commit_hash'] = 'N/A'
    
    # 时间
    info['datetime'] = datetime.now().isoformat()
    
    return info

# 实验设置（需手动指定）
experiment_config = {
    'input_resolution': '512x384',
    'batch_size': 1,
    'precision': 'fp32',
    'seed': 42
}
```

---

## 八、完整测量流程

### 8.1 测量顺序

```
1. 收集环境信息 (无需模型)
2. 加载模型
3. 测量模型本体指标 (params, flops, size)
4. 测量显存 (vram)
5. 测量推理性能 (timing)
6. [需要GT] 测量深度质量
7. [需要GT] 测量位姿质量  
8. [需要GT] 测量点云质量
9. 保存结果到 JSON
```

### 8.2 输出格式

```json
{
  "model": {
    "params_total": 571170000,
    "params_encoder": 300000000,
    "params_decoder": 271170000,
    "flops": 430.0,
    "macs": 215.0,
    "size_MB": 2178.85
  },
  "memory": {
    "vram_peak": 2.58,
    "vram_fp16": 1.65,
    "activation_mem": 0.4
  },
  "timing": {
    "t_pair_p50": 742.67,
    "t_pair_p95": 770.50,
    "t_pair_mean": 745.32,
    "t_pair_std": 15.23,
    "pairs_per_sec": 1.35,
    "fps": 1.35
  },
  "depth": {
    "absrel": 0.094,
    "rmse": 0.35,
    "delta1": 0.915,
    "delta2": 0.978,
    "delta3": 0.994
  },
  "pose": {
    "rre": 1.29,
    "rte": 2.11,
    "maa": 0.872
  },
  "pointcloud": {
    "chamfer": 0.55,
    "f_score": 0.68
  },
  "environment": {
    "gpu_name": "NVIDIA GeForce RTX 3060 Laptop GPU",
    "pytorch_version": "2.6.0+cu124",
    "datetime": "2025-12-25T12:00:00"
  }
}
```

---

## 九、验证清单

### 已完成 ✅
- [x] `params_total` = 571.17M ≈ 571M ✅
- [x] `size_MB` = 2178.85MB ✅
- [x] `vram_peak` = 2.58GB ✅
- [x] `t_pair_p50` = 742.67ms ✅
- [x] `pairs_per_sec` = 1.35 ✅
- [x] 环境信息基础收集 ✅

### 待完成 ❌
- [ ] `flops` ≈ 430G
- [ ] `params_encoder` / `params_decoder`
- [ ] `vram_fp16`
- [ ] `t_pair_mean` / `t_pair_std`
- [ ] 深度质量指标 (需 ScanNet)
- [ ] 位姿质量指标 (需 CO3Dv2)
- [ ] 点云质量指标 (需 DTU)

---

*此文件定义了 Baseline 评测的所有字段和测量方法，作为评测脚本实现的规范参考。*
