# DUSt3R-PQK 实验任务表（v1）
非常清楚，我们现在在制定论文实验部分的**三套方案**，分别对应三种预算与时间压力场景，**都必须能满足如下要求**：

> * 明确展示我们的 **创新点**：Feedforward Transformer 的轻量化方法系统性对比；
> * **体现多个方法路径**（蒸馏、剪枝、量化），不是只做一个；
> * 结论必须具备论文说服力，足够投稿 IEEE Access / CVPR Workshop 等级；
> * 控制资源预算（最小 / 中等 / 最佳）在合理范围内；
> * 所有内容以 **DUSt3R 模型**为基准构建，符合你项目初衷。

---

## ✅ 总体假设条件（共通）

* 默认使用单张 A100 为基准，**训练总时长约 300–350h**
* 若用单张 H100，效率提升约 **1.7–2.2x**，总时长压缩为 **160–210h**
* 所有方案只跑一次主实验，每种方法选择最佳子路径，不做 Grid Search
* 蒸馏（K）、量化（Q）、剪枝（P）为核心三法
* 论文需要展示 **单法效果 + 多法组合（如 K→Q、P→K→Q）**

---

# 🪶 最小方案：保论文基本成立，控制总成本 < $600

### 🎯 目标

* 核心只跑蒸馏 + 量化
* 剪枝不做，联合路径不做
* 不做大规模消融、不做 PQK 联合范式

### 📦 实验结构（共 3 组）

| 序号 | 实验名称             | 说明               | GPU 预算（H100） |
| -- | ---------------- | ---------------- | ------------ |
| A1 | 蒸馏 K-only        | 轻量 student 蒸馏    | 20h          |
| B1 | Q-only (PTQ/QAT) | 同一 student 上量化   | 10h          |
| D1 | K→Q              | 从 student 上做 QAT | 12h          |
|    | Baseline Eval    | Teacher 原模型测试    | 3h           |
|    | 实验评估 + 写作        | 输出图表与结论          | -            |

**⏱️ 总计时间**：≈45小时
**💵 成本预估**（H100，$6.88/h）：约 **$310**
**论文贡献**：

* 首个分析 DUSt3R 蒸馏 + 量化的系统实验
* 可 Claim：“我们为 Feedforward Transformer 构建了专用 student 架构，并验证了量化敏感点与最佳 keep-list”

---

# ⚖️ 中等方案：增加剪枝路径，控制总成本 < $900

### 🎯 目标

* 覆盖 K/Q/P 三路径
* 至少做一次剪枝（结构化）
* 做一次联合路径（P→K）

### 📦 实验结构（共 5 组）

| 序号 | 实验名称          | 说明                | GPU 预算（H100） |
| -- | ------------- | ----------------- | ------------ |
| A1 | 蒸馏 K-only     | 轻量 student 蒸馏     | 24h          |
| B1 | Q-only        | 原模型量化             | 10h          |
| C1 | 剪枝 P-only     | 结构化剪枝 + 微调        | 14h          |
| E1 | P→K           | 剪枝后补偿蒸馏           | 14h          |
| D1 | K→Q           | Student 蒸馏后再量化    | 10h          |
|    | Baseline Eval | Teacher 测评 + 结果对比 | 3h           |

**⏱️ 总计时间**：≈75小时
**💵 成本预估**：约 **$510–$600**（取 H100）
**论文贡献**：

* 明确三种轻量化路径对比（K / P / Q）
* 重点展示结构剪枝效果（可选剪 0.1/0.3 两档）
* Claim：我们首次系统性研究 DUSt3R 剪枝与量化可部署路径

---

# 🏆 最佳方案：具备顶刊冲击力，展示完整 PQK 联合与消融

### 🎯 目标

* 全部子路径执行（K/P/Q + PQK）
* 全部联合路径都做（K→Q、P→K→Q、PQK 一步法）
* 做多个 keep-list 消融、剪枝敏感性、量化校准规模实验

### 📦 实验结构（共 8–9 项）

