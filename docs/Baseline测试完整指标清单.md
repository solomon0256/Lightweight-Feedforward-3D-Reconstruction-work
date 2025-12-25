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

## 十三、训练过程记录（蒸馏/剪枝/量化时）

### 训练日志
| 项目 | 说明 | 必须 |
|------|------|:----:|
| **epoch** | 当前 epoch | ✅ |
| **step** | 当前 step | ✅ |
| **train_loss** | 训练损失 | ✅ |
| **val_loss** | 验证损失 | ✅ |
| **learning_rate** | 当前学习率 | ✅ |
| **grad_norm** | 梯度范数 | ✅ |
| **batch_time** | 每 batch 时间 | ✅ |
| **data_time** | 数据加载时间 | ✅ |
| **memory_used** | 显存占用 | ✅ |

### 蒸馏专用
| 项目 | 说明 | 必须 |
|------|------|:----:|
| **L_task** | 任务损失 | ✅ |
| **L_kd** | KL 散度损失 | ✅ |
| **L_fd** | 特征蒸馏损失 | ✅ |
| **temperature** | 蒸馏温度 T | ✅ |
| **alpha/beta/gamma** | 损失权重 | ✅ |

### 剪枝专用
| 项目 | 说明 | 必须 |
|------|------|:----:|
| **sparsity** | 当前稀疏度 | ✅ |
| **pruned_params** | 已剪枝参数量 | ✅ |
| **pruned_flops** | 已剪枝 FLOPs | ✅ |
| **importance_scores** | 重要性分数分布 | ✅ |

### 量化专用
| 项目 | 说明 | 必须 |
|------|------|:----:|
| **quant_loss** | 量化损失 | ✅ |
| **scale_factors** | 量化缩放因子 | ✅ |
| **zero_points** | 量化零点 | ✅ |
| **calibration_stats** | 校准统计 | ✅ |

### 检查点记录
| 项目 | 说明 | 必须 |
|------|------|:----:|
| **best_ckpt** | 最佳检查点路径 | ✅ |
| **last_ckpt** | 最新检查点路径 | ✅ |
| **best_metric** | 最佳指标值 | ✅ |
| **best_epoch** | 最佳 epoch | ✅ |
| **early_stop_counter** | 早停计数器 | ✅ |

---

## 十四、超参数记录

### 通用超参数
| 项目 | 示例 | 必须 |
|------|------|:----:|
| **optimizer** | AdamW | ✅ |
| **lr_init** | 1e-4 | ✅ |
| **lr_min** | 1e-6 | ✅ |
| **lr_scheduler** | cosine | ✅ |
| **warmup_epochs** | 5 | ✅ |
| **weight_decay** | 0.01 | ✅ |
| **batch_size** | 16 | ✅ |
| **accum_iter** | 4 | ✅ |
| **max_epochs** | 100 | ✅ |
| **clip_grad** | 1.0 | ✅ |

### 蒸馏超参数
| 项目 | 示例 | 必须 |
|------|------|:----:|
| **T (temperature)** | 3.0 | ✅ |
| **alpha** | 0.5 | ✅ |
| **beta (KL weight)** | 0.7 | ✅ |
| **gamma (FD weight)** | 0.1 | ✅ |
| **student_arch** | ViT-S | ✅ |
| **teacher_frozen** | True | ✅ |

### 剪枝超参数
| 项目 | 示例 | 必须 |
|------|------|:----:|
| **rho (target sparsity)** | 0.3 | ✅ |
| **pruning_method** | L1 | ✅ |
| **pruning_schedule** | gradual | ✅ |
| **pruning_start_epoch** | 5 | ✅ |
| **pruning_end_epoch** | 50 | ✅ |
| **finetune_epochs** | 15 | ✅ |

### 量化超参数
| 项目 | 示例 | 必须 |
|------|------|:----:|
| **bits_weight** | 8 | ✅ |
| **bits_activation** | 8 | ✅ |
| **quant_mode** | PTQ/QAT | ✅ |
| **calibration_size** | 512 | ✅ |
| **keep_list** | [LN, Softmax] | ✅ |
| **symmetric** | True | ✅ |
| **per_channel** | True | ✅ |

