# 📑 Research & Paper Writing Procedure
项目主题：Feedforward 3D Reconstruction 模型轻量化与边缘应用  
周期：约 2–3 个月  
输出：一篇可发表的工科实验型论文（目标：IEEE Access / EI 会议）

---

## 🎯 阶段 0：立项 & 前置准备
目标：确定研究范围，准备文献与实验环境

- [ ] 确定研究方向：  
  - Feedforward 3D Reconstruction (DUSt3R 等)
  - 模型压缩 (Pruning / Quantization / Knowledge Distillation)
  - 边缘应用（嵌入式 GPU / 移动平台）

- [ ] 文献收集（已完成 ✅）  
  - Feedforward 3D Reconstruction 论文  
  - 模型压缩 / 轻量化 论文  
  - 边缘计算相关论文  

- [ ] 输出文件：
  - `PROJECT_CHARTER.md` → 题目 / 目标 / 成功标准 / 风险
  - `literature_summary.xlsx` → 36 篇论文的表格（编号、贡献、缺陷、与你研究的关系）
  - `related_work_notes.md` → mini 文献综述笔记

---

## 📝 阶段 1：文献处理 & 研究设计
目标：吃透前人工作，确定实验计划

- [ ] 文献综述写作  
  - 每类 1–2 页总结  
  - 结构：现状 → 缺陷 → 可切入点  
  - 形成初版 “相关工作” 章节

- [ ] 研究问题定义  
  - baseline: DUSt3R  
  - 要做的改进：PQK (Pruning + Quantization + Knowledge Distillation)  
  - 对比对象：原始 DUSt3R / 他人轻量化方案（若有）

- [ ] 实验计划设计  
  - 数据集：DTU、ScanNet、CO3D  
  - 指标：Chamfer Distance, PSNR, SSIM, 参数量、推理时间  
  - 实验组合：
    - 原始模型
    - P / Q / K 单独
    - PQ / QK / PK
    - PQK 全部

- [ ] 输出文件：
  - `experiment_plan.md`
  - `dataset_info.md`

---

## ⚙️ 阶段 2：环境搭建
目标：搭建实验环境，跑通 baseline

- [ ] 软件环境  
  - Python, PyTorch, CUDA  
  - Conda 环境 → `requirements.txt`

- [ ] Baseline 复现  
  - 下载 DUSt3R 源码  
  - 跑通 demo，保存可视化结果 → `baseline_demo_output/`

- [ ] 输出文件：
  - `requirements.txt`
  - `baseline_logs/`
  - `baseline_demo_output/`

---

## 🧪 阶段 3：实验实施
目标：完成模型轻量化实验，记录数据

- [ ] 剪枝实验 (P)  
  - 不同比例（30%、50%、70%）  
  - 输出：`ablation_pruning.csv`

- [ ] 蒸馏实验 (K)  
  - 大模型 → 小模型  
  - Loss 曲线、对比表格  
  - 输出：`ablation_kd.csv`

- [ ] 量化实验 (Q)  
  - Post-training Quantization (PTQ)  
  - Quantization-aware Training (QAT)  
  - 输出：`ablation_quant.csv`

- [ ] PQK 组合实验  
  - 记录 trade-off：精度 vs. 速度  
  - 输出：`tradeoff_results.csv`

- [ ] 输出文件：
  - `results/main_results.csv`
  - `results/ablation_pruning.csv`
  - `results/ablation_kd.csv`
  - `results/ablation_quant.csv`
  - `figures/qualitative.png` (可视化对比)
  - `figures/tradeoff_curve.png`

---

## 📊 阶段 4：结果整理 & 分析
目标：把实验结果转化为论文图表

- [ ] 绘制图表  
  - 精度对比表  
  - 速度–精度折线图  
  - 可视化结果（对比图）

- [ ] 分析讨论  
  - 哪种方法 trade-off 最优？  
  - 为什么 PQK 最有效？  
  - 和边缘设备限制结合分析

- [ ] 输出文件：
  - `06_results/README.md`  
  - `07_figures/`

---

## ✍️ 阶段 5：论文写作
目标：完成论文初稿

- [ ] 结构：
  1. Abstract
  2. Introduction
  3. Related Work （文献综述）
  4. Method （PQK 设计）
  5. Experiments （实验流程 + 数据集 + 指标）
  6. Results & Discussion （表格、图表 + 分析）
  7. Conclusion （总结 + 未来展望）

- [ ] 输出文件：
  - `paper_draft.docx`
  - `references.bib`

---

## 📤 阶段 6：投稿 & 修改
目标：完成投稿，处理审稿意见

- [ ] 选择期刊 /会议  
  - IEEE Access（EI，快，工程导向）  
  - 或 ISIE / IWIS 等会议  

- [ ] 按模板排版  
  - `paper_final.tex`  
  - `paper_final.pdf`

- [ ] 审稿修改  
  - `review_response.md`

---

# ✅ 输出总览
最终会得到以下关键产物：
- `PROJECT_CHARTER.md`
- `literature_summary.xlsx`
- `related_work_notes.md`
- `experiment_plan.md`
- `requirements.txt`
- `baseline_demo_output/`
- `results/*.csv`
- `figures/*.png`
- `paper_draft.docx`
- `paper_final.pdf`