| 实验名称           | 内容概述                   | GPU 预算（H100） |
| -------------- | ---------------------- | ------------ |
| K-only         | 主 student 蒸馏           | 28h          |
| Q-only         | PTQ + QAT + keep-list  | 12h          |
| P-only         | 通道剪枝（ρ=0.1） + 微调       | 16h          |
| K→Q            | 蒸馏后量化                  | 12h          |
| P→K            | 剪后补偿蒸馏                 | 14h          |
| P→K→Q          | 剪+蒸+量化                 | 20h          |
| Joint PQK      | 一步联合范式                 | 25h          |
| Ablation Study | Loss 结构、剪枝策略、keep-list | 10h          |
| Baseline + 评估  | 原模型评估，结论图表             | 3h           |

**⏱️ 总计时间**：≈140–150小时
**💵 成本预估**：H100 单卡约 **$950–$1,050**
**论文贡献**：

* **首次**系统性研究 DUSt3R 的蒸馏 + 剪枝 + 量化联合范式
* 明确提出 "PQK 三合一”轻量化工程路径
* 可撰写：“我们构建了完整 Feedforward Transformer 的轻量化评估基准”
* 可选投稿目标：

  * CVPR Workshop: Efficient 3D
  * NeurIPS Submission（需补实验）

---

## 🔁 后续策略建议

| 事项       | 建议做法                                 |
| -------- | ------------------------------------ |
| 数据复用     | 所有实验复用同一校准集（避免重复训练）                  |
| 快照管理     | 每轮保存 best.ckpt，防止中断损失                |
| 成本优化     | 大实验用 H100，评估用 A10/G5，避免 P4           |
| 多实验并行    | 不推荐，增加磁盘管理复杂度和写论文出错风险                |
| 实验执行顺序建议 | K-only → P-only → Q-only → 联合路径（PQK） |

---

如需我给出完整执行清单（每个命令/路径、日志管理、时间表），可立刻生成。是否需要继续？

> **用途**：作为本项目唯一的执行蓝图与排程文档；所有实验、检查点、日志字段、成功线、止损规则、输出物与日程均以此为准。

---

## 0. 文件放置与命名

* **建议存放路径**：`/experiments/DUSt3R_PQK/schedule/DUSt3R-PQK_实验任务表_v1.md`
* **版本管理**：采用递增版本号（v1, v2…）；每次改动在本文件最末“变更记录”处登记。
* **关联文件**：

  * 配置：`/experiments/DUSt3R_PQK/configs/{distill,quant,prune}.yaml`
  * 脚本：`/experiments/DUSt3R_PQK/scripts/*`
  * 日志：`/experiments/DUSt3R_PQK/logs/*.json`
  * 模型：`/experiments/DUSt3R_PQK/outputs/*`
  * 报告：`/experiments/DUSt3R_PQK/reports/*`

---

## 1. 全局口径与约束（硬性）

* **模型**：DUSt3R（Teacher 已验证）
* **输入与负载**：`[1,3,512,512]`，**BS=1**，固定 **pair-graph = 邻近K=4**（静态 shape）。
* **指标**：

  * *质量*：Chamfer / AbsRel / RMSE / δ1 / 重投影误差(px)
  * *效率*：t_pair(p50/p95, ms) / t_scene(s) / pairs/sec
  * *资源*：VRAM(GB) / Params(M) / Size(MB) / FLOPs(G)（Jetson 可加功耗）
* **成功阈值（主线）**：对 Teacher，**精度跌幅 ≤ 1%**；对 Student FP32，**t_pair p50 下降 ≥ 50%**。
* **预算/周期**：≤ $1000（GPU 小时约 100h），≤ 30 天。

---

## 2. 工具链（主/备）

* **主线**：PyTorch → ONNX(静态) → TensorRT + **ModelOpt**（剪枝/量化/蒸馏组合 & keep-list）。
* **备线**：PyTorch → **OpenVINO NNCF / Intel Neural Compressor**（量化 & 结构化剪枝）。
* **资产清单**：校准集 ≥ 512 张（量化）；评测对图若干（固定列表与顺序）。