---

## 十五、实验元数据

### 实验标识
| 项目 | 示例 | 必须 |
|------|------|:----:|
| **exp_id** | K-only_v1 | ✅ |
| **exp_name** | 蒸馏实验1 | ✅ |
| **combo** | K-only / P→K / K→Q | ✅ |
| **run_id** | run_001 | ✅ |
| **parent_exp** | baseline_v1 | ✅ |

### 时间记录
| 项目 | 示例 | 必须 |
|------|------|:----:|
| **start_time** | 2025-12-25 10:00:00 | ✅ |
| **end_time** | 2025-12-25 18:30:00 | ✅ |
| **total_time_h** | 8.5 | ✅ |
| **gpu_hours** | 8.5 | ✅ |

### 成本记录
| 项目 | 示例 | 必须 |
|------|------|:----:|
| **gpu_type** | H100 | ✅ |
| **gpu_price_per_h** | $6.88 | ✅ |
| **total_cost** | $58.48 | ✅ |
| **cloud_provider** | Lambda Labs | ✅ |

### 状态记录
| 项目 | 示例 | 必须 |
|------|------|:----:|
| **status** | completed / failed / running | ✅ |
| **exit_code** | 0 | ✅ |
| **error_msg** | (如有) | ✅ |
| **notes** | 备注 | ✅ |

---

## 十六、可视化输出

