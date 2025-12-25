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

### 深度/几何类
| 指标 | 说明 | 必须 |
|------|------|:----:|
| **absrel** | 相对深度误差 | ✅ |
| **rmse** | 均方根误差 | ✅ |
| **delta1** | 阈值正确率 δ<1.25 | ✅ |
| **delta2** | 阈值正确率 δ<1.25² | 可选 |
| **delta3** | 阈值正确率 δ<1.25³ | 可选 |

### 点云/3D 一致性
| 指标 | 说明 | 必须 |
|------|------|:----:|
| **chamfer** | Chamfer Distance | ✅ |
| **reproj_px** | 重投影像素误差 | ✅ |
| **point_to_plane** | 点到平面误差 | 可选 |

### 场景级别（多视图）
| 指标 | 说明 | 必须 |
|------|------|:----:|
| **completeness** | 重建完整度 | 可选 |
| **coverage** | 覆盖率 | 可选 |

---

## 五、能耗指标（现阶段可选，预留接口）

| 指标 | 单位 | 说明 | 必须 |
|------|------|------|:----:|
| **gpu_power** | W | GPU 功耗（nvidia-smi） | 可选 |
| **energy_per_frame** | J | 每帧能耗 | 可选 |
| **energy_per_pair** | J | 每对图能耗 | 可选 |

> ⚠️ 第一篇论文可以不测，但要在 Limitations / Future Work 里说明

---

## 六、复现环境信息（极其重要）

### 硬件
| 项目 | 示例 | 必须 |
|------|------|:----:|
| **GPU 型号** | NVIDIA RTX 3060 Laptop | ✅ |
| **GPU 显存** | 6 GB | ✅ |
| **CPU 型号** | Intel i7-11800H | ✅ |
| **RAM** | 32 GB | ✅ |

### 软件
| 项目 | 示例 | 必须 |
|------|------|:----:|
| **OS** | Windows 11 / Ubuntu 22.04 | ✅ |
| **Python** | 3.10.x | ✅ |
| **PyTorch** | 2.6.0+cu124 | ✅ |
| **CUDA** | 12.4 | ✅ |
| **cuDNN** | 8.x | ✅ |

### 实验设置
| 项目 | 示例 | 必须 |
|------|------|:----:|
| **输入分辨率** | 512×384 | ✅ |
| **batch size** | 1 | ✅ |
| **precision** | FP32 / FP16 | ✅ |
| **pair_graph** | 邻近 K=4 | ✅ |
| **cudnn.benchmark** | True/False | ✅ |

### 版本控制
| 项目 | 说明 | 必须 |
|------|------|:----:|
| **commit hash** | Git 提交哈希 | ✅ |
| **测试日期** | YYYY-MM-DD | ✅ |

---

## 七、成功阈值（后续轻量化对比基准）

| 指标 | 阈值 | 说明 |
|------|------|------|
| 精度跌幅（vs Teacher） | ≤ 1.5% | 主质量指标 |
| 速度提升（vs Student FP32） | ≥ 50% | t_pair p50 |
| Q-only 精度跌幅 | ≤ 2.0% | 量化单独允许稍大 |

---

## 八、输出文件格式

### 必须输出
- `logs/teacher_eval.json` — 原始测试日志
- `reports/baseline_report.md` — 可读报告
- `reports/result_table.xlsx` — 表格汇总

### JSON 日志字段（统一格式）
```json
{
  "exp_id": "baseline_teacher_v1",
  "model": "DUSt3R_ViTLarge_BaseDecoder_512_dpt",
  "datetime": "2025-12-25T10:00:00",
  "commit": "abc1234",
  
  "model_info": {
    "params_total_M": 571.2,
    "params_encoder_M": 304.0,
    "params_decoder_M": 267.2,
    "flops_G": 123.4,
    "size_MB": 2180
  },
  
  "resources": {
    "vram_peak_GB": 2.77,
    "vram_fp16_GB": 1.5
  },
  
  "latency": {
    "t_pair_p50_ms": 45.2,
    "t_pair_p95_ms": 48.1,
    "t_pair_mean_ms": 45.5,
    "t_pair_std_ms": 2.3,
    "t_scene_s": 12.5,
    "pairs_per_sec": 22.1,
    "warmup_runs": 10,
    "measure_runs": 100
  },
  
  "quality": {
    "chamfer": 0.025,
    "absrel": 0.089,
    "rmse": 0.312,
    "delta1": 0.945,
    "reproj_px": 1.23
  },
  
  "environment": {
    "gpu": "NVIDIA RTX 3060 Laptop GPU",
    "gpu_memory_GB": 6,
    "cpu": "Intel i7-11800H",
    "ram_GB": 32,
    "os": "Windows 11",
    "python": "3.10.x",
    "pytorch": "2.6.0+cu124",
    "cuda": "12.4",
    "cudnn": "8.x",
    "cudnn_benchmark": true
  },
  
  "settings": {
    "input_resolution": [512, 384],
    "batch_size": 1,
    "precision": "FP32",
    "pair_graph": "neighbor_K4"
  }
}
```

---

## 九、Checklist（测试前检查）

- [ ] GPU 型号固定，后续所有实验用同一台
- [ ] 输入分辨率、batch size、pair_graph 固定
- [ ] 测试脚本能输出上述所有指标
- [ ] 日志格式符合统一 JSON schema
- [ ] 记录 commit hash 和测试日期
- [ ] 环境信息完整（硬件+软件）

---

## 十、关键原则

> **Baseline 的目标不是"跑得快"，而是建立一个"可复现、可对比、可扩展"的参考坐标系**

1. ✅ 必须统一测试平台（GPU + 软件栈）
2. ❌ 不需要一开始就在边缘设备上测
3. ✅ 必须把"与硬件强相关"和"与模型本身相关"的指标分开记录
4. ✅ Baseline 现在测一次，后面所有轻量化方法都只在这个 baseline 上对比
5. ❌ 不要 baseline 用 A100，轻量化用 RTX3060（混着报 latency 无效）

---

*最后更新: 2025-12-25*
