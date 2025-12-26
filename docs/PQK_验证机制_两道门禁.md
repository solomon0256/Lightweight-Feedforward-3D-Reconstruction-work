# PQK 实验验证机制：两道门禁 + 三套数据

> **创建日期**: 2025-12-26  
> **来源**: GPT 工程化指导  
> **目的**: 避免服务器返工，本地验证脚本正确性与性能趋势

---

## 🎯 核心结论

**"只靠 1-2 个样本跑通"只能证明代码不报错，不能证明口径正确，更不能证明性能趋势。**

正确做法：用**小规模但足够覆盖的"验收集 + 口径锁定 + 趋势预估"**，把两类风险拆开处理：

| 风险类型 | 解决方案 | 在哪做 |
|----------|----------|--------|
| 脚本逻辑错误 | Golden outputs + 统计一致性 + Schema 断言 | 本地 |
| 性能/精度崩溃 | 小规模趋势集 + 早期预警阈值 | 本地，服务器只做最终确认 |

---

## 📋 两道门禁 + 三套数据

### 门禁 A：正确性门（防口径漂移）

**目标**：量化/剪枝/蒸馏后 **输出字段不变、尺度不变、评测口径不变**

### 门禁 B：趋势门（防精度/性能崩）

**目标**：在小规模上就能看出"崩不崩""有没有希望"

### 三套数据（固定，不返工）

| 数据集 | 规模 | 用途 | 耗时 |
|--------|------|------|------|
| **Smoke Set（冒烟集）** | 8-16 对 | 能否跑完、schema一致、无NaN/Inf、速度方向正确 | 2-5分钟 |
| **Trend Set（趋势集）** | 128-256 对 | 指标趋势是否开始崩 | 30-60分钟 |
| **Final Set（最终集）** | 完整评测 | 论文口径，只在通过A+B后跑 | 服务器 |

---

## 🔒 风险1：脚本逻辑错（口径漂移）解决方案

### 1.1 Schema/字段断言（必须）

量化后最常见 bug：
- 输出字段名变了
- dtype 变了（float16/int8 导致数值截断）
- shape 变了
- 缺字段导致统计默默跳过

**断言规则**：
```python
# 评测开始前必须 assert
required_keys = ['pred_depth', 'pred_pose', 'confidence', 'pts3d']
for key in required_keys:
    assert key in outputs, f"Missing key: {key}"
    assert outputs[key].shape == expected_shapes[key], f"Shape mismatch: {key}"
    assert outputs[key].dtype in allowed_dtypes, f"Dtype error: {key}"
    assert torch.isfinite(outputs[key]).all(), f"NaN/Inf in {key}"
```

### 1.2 尺度对齐锁定（必须）

最容易返工的坑：**scale alignment 变了**

**解决方案**：
- 把"尺度策略"写死并落盘：`scale_mode = median_ratio`
- 保存每张图的 `scale_s`
- 量化/剪枝后必须使用同一策略
- 检查 `scale_s` 的分布（mean/std/p95）不能漂太多

### 1.3 Golden Outputs（强力但成本低）

在 Smoke Set 上保存"黄金中间产物"：

```json
// golden_smoke.jsonl - 每行一个样本
{
  "sample_id": "seq01_frame000_frame001",
  "t_err_m": 0.0185,
  "R_err_deg": 1.55,
  "absrel": 0.1168,
  "rmse": 0.1446,
  "delta1": 0.8995,
  "scale_s": 1.0234
}
```

**对比规则**：
| 方法 | 允许误差 |
|------|----------|
| FP16 | 极小（< 0.1%） |
| INT8 | 可放宽（< 1%） |
| 剪枝 | 按剪枝率调整 |

---

## 📊 风险2：性能/精度崩（趋势预警）解决方案

### 2.1 趋势集要测什么

**深度指标**：
- `absrel, rmse, delta1, delta2, delta3, rmse_log, sqrel, si_log`

**位姿指标**：
- `median_pos_error, median_angular_error`
- `acc@0.25m,2°`, `acc@0.5m,5°`

**性能指标**：
- `latency_p50/p95`, `vram_peak`

### 2.2 早停阈值（自动判死刑规则）

| 方法 | 精度红线 | 动作 |
|------|----------|------|
| **FP16** | delta1 下降 > 1% 或 visloc acc 降 > 2% | 停，查口径 |
| **INT8 PTQ** | delta1 下降 > 3% 或 absrel 上升 > 10% | 判"趋势崩"，不上服务器 |
| **剪枝** | 每减少 20% FLOPs，delta1 下降 > 2% | 改剪枝策略 |
| **蒸馏** | 前 10% 训练若指标不回升 | 立刻停，检查 loss |

---

## 📜 评测合同（Evaluation Contract）

**必须冻结，永不随实验改动**：

