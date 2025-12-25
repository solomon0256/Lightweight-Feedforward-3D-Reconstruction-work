# Baseline 测试完整指标清单

> **目的**：建立一个"可复现、可对比、可扩展"的参考坐标系  
> **原则**：Baseline 对比的是"模型之间"，不是"机器之间"

---

## 一、模型本体指标（与硬件无关，永远有效）

| 指标 | 单位 | 说明 | 必须 |
|------|------|------|:----:|
| **params_total** | M | 总参数量 | ✅ |
| **params_encoder** | M | Encoder 参数量 | ✅ |
| **params_decoder** | M | Decoder 参数量 | ✅ |
| **flops** | G | 计算量（指定输入分辨率） | ✅ |
| **macs** | G | 乘加操作数 | 可选 |
| **size_MB** | MB | 模型文件大小 | ✅ |

### 模型结构信息（必须记录）
- 输入形式：#views、resolution、是否 pair-wise
- 是否 feed-forward（明确强调）
- 是否需要后处理（对齐、融合、优化）

---

## 二、显存与内存指标

| 指标 | 单位 | 说明 | 必须 |
|------|------|------|:----:|
| **vram_peak** | GB | 峰值显存（forward-only, BS=1） | ✅ |
| **vram_fp16** | GB | FP16 模式峰值显存 | ✅ |
| **activation_memory** | GB | 激活值内存 | 可选 |

---

## 三、推理性能指标

| 指标 | 单位 | 说明 | 必须 |
|------|------|------|:----:|
| **t_pair_p50** | ms | 单对图推理时延（中位数） | ✅ |
| **t_pair_p95** | ms | 单对图推理时延（95分位） | ✅ |
| **t_pair_mean** | ms | 单对图推理时延（平均） | ✅ |
| **t_pair_std** | ms | 单对图推理时延（标准差） | ✅ |
| **t_scene** | s | 整个场景耗时 | ✅ |
| **pairs_per_sec** | pair/s | 吞吐量 | ✅ |
| **fps** | frame/s | 帧率（如适用） | 可选 |

### 测量要求
- batch size = 1
- warm-up ≥ 10 次
- 测量次数 ≥ 100 次
- 记录是否开启 cudnn.benchmark

---

## 四、精度/质量指标

### 4.1 DUSt3R 官方核心指标（必须测）
| 指标 | 说明 | 来源 | 必须 |
|------|------|------|:----:|
| **L21** | 3D点欧几里得距离 (官方训练损失) | DUSt3R 官方 | ✅ |
| **Regr3D** | 尺度不变的 3D 回归误差 | DUSt3R 官方 | ✅ |
| **confidence** | 预测置信度 | DUSt3R 官方 | ✅ |
| **reproj_px** | 重投影像素误差 | DUSt3R 官方 | ✅ |

### 4.2 位姿估计指标（DUSt3R visloc 任务）
| 指标 | 说明 | 必须 |
|------|------|:----:|
| **pose_error** | 位姿平移误差 (米) | ✅ |
| **angular_error** | 位姿旋转误差 (度) | ✅ |
| **median_pos_error** | 位姿误差中位数 | ✅ |
| **median_angular_error** | 角度误差中位数 | ✅ |
| **acc@0.1m,1°** | 0.1米+1度内的准确率 | ✅ |
| **acc@0.25m,2°** | 0.25米+2度内的准确率 | ✅ |
| **acc@0.5m,5°** | 0.5米+5度内的准确率 | ✅ |
| **acc@5m,10°** | 5米+10度内的准确率 | ✅ |

### 4.3 深度/几何类（通用指标）
| 指标 | 说明 | 必须 |
|------|------|:----:|
| **absrel** | 相对深度误差 | ✅ |
| **sqrel** | 平方相对误差 | ✅ |
| **rmse** | 均方根误差 | ✅ |
| **rmse_log** | 对数均方根误差 | ✅ |
| **delta1** | 阈值正确率 δ<1.25 | ✅ |
| **delta2** | 阈值正确率 δ<1.25² | ✅ |
| **delta3** | 阈值正确率 δ<1.25³ | ✅ |
| **si_log** | 尺度不变对数误差 | 可选 |