---

## 3. 实验全集与优先级

> 共 8 类；本论文主线执行 **5 类**（A/B/D/C/H）。其余为可选增强。

| 代号 | 组合            | 目的              | 前沿点                                            |  预估 GPU |  优先级  |
| -- | ------------- | --------------- | ---------------------------------------------- | ------: | :---: |
| A  | **K-only**    | 学生FP32逼近Teacher | 轻量蒸馏日程（后段加大KL）                                 |  32–48h | ★★★★★ |
| B  | **Q-only**    | 端侧收益最大          | QAT INT8 + **keep-list**(LN/Softmax/Attn保FP16) |  12–20h | ★★★★★ |
| C  | **P-only**    | 可部署的结构化降FLOPs   | ρ=0.1/0.3 + 依赖/敏感度                             |  20–30h | ★★★★☆ |
| D  | **K→Q**       | 工程主线            | 蒸馏后 QAT 的业界标配                                  | +12–20h | ★★★★★ |
| E  | **P→K**       | 剪后补偿精度          | 短蒸馏 10–15 epoch                                | +12–18h | ★★★★☆ |
| F  | **P→K→Q**     | 顺序上限            | 结构化+蒸馏+QAT                                     | +20–30h | ★★★☆☆ |
| G  | **Joint PQK** | 一步法创新           | 稀疏+蒸馏+量化感知联合损失                                 |  30–40h | ★★☆☆☆ |
| H  | **消融/敏感**     | 学术完整            | Loss/keep-list/校准规模/PairGraph/输入尺度             |   6–12h | ★★★★☆ |

> **执行集（v1）**：A, B, **D**, C, H。F/G 视进度再定。

---

## 4. 统一日志字段（CSV/JSON）

```
exp_id, combo, rho, T, beta, gamma, bits_w, bits_a, keep_list,
params_M, flops_G, size_MB, vram_GB,
chamfer, absrel, rmse, delta1, reproj_px,
t_pair_p50_ms, t_pair_p95_ms, t_scene_s, pairs_per_sec,
notes, gpu_hours, seed, commit, datetime
```

* **日志目录**：`/experiments/DUSt3R_PQK/logs/{teacher_eval,distill_log,quant_eval,prune_eval,edge_log}.json`
* **生成约束**：所有脚本必须写满上述字段（缺失用 `null`）。

---

## 5. 阶段化执行蓝图（SOP）

### 5.1 A) K-only（轻量蒸馏）

* **目标**：学生 FP32 精度跌幅 ≤ 1%，为量化提供稳定分布。
* **损失**：`L = α·L_task + β·KL(p_T^T || p_S^T) + γ·||F_T - F_S||^2`

  * 超参：`T ∈ {3,5}`；`β ∈ {0.5,0.7}`；`γ ∈ {0,0.1}`（默认 `γ=0`）
  * 日程：前 70% 以 `L_task` 为主，后 30% 提高 `β`（如 0.5→0.7）。
* **学生结构**：在 DUSt3R 编解码器上 **减深度/heads/FFN 25–35%**；或用 ρ=0.1 的轻剪版本作为 Student-P。
* **步骤清单**：

  1. 固定 `workload.yaml`（输入/配对/seed）。
  2. 加载 Teacher → 产出 Teacher 基线日志。
  3. 启动蒸馏（3–4 个小网格点；早停=3）。
  4. 评测：质量/效率/资源三类指标；归档 ckpt。
* **止损**：连续 3 ckpt 未提升或跌幅>1.5% 即停；最大全程 30 epoch。
* **成功线**：主质量指标 ≤ 1% 跌幅。

### 5.2 B) Q-only（量化）

* **目标**：端上时延/体积/显存显著下降。
* **策略**：PTQ 校准（≥512 张）→ 若掉点>1% 转 **QAT**（10–15 epoch）。

  * 量化：`W8A8`, 权重 per-channel，激活 per-tensor；
  * **keep-list**：`LayerNorm / Softmax / AttentionScales` 固定 FP16。