### 训练曲线
| 项目 | 格式 | 必须 |
|------|------|:----:|
| **loss_curve.png** | PNG | ✅ |
| **lr_curve.png** | PNG | ✅ |
| **metric_curve.png** | PNG | ✅ |
| **grad_norm_curve.png** | PNG | ✅ |
| **tensorboard_logs/** | TensorBoard | ✅ |
| **wandb_logs/** | W&B | 可选 |

### 结果可视化
| 项目 | 格式 | 必须 |
|------|------|:----:|
| **pointcloud_vis.ply** | PLY | ✅ |
| **depth_vis.png** | PNG | ✅ |
| **match_vis.png** | PNG | ✅ |
| **error_heatmap.png** | PNG | ✅ |
| **confidence_vis.png** | PNG | ✅ |

### 对比图
| 项目 | 格式 | 必须 |
|------|------|:----:|
| **teacher_vs_student.png** | PNG | ✅ |
| **before_after_prune.png** | PNG | ✅ |
| **fp32_vs_int8.png** | PNG | ✅ |
| **tradeoff_curve.png** | PNG | ✅ |

---

## 十七、失败与调试记录

### 错误日志
| 项目 | 说明 | 必须 |
|------|------|:----:|
| **error_type** | OOM / NaN / Diverge | ✅ |
| **error_msg** | 完整错误信息 | ✅ |
| **error_traceback** | 堆栈信息 | ✅ |
| **error_epoch** | 出错 epoch | ✅ |
| **error_step** | 出错 step | ✅ |

### 调试信息
| 项目 | 说明 | 必须 |
|------|------|:----:|
| **gpu_memory_snapshot** | 显存快照 | ✅ |
| **nan_check** | NaN 检测结果 | ✅ |
| **gradient_overflow** | 梯度溢出检测 | ✅ |
| **input_stats** | 输入数据统计 | ✅ |
| **output_stats** | 输出数据统计 | ✅ |

### 恢复信息
| 项目 | 说明 | 必须 |
|------|------|:----:|
| **resume_from** | 恢复检查点 | ✅ |
| **resume_epoch** | 恢复 epoch | ✅ |
| **retry_count** | 重试次数 | ✅ |

---

## 十八、数据集详细信息

### 训练数据
| 项目 | 示例 | 必须 |
|------|------|:----:|
| **train_dataset** | CO3Dv2 | ✅ |
| **train_split** | train | ✅ |
| **train_size** | 50000 pairs | ✅ |
| **train_resolution** | 512×384 | ✅ |
| **augmentation** | ColorJitter, RandomCrop | ✅ |

### 验证数据
| 项目 | 示例 | 必须 |
|------|------|:----:|
| **val_dataset** | CO3Dv2 | ✅ |
| **val_split** | val | ✅ |
| **val_size** | 5000 pairs | ✅ |
| **val_frequency** | every epoch | ✅ |

### 测试数据
| 项目 | 示例 | 必须 |
|------|------|:----:|
| **test_dataset** | ScanNet++ | ✅ |
| **test_split** | test | ✅ |
| **test_size** | 1000 pairs | ✅ |

### 校准数据（量化用）
| 项目 | 示例 | 必须 |
|------|------|:----:|
| **calib_dataset** | CO3Dv2 subset | ✅ |
| **calib_size** | 512 张 | ✅ |
| **calib_selection** | random | ✅ |

---

## 十九、模型文件输出

### 检查点文件
| 文件 | 说明 | 必须 |
|------|------|:----:|
| **best.pth** | 最佳模型权重 | ✅ |
| **last.pth** | 最新模型权重 | ✅ |
| **optimizer.pth** | 优化器状态 | ✅ |
| **scheduler.pth** | 调度器状态 | ✅ |
| **config.yaml** | 实验配置 | ✅ |

### 导出格式
| 文件 | 说明 | 必须 |
|------|------|:----:|
| **model.onnx** | ONNX 格式 | ✅ |
| **model.engine** | TensorRT 引擎 | 可选 |
| **model_fp16.pth** | FP16 权重 | ✅ |
| **model_int8.pth** | INT8 权重 | 可选 |

### 元数据文件
| 文件 | 说明 | 必须 |
|------|------|:----:|
| **model_card.md** | 模型说明卡 | ✅ |
| **metrics.json** | 指标 JSON | ✅ |
| **hyperparams.json** | 超参数 JSON | ✅ |

---

## 二十、论文材料清单

### 表格数据
| 项目 | 格式 | 必须 |
|------|------|:----:|
| **main_results.csv** | 主实验结果 | ✅ |
| **ablation_results.csv** | 消融实验结果 | ✅ |
| **comparison_results.csv** | 对比实验结果 | ✅ |
| **latex_tables/** | LaTeX 表格 | ✅ |

### 图表
| 项目 | 格式 | 必须 |
|------|------|:----:|
| **figure_*.pdf** | 论文图（矢量） | ✅ |
| **figure_*.png** | 论文图（高清） | ✅ |
| **supplementary/** | 补充材料图 | ✅ |

### 复现材料
| 项目 | 说明 | 必须 |
|------|------|:----:|
| **requirements.txt** | 依赖列表 | ✅ |
| **run_all.sh** | 一键运行脚本 | ✅ |
| **README.md** | 复现说明 | ✅ |
| **pretrained_weights/** | 预训练权重链接 | ✅ |

---

## 二十一、Git 版本记录

### 代码版本
| 项目 | 说明 | 必须 |
|------|------|:----:|
| **main_repo_commit** | 主仓库 commit | ✅ |
| **dust3r_commit** | DUSt3R submodule commit | ✅ |
| **croco_commit** | CroCo submodule commit | ✅ |
| **branch** | 分支名 | ✅ |
| **tag** | 版本标签 | 可选 |

### 变更记录
| 项目 | 说明 | 必须 |
|------|------|:----:|
| **git_diff** | 与基线的代码差异 | ✅ |
| **modified_files** | 修改的文件列表 | ✅ |
| **config_diff** | 配置差异 | ✅ |

---

## 二十二、最终指标统计

### 总记录项数量

| 大类 | 子类数 | 字段数 |
|------|--------|--------|
| 测试指标 | 11 | 91+ |
| 训练记录 | 5 | 30+ |
| 超参数 | 4 | 35+ |
| 实验元数据 | 4 | 20+ |
| 可视化 | 3 | 15+ |
| 失败调试 | 3 | 15+ |
| 数据集 | 4 | 15+ |
| 模型文件 | 3 | 12+ |
| 论文材料 | 3 | 10+ |
| Git版本 | 2 | 8+ |
| **合计** | **42** | **250+** |

---

*最后更新: 2025-12-25*
