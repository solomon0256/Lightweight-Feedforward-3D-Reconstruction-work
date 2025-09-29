# 项目立项书（Project Charter）

## 1. 项目名称（暂定）

**系统性探索 Feedforward 3D Reconstruction 模型的轻量化 (Pruning + Quantization + Knowledge Distillation, PQK)**
（备用方向：无人机小目标检测的轻量化与改进）

---

## 2. 背景与动机

* 你希望在 2–4 个月内产出一篇 **中档 SCI（IF 3–6）** 论文，用于研究生申请 CV 增色。
* 你的条件：本科生水平，无实验室，仅一台电脑，无自主数据采集能力。
* 需要直观可见的实验结果，而非抽象理论。
* 方向锁定在 **机器视觉 / 人工智能 / 机器学习**，尤其是 **3D Reconstruction 与无人机视觉应用**。
* Feedforward 3D Reconstruction 模型（如 DUSt3R、VGGT、MASt3R）是 2023–2024 年的新兴方向，性能优异但资源消耗大。
* 轻量化（剪枝、蒸馏、量化）在分类/检测已有研究，但在该类 3D 模型上几乎无人系统探索，存在**空白点**。

---

## 3. 研究范围与任务

* **核心研究问题**：如何在保证精度的情况下，通过 PQK 轻量化降低前馈式 3D 重建模型的计算与存储开销。
* **方法**：

  * 剪枝（Pruning）：结构化剪枝 attention heads / hidden units / FFN。
  * 蒸馏（Knowledge Distillation）：logits / 特征 / 任务层输出蒸馏。
  * 量化（Quantization）：FP32 → FP16 / INT8。
* **实验设计**：

  * baseline: 原始 DUSt3R (Teacher)
  * 剪枝 (P)
  * 量化 (Q)
  * 蒸馏 (K)
  * PQ, PK, QK, PQK 全组合对比
* **数据集**：

  * 主：ScanNet、DTU、CO3D（任选其一/两）
  * 备用：VisDrone (无人机小目标检测)

---

## 4. 文献综述定位

* 我们已阅读：

  * 《Advances in Feed-Forward 3D Reconstruction and View Synthesis: A Survey》 (2025)
  * 《Feed-Forward 3D Reconstruction: Current Challenges and Future Directions》 (2025)

  * 《Multi-View 3D Reconstruction using Knowledge Distillation》 (arXiv, 2024.12, 未经同行评审)
  * 这篇文章是我们的基础！！！！！！！！！！！！！！！！！！！！！

  * 《PQK: Model Compression via Pruning, Quantization, and Knowledge Distillation》 (2021)
* 空白点：已有研究仅做蒸馏，且仅限室内小数据集；缺乏系统性 PQK 实验、缺乏边缘设备验证。

---

## 5. 时间线

* **第 1–2 周**：环境搭建，数据集准备，Teacher baseline 复现
* **第 3–5 周**：剪枝、蒸馏、量化实验，完成对比表
* **第 6–7 周**：消融实验、鲁棒性测试、可视化结果整理
* **第 8 周**：打包交付实验结果与图表，交由写手撰写论文
* **第 9–12 周**：论文写作、修改、定稿
* **第 12–16 周**：投稿与审稿答复

---

## 6. 风险与应对措施

1. **Teacher 模型难以复现**

   * 对策：先用小规模子集（ScanNet-mini/DTU 部分场景）跑通；必要时切换到备用方向（UAV 检测）。
2. **轻量化精度下降过大**

   * 对策：降低剪枝比例，结合蒸馏补偿，采用混合精度量化。
3. **时间超支**

   * 对策：若 3D 路线无法按时完成，则切换到 UAV 小目标检测 + YOLOv8 微改进，快速产出结果。

---

## 7. 预期交付物

* 数据集说明文档（来源、划分、预处理）
* 方法说明文档（Teacher/Student 配置，轻量化细节）
* 实验结果表（baseline vs 改进；PQ/K/Q 全组合消融）
* 速度—精度权衡图
* 可视化图板（重建结果对比、检测结果对比）
* 训练日志与配置文件
* 写手交付简报（贡献点、结果总结、参考文献列表）

---

## 8. 贡献点包装（初步）

1. **首个系统性研究 feedforward 3D reconstruction 模型的 PQK 轻量化**。
2. **定量对比不同轻量化组合，验证 trade-off 曲线**。
3. **边缘设备验证（GPU/Jetson/Colab），展示实际部署可行性**。