### 4.4 点云/3D 一致性
| 指标 | 说明 | 必须 |
|------|------|:----:|
| **chamfer** | Chamfer Distance | ✅ |
| **chamfer_L1** | Chamfer L1 距离 | ✅ |
| **chamfer_L2** | Chamfer L2 距离 | ✅ |
| **f_score** | F-Score (阈值=0.01) | ✅ |
| **point_to_plane** | 点到平面误差 | ✅ |
| **normal_consistency** | 法向一致性 | 可选 |

### 4.5 场景级别（多视图）
| 指标 | 说明 | 必须 |
|------|------|:----:|
| **completeness** | 重建完整度 | ✅ |
| **accuracy** | 重建精度 | ✅ |
| **coverage** | 覆盖率 | ✅ |
| **num_matches** | 匹配点数量 | ✅ |

### 4.6 匹配质量
| 指标 | 说明 | 必须 |
|------|------|:----:|
| **match_precision** | 匹配精度 | ✅ |
| **match_recall** | 匹配召回率 | ✅ |
| **inlier_ratio** | 内点比例 | ✅ |
| **epipolar_error** | 极线误差 | 可选 |

---

## 五、能耗指标

| 指标 | 单位 | 说明 | 必须 |
|------|------|------|:----:|
| **gpu_power_avg** | W | GPU 平均功耗 | ✅ |
| **gpu_power_peak** | W | GPU 峰值功耗 | ✅ |
| **energy_per_frame** | J | 每帧能耗 | ✅ |
| **energy_per_pair** | J | 每对图能耗 | ✅ |
| **gpu_utilization** | % | GPU 利用率 | ✅ |
| **memory_bandwidth** | GB/s | 内存带宽利用率 | 可选 |
| **thermal_throttling** | bool | 是否发生热降频 | ✅ |

---

## 六、边缘设备指标（Jetson 等）

| 指标 | 单位 | 说明 | 必须 |
|------|------|------|:----:|
| **jetson_power** | W | Jetson 功耗 | 可选 |
| **jetson_fps** | frame/s | Jetson 帧率 | 可选 |
| **jetson_latency** | ms | Jetson 时延 | 可选 |
| **tensorrt_speedup** | x | TensorRT 加速比 | 可选 |
| **onnx_compatible** | bool | ONNX 兼容性 | ✅ |

---

## 七、复现环境信息（极其重要）

### 硬件
| 项目 | 示例 | 必须 |
|------|------|:----:|
| **GPU 型号** | NVIDIA RTX 3060 Laptop | ✅ |
| **GPU 显存** | 6 GB | ✅ |
| **GPU 驱动版本** | 537.42 | ✅ |
| **CPU 型号** | Intel i7-11800H | ✅ |
| **CPU 核心数** | 8核16线程 | ✅ |
| **RAM** | 32 GB | ✅ |
| **RAM 频率** | DDR4-3200 | 可选 |
| **存储类型** | NVMe SSD | ✅ |

### 软件
| 项目 | 示例 | 必须 |
|------|------|:----:|
| **OS** | Windows 11 / Ubuntu 22.04 | ✅ |
| **Python** | 3.10.x | ✅ |
| **PyTorch** | 2.6.0+cu124 | ✅ |
| **CUDA** | 12.4 | ✅ |
| **cuDNN** | 8.x | ✅ |
| **TensorRT** | 8.x (如使用) | 可选 |
| **ONNX Runtime** | 1.x (如使用) | 可选 |
| **NumPy** | 1.x | ✅ |
| **OpenCV** | 4.x | ✅ |

### 实验设置
| 项目 | 示例 | 必须 |
|------|------|:----:|
| **输入分辨率** | 512×384 | ✅ |
| **batch size** | 1 | ✅ |
| **precision** | FP32 / FP16 | ✅ |
| **pair_graph** | 邻近 K=4 | ✅ |
| **cudnn.benchmark** | True/False | ✅ |
| **cudnn.deterministic** | True/False | ✅ |
| **torch.backends.cuda.matmul.allow_tf32** | True/False | ✅ |
| **random_seed** | 42 | ✅ |