* **步骤清单**：PTQ 自检 → QAT 训练 → 导出 ONNX → TensorRT engine（静态 512²）。
* **止损**：QAT 10 epoch 仍>1% 掉点 → 扩大 keep-list 或回退至 K→Q 路线。
* **成功线**：≤1% 掉点；**t_pair p50 ↓ ≥ 50%**（vs 学生 FP32）。

### 5.3 D) K→Q（主线）

* **目标**：最稳交付管线（论文核心）。
* **做法**：A 的最佳学生 → 按 B 的 QAT；keep-list 同步。
* **成功线**：≤1% 掉点；t_pair p50 ↓ ≥ 50%。

### 5.4 C) P-only（结构化剪枝）

* **目标**：结构化、可部署地降低 FLOPs/Params。
* **策略**：通道/头/FFN 维剪；L1/L2 importance + 依赖/敏感度引导；**仅 ρ=0.1 / 0.3 两档**。
* **步骤清单**：剪枝 → 微调 10–15 epoch → 评测归档。
* **止损**：跌幅>3% 或不收敛即停。
* **成功线**：体积降低 ≥ 25%，主指标跌幅 ≤ 3%。

### 5.5 H) 消融与敏感性

* **Loss**：去 KD / 去 FD（`γ=0`）/ 只 KL vs KL+FD。
* **keep-list**：去 LN 或 Softmax 或 Attn 各一次。
* **校准规模**：128/256/512 对比。
* **pair-graph**：K=2/4/8；Top-K 相似度 vs 邻近。
* **输入尺度**：在“全流程最佳单点”上补测 384 与 640 单点复测。

---

## 6. 30 天日程（可勾选）

### 第 1 周

* [ ] D1–D2：环境 + `baseline_eval.py` + `workload.yaml`；`teacher_eval.json` 产出。
* [ ] D3–D4：校准集(≥512)整理；Teacher 基线报告。
* [ ] D5–D7：K-only 两点（T=3/5, β=0.5）；必要时补 β=0.7。

### 第 2 周

* [ ] D8：PTQ 预检 + keep-list 自检。
* [ ] D9–D10：K 最优学生 → QAT。
* [ ] D11：TensorRT 引擎（静态 512²）。
* [ ] D12–D14：P-only（ρ=0.1 微调）。

### 第 3 周

* [ ] D15–D16：P→K（短蒸馏 10–15 epoch）。
* [ ] D17–D18：P→K→Q（如进度允许）。
* [ ] D19：K→Q vs P→K→Q 对比图表。

### 第 4 周

* [ ] D20–D22：Joint PQK（若资源允许；否则跳过）。
* [ ] D23：消融/敏感（keep-list / 校准规模 / K 值）。
* [ ] D24–D26：端侧复测 + 384/640 单点复测。
* [ ] D27–D30：结果总表、曲线与报告草稿。

---

## 7. 输出物清单（论文可直接使用）

* `reports/result_table.xlsx`：四象限（质量/效率/资源/端测）主表
* `reports/plots/*.png`：Trade-off 曲线（x=t_pair 或 VRAM，y=主质量指标）
* `reports/baseline_report.md`：Teacher 基线
* `logs/*.json`：统一字段的原始日志（评审最爱）
* `outputs/*.pth|.engine`：模型/引擎产物

---

## 8. 风险与回滚

* **量化掉点 >1%**：扩大 keep-list；启用 K→Q；或延长 QAT 5 epoch。
* **剪枝不收敛**：降档到 ρ=0.1；缩短微调并回蒸馏补偿；必要时撤销 P。
* **蒸馏不收敛**：减小 β 或延长前 70% 的 `L_task` 权重阶段。

---

## 9. 变更记录

* v1（Oct 8, 2025）：首版建立（实验全集+主线五类+日程+SOP）。
