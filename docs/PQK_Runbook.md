# PQK 实验执行规范 (Runbook)

> **版本**: v1.0  
> **创建日期**: 2025-12-26  
> **状态**: Active

---

## 🎯 核心原则

**"不返工 + 可复现 + 论文导向"**

1. Baseline 已冻结 (`baseline-freeze-v1`)，只读不改
2. 所有 PQK 实验使用同一套评测 schema
3. 每次 run 必须产出标准化文件

---

## 📁 目录结构

```
runs/
├── BASELINE_FREEZE/           # 冻结的 baseline（只读）
│   ├── baseline_complete.json
│   ├── depth_metrics_complete.json
│   ├── command.txt
│   ├── git_commit.txt
│   ├── git_diff.patch
│   └── README.md
│
├── 20251226_1500_Q_fp16_7scenes_heads_s0/   # 实验 run
│   ├── config.yaml            # 超参配置
│   ├── command.txt            # 执行命令
│   ├── git_commit.txt         # commit hash
│   ├── git_diff.patch         # 代码改动
│   ├── stdout.log             # 终端输出
│   ├── stderr.log             # 错误输出
│   ├── summary.json           # 聚合结果（与baseline同schema）
│   ├── results_raw.jsonl      # 逐样本结果
│   └── profile.json           # 性能分析
│
└── ...
```

---

## 🏷️ 实验ID命名规范

格式：`YYYYMMDD_HHMM_<method>_<variant>_<dataset>_s<seed>`

| 字段 | 说明 | 示例 |
|------|------|------|
| YYYYMMDD_HHMM | 时间戳 | 20251226_1500 |
| method | P / Q / K | Q |
| variant | 具体变体 | fp16, int8, pruned_50 |
| dataset | 数据集 | 7scenes_heads |
| seed | 随机种子 | s0 |

**示例**:
- `20251226_1500_Q_fp16_7scenes_heads_s0`
- `20251226_1700_P_encoder_50pct_7scenes_heads_s42`
- `20251227_0900_K_vit_small_7scenes_heads_s0`

---

## 📋 每次 Run 必须产出的文件

### 1. config.yaml（必须）

```yaml
exp_id: "20251226_1500_Q_fp16_7scenes_heads_s0"
method: "Q"
variant: "fp16"
dataset: "7scenes_heads"
seed: 0
timestamp: "2025-12-26T15:00:00"

model:
  name: "DUSt3R_ViTLarge_BaseDecoder_512_dpt"
  weights: "checkpoints/DUSt3R_ViTLarge_BaseDecoder_512_dpt.pth"
  precision: "fp16"

data:
  dataset_path: "datasets/7-scenes/heads"
  resolution: [512, 384]
  pairs_file: "pose_based_top20.txt"
  scale_alignment: "median"

# PQK 特定参数
quantization:  # Q
  bits: 16
  calibration_samples: 100

# pruning:     # P
#   method: "magnitude"
#   ratio: 0.5
#   structured: true

# distillation:  # K
#   teacher: "DUSt3R_ViTLarge"
#   temperature: 4.0
#   alpha_kd: 0.7
```

### 2. summary.json（必须，与 baseline 同 schema）

```json
{
  "exp_id": "20251226_1500_Q_fp16_7scenes_heads_s0",
  "method": "Q",
  "variant": "fp16",
  "dataset": "7scenes_heads",
  "timestamp": "2025-12-26T15:00:00",
  "baseline_ref": "runs/BASELINE_FREEZE/baseline_complete.json",
  
  "model": {
    "name": "DUSt3R_ViTLarge_BaseDecoder_512_dpt",
    "params_total": 571166720,
    "macs": 464700000000
  },
  
  "performance": {
    "t_pair_p50_ms": 180.0,
    "t_pair_p95_ms": 195.0,
    "vram_peak_gb": 1.8,
    "throughput_pairs_per_sec": 5.5
  },
  
  "quality_depth": {
    "absrel": 0.1170,
    "sqrel": 0.0361,
    "rmse": 0.1448,
    "rmse_log": 0.1655,
    "delta1": 0.8990,
    "delta2": 0.9630,
    "delta3": 0.9775,
    "si_log": 0.1615
  },
  
  "quality_pose_visloc": {
    "median_pos_error_m": 0.0186,
    "median_angular_error_deg": 1.56,
    "acc_0.1m_1deg": 31.8,
    "acc_0.25m_2deg": 59.5
  }
}
```