### 数据集信息
| 项目 | 示例 | 必须 |
|------|------|:----:|
| **评测数据集** | CO3Dv2 / ScanNet++ | ✅ |
| **测试集大小** | 1000 pairs | ✅ |
| **校准集大小** | 512 张 | ✅ |

### 版本控制
| 项目 | 说明 | 必须 |
|------|------|:----:|
| **commit hash** | Git 提交哈希 | ✅ |
| **DUSt3R 版本** | commit hash | ✅ |
| **测试日期** | YYYY-MM-DD | ✅ |
| **测试时间** | HH:MM:SS | ✅ |

---

## 八、成功阈值（后续轻量化对比基准）

| 指标 | 阈值 | 说明 |
|------|------|------|
| 精度跌幅（vs Teacher） | ≤ 1.5% | 主质量指标 |
| 速度提升（vs Student FP32） | ≥ 50% | t_pair p50 |
| Q-only 精度跌幅 | ≤ 2.0% | 量化单独允许稍大 |
| P-only 精度跌幅 | ≤ 3.0% | 剪枝单独允许稍大 |
| 模型体积降低 | ≥ 25% | P-only 目标 |
| 显存降低 | ≥ 30% | 轻量化目标 |

---

## 九、输出文件格式

### 必须输出
- `logs/teacher_eval.json` — 原始测试日志
- `reports/baseline_report.md` — 可读报告
- `reports/result_table.xlsx` — 表格汇总
- `reports/result_table.csv` — CSV 格式
- `reports/plots/` — 图表目录

### JSON 日志字段（统一格式）
```json
{
  "exp_id": "baseline_teacher_v1",
  "model": "DUSt3R_ViTLarge_BaseDecoder_512_dpt",
  "datetime": "2025-12-25T10:00:00",
  "commit": "abc1234",
  "dust3r_commit": "xyz5678",
  
  "model_info": {
    "params_total_M": 571.2,
    "params_encoder_M": 304.0,
    "params_decoder_M": 267.2,
    "flops_G": 123.4,
    "macs_G": 61.7,
    "size_MB": 2180
  },
  
  "resources": {
    "vram_peak_GB": 2.77,
    "vram_fp16_GB": 1.5,
    "activation_memory_GB": 0.8
  },
  
  "latency": {
    "t_pair_p50_ms": 45.2,
    "t_pair_p95_ms": 48.1,
    "t_pair_mean_ms": 45.5,
    "t_pair_std_ms": 2.3,
    "t_pair_min_ms": 42.0,
    "t_pair_max_ms": 55.0,
    "t_scene_s": 12.5,
    "pairs_per_sec": 22.1,
    "warmup_runs": 10,
    "measure_runs": 100
  },
  
  "quality_dust3r_official": {
    "L21": 0.025,
    "Regr3D": 0.032,
    "confidence_mean": 0.85,
    "reproj_px": 1.23
  },
  
  "quality_pose": {
    "pose_error_median_m": 0.15,
    "angular_error_median_deg": 2.3,
    "acc_0.1m_1deg": 45.2,
    "acc_0.25m_2deg": 68.5,
    "acc_0.5m_5deg": 85.3,
    "acc_5m_10deg": 95.1
  },
  
  "quality_depth": {
    "absrel": 0.089,
    "sqrel": 0.012,
    "rmse": 0.312,
    "rmse_log": 0.145,
    "delta1": 0.945,
    "delta2": 0.982,
    "delta3": 0.995,
    "si_log": 0.132
  },
  
  "quality_pointcloud": {
    "chamfer": 0.025,
    "chamfer_L1": 0.023,
    "chamfer_L2": 0.028,
    "f_score": 0.89,
    "point_to_plane": 0.018,
    "normal_consistency": 0.92
  },
  
  "quality_scene": {
    "completeness": 0.88,
    "accuracy": 0.92,
    "coverage": 0.85,
    "num_matches": 12500
  },
  
  "quality_matching": {
    "match_precision": 0.91,
    "match_recall": 0.87,
    "inlier_ratio": 0.78,
    "epipolar_error": 1.5
  },
  
  "energy": {
    "gpu_power_avg_W": 120,
    "gpu_power_peak_W": 150,
    "energy_per_pair_J": 5.4,
    "gpu_utilization_pct": 95,
    "thermal_throttling": false
  },
  
  "environment": {
    "gpu": "NVIDIA RTX 3060 Laptop GPU",
    "gpu_memory_GB": 6,
    "gpu_driver": "537.42",
    "cpu": "Intel i7-11800H",
    "cpu_cores": 8,
    "ram_GB": 32,
    "os": "Windows 11",
    "python": "3.10.x",
    "pytorch": "2.6.0+cu124",
    "cuda": "12.4",
    "cudnn": "8.x",
    "numpy": "1.24.0",
    "opencv": "4.8.0"
  },
  
  "settings": {
    "input_resolution": [512, 384],
    "batch_size": 1,
    "precision": "FP32",
    "pair_graph": "neighbor_K4",
    "cudnn_benchmark": true,
    "cudnn_deterministic": false,
    "allow_tf32": false,
    "random_seed": 42
  },
  
  "dataset": {
    "name": "CO3Dv2",
    "split": "test",
    "num_pairs": 1000,
    "calibration_size": 512
  }
}
```

