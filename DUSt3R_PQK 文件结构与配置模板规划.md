# DUSt3R_PQK 文件结构与配置模板规划（v1）

## 🧱 一、推荐的文件结构（标准科研项目结构 + 轻量化实验专用）

**存放根路径建议：**

```
/experiments/DUSt3R_PQK/
```

---

### 📂 完整目录树结构

```
/experiments/DUSt3R_PQK/
│
├── schedule/                     # 实验任务计划与日程
│   ├── DUSt3R-PQK_实验任务表_v1.md
│   └── TaskCards/                # 每个实验一张独立任务卡（markdown）
│       ├── K-only_A1.md
│       ├── K-only_A2.md
│       ├── Q-only_B1.md
│       ├── K→Q_D1.md
│       ├── P-only_C1.md
│       ├── H_Ablation_H1.md
│       └── H_Ablation_H2.md
│
├── configs/                      # YAML 配置文件
│   ├── distill.yaml              # 蒸馏配置模板
│   ├── quant.yaml                # 量化配置模板
│   ├── prune.yaml                # 剪枝配置模板
│   ├── workload.yaml             # 公共输入与环境配置
│   └── eval.yaml                 # 统一评测配置（Teacher/Student）
│
├── scripts/                      # 实验脚本
│   ├── run_distill.py
│   ├── run_quant.py
│   ├── run_prune.py
│   ├── run_eval.py
│   └── utils/                    # 公共函数库
│       ├── logger.py
│       ├── metrics.py
│       ├── trainer.py
│       ├── quant_tools.py
│       └── prune_tools.py
│
├── data/
│   ├── calibration/              # 量化校准集（≥512 张）
│   ├── eval_pairs/               # 测试对图
│   ├── dataset_info.json
│   └── README.md
│
├── logs/
│   ├── teacher_eval.json
│   ├── distill_log.json
│   ├── quant_eval.json
│   ├── prune_eval.json
│   ├── edge_eval.json
│   └── unified_log_schema.json   # 日志字段定义（v1.1 扩展）
│
├── outputs/
│   ├── checkpoints/              # *.pth 文件
│   ├── engines/                  # TensorRT *.engine 文件
│   └── reports/                  # 中间可视化结果（可选）
│
├── reports/
│   ├── result_table.xlsx
│   ├── plots/
│   │   ├── tradeoff_curve.png
│   │   ├── ablation_chart.png
│   │   └── latency_vs_quality.png
│   └── baseline_report.md
│
└── README.md
```

---

## ⚙️ 二、配置模板规划（YAML）

这些 YAML 会直接被脚本读取。所有参数采用“**低耦合可调**”风格。

生成计划：三份模板（distill.yaml / quant.yaml / prune.yaml），内容包括：

* 数据与路径设定；
* 主要超参；
* 可选调节项；
* 输出控制（日志与保存路径）。

**命名路径**：

```
/experiments/DUSt3R_PQK/configs/distill.yaml
/experiments/DUSt3R_PQK/configs/quant.yaml
/experiments/DUSt3R_PQK/configs/prune.yaml
```

这三份模板将用于快速配置蒸馏、量化、剪枝流程，支持直接在 `run_*.py` 脚本中调用。