### 3. 其他必须文件

| 文件 | 内容 |
|------|------|
| `command.txt` | 完整执行命令 |
| `git_commit.txt` | `git rev-parse HEAD` 输出 |
| `git_diff.patch` | `git diff` 输出 |
| `stdout.log` | 终端输出 |
| `results_raw.jsonl` | 逐样本结果（可选但建议） |
| `profile.json` | 性能分析（可选但建议） |

---

## 🚀 PQK 执行顺序

### Phase 1: Quantization（最快出结果）

| 实验 | 说明 | 预期收益 |
|------|------|----------|
| Q1: FP16 | 半精度推理 | 速度 ~2x, VRAM ~0.5x |
| Q2: INT8 PTQ | 8位量化 | 速度 ~3x, VRAM ~0.25x |
| Q3: QAT | 量化感知训练 | 如果PTQ掉太多再做 |

### Phase 2: Pruning（参数/速度曲线）

| 实验 | 说明 | 预期收益 |
|------|------|----------|
| P1: Encoder 30% | 剪 encoder 30% | params -30%, 精度小降 |
| P2: Encoder 50% | 剪 encoder 50% | params -50%, 速度提升 |
| P3: Full 50% | 全模型剪枝 | 更激进压缩 |

### Phase 3: Knowledge Distillation（训练小模型）

| 实验 | 说明 | 预期收益 |
|------|------|----------|
| K1: ViT-Small | 用小 encoder | params ~150M |
| K2: Feature KD | 特征级蒸馏 | 更好精度保持 |
| K3: Combined | P+Q+K 组合 | 极致轻量化 |

---

## 🛠️ 使用 RunLogger

```python
from scripts.run_logger import RunLogger

# 创建实验
with RunLogger("Q", "fp16", "7scenes_heads", seed=0) as run:
    # 1. 记录配置
    run.log_config({
        "model": {"name": "DUSt3R_ViTLarge", "precision": "fp16"},
        "data": {"dataset_path": "datasets/7-scenes/heads"},
    })
    
    # 2. 运行实验...
    results = run_experiment()
    
    # 3. 记录结果
    run.log_results(results)
    
    # 4. 记录性能
    run.log_profile({"t_pair_p50_ms": 180, "vram_peak_gb": 1.8})

# 自动保存所有文件到 runs/<exp_id>/
```

---

## 📊 与 Baseline 对比

```python
from scripts.run_logger import RunLogger

# 对比当前实验与 baseline
comparison = RunLogger.compare_with_baseline(
    "runs/20251226_1500_Q_fp16_7scenes_heads_s0/summary.json"
)

# 输出:
# {
#   "quality_depth": {
#     "absrel": {"baseline": 0.1168, "current": 0.1170, "change_pct": 0.17}
#   },
#   "performance": {
#     "t_pair_p50_ms": {"baseline": 353, "current": 180, "change_pct": -49.0}
#   }
# }
```

---

## ✅ Checklist（每次 Run）

- [ ] 使用 `RunLogger` 创建实验
- [ ] 填写 `config.yaml` 所有必要字段
- [ ] 确保 `summary.json` schema 与 baseline 一致
- [ ] 保存 `git_commit.txt` 和 `git_diff.patch`
- [ ] 运行完成后检查输出文件完整性
- [ ] （可选）与 baseline 对比并记录 change_pct

---

## 🔗 相关文件

| 文件 | 说明 |
|------|------|
| [runs/BASELINE_FREEZE/](../runs/BASELINE_FREEZE/) | 冻结的 baseline |
| [scripts/run_logger.py](../scripts/run_logger.py) | 统一日志系统 |
| [logs/baseline_complete.json](../logs/baseline_complete.json) | Baseline 完整结果 |

---

*文档版本: v1.0 | 最后更新: 2025-12-26*