---

## 十、Checklist（测试前检查）

### 环境准备
- [ ] GPU 型号固定，后续所有实验用同一台
- [ ] 输入分辨率、batch size、pair_graph 固定
- [ ] 随机种子固定
- [ ] cudnn.benchmark 设置一致
- [ ] 环境信息完整记录（硬件+软件）

### 数据准备
- [ ] 评测数据集准备完成
- [ ] 校准集准备完成（≥512张）
- [ ] 数据集路径配置正确

### 测试脚本
- [ ] 能输出所有质量指标
- [ ] 能输出所有效率指标
- [ ] 能输出所有资源指标
- [ ] 日志格式符合统一 JSON schema
- [ ] 记录 commit hash 和测试日期

### 测试执行
- [ ] warm-up 次数 ≥ 10
- [ ] 测量次数 ≥ 100
- [ ] 显存清理后再测
- [ ] 无其他 GPU 进程干扰

### 输出检查
- [ ] JSON 日志完整
- [ ] 报告文档生成
- [ ] 图表生成（如需要）

---

## 十一、指标汇总表

### 总计指标数量

| 类别 | 必须 | 可选 | 合计 |
|------|------|------|------|
| 模型本体 | 5 | 1 | 6 |
| 显存内存 | 2 | 1 | 3 |
| 推理性能 | 6 | 1 | 7 |
| DUSt3R官方 | 4 | 0 | 4 |
| 位姿估计 | 8 | 0 | 8 |
| 深度几何 | 7 | 1 | 8 |
| 点云3D | 5 | 1 | 6 |
| 场景级别 | 4 | 0 | 4 |
| 匹配质量 | 3 | 1 | 4 |
| 能耗 | 5 | 1 | 6 |
| 边缘设备 | 1 | 4 | 5 |
| 环境信息 | 25+ | 5+ | 30+ |
| **合计** | **75+** | **16+** | **91+** |

---

## 十二、关键原则

> **Baseline 的目标不是"跑得快"，而是建立一个"可复现、可对比、可扩展"的参考坐标系**

1. ✅ 必须统一测试平台（GPU + 软件栈）
2. ❌ 不需要一开始就在边缘设备上测
3. ✅ 必须把"与硬件强相关"和"与模型本身相关"的指标分开记录
4. ✅ Baseline 现在测一次，后面所有轻量化方法都只在这个 baseline 上对比
5. ❌ 不要 baseline 用 A100，轻量化用 RTX3060（混着报 latency 无效）
6. ✅ DUSt3R 官方指标（L21, Regr3D, pose_error）必须测
7. ✅ 所有指标用统一的 JSON schema 记录

---

*最后更新: 2025-12-25*
