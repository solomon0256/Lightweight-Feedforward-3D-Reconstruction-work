# 🛠️ DUSt3R-PQK 代码工程进度

> **目标**：从零搭建最小方案实验平台（Baseline + K + Q + K→Q）  
> **开始时间**：2025-12-22  
> **预计完成**：2-3 工作日

---

## 📋 工程阶段清单

### Phase 0: 基础设施（公共工具库）
- [ ] `scripts/utils/config.py` - 配置加载器
- [ ] `scripts/utils/logger.py` - 统一日志写入
- [ ] `scripts/utils/metrics.py` - 指标计算（Chamfer/AbsRel/RMSE/δ1）
- [ ] `scripts/utils/timer.py` - 时延统计（p50/p95）
- [ ] `scripts/utils/model_stats.py` - 模型统计（Params/FLOPs/Size）

### Phase 1: Baseline 评测
- [ ] `scripts/baseline_eval.py` - Teacher 评测主脚本
- [ ] 验证：能加载模型、跑推理、输出日志

### Phase 2: K-only 蒸馏
- [ ] `scripts/models/student.py` - Student 架构定义
- [ ] `scripts/train_distill.py` - 蒸馏训练主脚本
- [ ] 验证：能启动训练循环、保存 checkpoint

### Phase 3: Q-only 量化
- [ ] `scripts/quantize.py` - PTQ/QAT + ONNX 导出
- [ ] 验证：能完成量化、导出 ONNX

### Phase 4: K→Q 联合
- [ ] `scripts/run_kq_pipeline.py` - 联合流程脚本
- [ ] 验证：能串联 K→Q 完整流程

### Phase 5: 集成测试
- [ ] 干跑测试（mock 数据）
- [ ] 配置校验脚本
- [ ] 文档完善

---

## 📝 详细进度记录

### 2025-12-22 Session 1

**开始时间**：[待记录]

#### Phase 0: 基础设施

##### 0.1 配置加载器
- **文件**：`scripts/utils/config.py`
- **功能**：加载 YAML 配置，合并 workload/eval/实验配置
- **状态**：🔄 进行中

---

## 📁 最终文件结构预览

```
scripts/
├── utils/
│   ├── __init__.py
│   ├── config.py        # 配置加载
│   ├── logger.py        # 统一日志
│   ├── metrics.py       # 指标计算
│   ├── timer.py         # 时延统计
│   └── model_stats.py   # 模型统计
├── models/
│   ├── __init__.py
│   └── student.py       # Student 架构
├── baseline_eval.py     # P0: Teacher 评测
├── train_distill.py     # P1: 蒸馏训练
├── quantize.py          # P2: 量化
├── run_kq_pipeline.py   # P3: K→Q 联合
└── devcheck.py          # 干跑校验
```

---

## ⚠️ 依赖说明

本代码平台基于以下假设：
1. DUSt3R 官方代码已安装（`dust3r` 包可导入）
2. PyTorch >= 2.0
3. 量化需要：`torch.ao.quantization` 或 `nvidia-modelopt`（TensorRT）

如环境不满足，需先配置环境。