```yaml
# eval_contract.yaml
version: "1.0"
frozen_date: "2025-12-26"

data:
  dataset: "7-scenes"
  subscene: "heads"
  query_split: "seq-01"
  mapping_split: "seq-02"
  pairs_file: "pose_based_top20.txt"
  sampling_seed: 42

input:
  resolution: [512, 384]
  normalize: true
  batch_size: 1

output_route:
  visloc: "DUSt3R as 2D-2D matcher + retrieval topK"
  depth: "F(I, I), depth = pts3d[:,:,2]"

scale_alignment:
  method: "median_ratio"
  clip_range: [0.1, 10.0]

core_kpi:
  pose:
    - median_t_cm
    - median_R_deg
    - acc@0.25m,2deg
  depth:
    - absrel
    - delta1
    - rmse
  performance:
    - t_pair_p50_ms
    - t_pair_p95_ms
    - vram_peak_gb

guardrails:
  accuracy:
    absrel_max_increase_pct: 10
    delta1_max_decrease_pct: 3
    visloc_acc_max_decrease_pct: 5
  stability:
    nan_inf_rate: 0
    assertion_failure_rate: 0
  performance:
    latency_must_decrease: true
    latency_variance_max_ratio: 2.0
```

---

## 🚀 执行流程（最短路径）

### Step 0：冻结 Baseline（已完成 ✅）

- 固定数据集、split、分辨率、尺度对齐策略
- 保存 `runs/BASELINE_FREEZE/`
- 打 Git Tag `baseline-freeze-v1`

### Step 1：建立 Smoke + Golden（一次性，10分钟）

```bash
# 固定 16 对样本
python scripts/create_smoke_set.py --num-pairs 16 --seed 42

# baseline 在 smoke 上保存 golden
python scripts/eval_smoke.py --save-golden
```

### Step 2：每次 PQK 版本先过 Smoke Gate（2-5分钟）

```bash
python scripts/eval_smoke.py --check-golden --method Q --variant fp16
```

**通过条件**：
- [ ] 输出字段/shape/dtype 全一致
- [ ] 指标计算不报错、无 NaN/Inf
- [ ] 与 golden 的差异在允许范围

**不过就别往下走！**

### Step 3：再过 Trend Gate（本地 30-60分钟）

```bash
python scripts/eval_trend.py --method Q --variant fp16 --num-pairs 200
```

**检查**：
- [ ] 精度护栏：absrel/delta1/visloc 是否触发红线
- [ ] 稳定性护栏：失败率为 0
- [ ] 性能护栏：延迟下降、方差合理

**触发早停阈值 → 判死刑，不上服务器**

### Step 4：通过后再上服务器跑 Final

只给"候选胜者"付费！

---

## 🔧 为什么"有标准流程"≠"照做就不会翻车"

### 5个会让"照流程"失效的变量

| # | 变量 | 风险 |
|---|------|------|
| 1 | 输出不是分类概率 | pose/depth/pointmap 误差对齐敏感 |
| 2 | 尺度对齐策略多种 | 任何改变都能让指标"假提升/假下降" |
| 3 | 评测协议强依赖数据集 | 不同脚本默认不同 sampling/filtering |
| 4 | 量化改变数值稳定性 | attention/layernorm/softmax 容易局部崩 |
| 5 | 蒸馏监督信号定义 | distill 3D 需要选 loss/对齐/mask |

---

## 📚 参考资源

### 学术综述

| 论文 | 链接 |
|------|------|
| A Survey on Model Compression for LLMs | [arXiv:2308.07633](https://arxiv.org/abs/2308.07633) |
| Model Compression for DNNs: A Survey | [MDPI](https://www.mdpi.com/2073-431X/12/3/60) |
| Survey of Model Compression and Acceleration | [arXiv:1710.09282](https://arxiv.org/abs/1710.09282) |
| Comprehensive Survey for Vision Transformers | [arXiv:2404.10407](https://arxiv.org/abs/2404.10407) |

### 官方教程

| 资源 | 链接 |
|------|------|
| PyTorch Knowledge Distillation | [PyTorch Docs](https://docs.pytorch.org/tutorials/beginner/knowledge_distillation_tutorial.html) |
| DeepSpeed Model Compression | [DeepSpeed](https://www.deepspeed.ai/tutorials/model-compression/) |

---

## ✅ Checklist（每次 PQK 实验）

### 实验前
- [ ] 确认 `eval_contract.yaml` 未修改
- [ ] 确认 `golden_smoke.jsonl` 存在
- [ ] 确认 smoke/trend 数据集固定

### Smoke Gate
- [ ] Schema 断言全部通过
- [ ] 无 NaN/Inf
- [ ] 与 golden 差异在允许范围
- [ ] 速度方向正确（量化/剪枝应该更快）

### Trend Gate
- [ ] absrel 上升 < 10%
- [ ] delta1 下降 < 3%
- [ ] visloc acc 下降 < 5%
- [ ] 延迟确实下降
- [ ] 无稳定性问题

### 上服务器前
- [ ] Smoke Gate ✅
- [ ] Trend Gate ✅
- [ ] 所有文件已提交 Git
- [ ] config.yaml 已保存

---

## 🎯 核心原则

> **"只要 1 对 2 没问题就不会离预期差太远吗？"**
> 
> **不成立。**
>
> - 脚本口径漂移不会导致报错，但会让你得到"看似合理的错结果"
> - 量化/剪枝的精度崩在 1-2 样本上看不出来，必须看分布和趋势
>
> **正确表述**：通过门禁 A（口径锁定）+ 门禁 B（趋势门），才可以认为"上服务器大规模跑不会离预期差太远"。

---

*文档版本: v1.0 | 最后更新: 2025-12-26*
