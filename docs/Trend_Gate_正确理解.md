# Trend Gate 的正确理解

> **修正日期**: 2025-12-27  
> **目的**: 纠正对 Trend Gate 的理解

---

## ❌ 错误理解

**之前认为**：
- Trend Gate 需要根据训练进度/压缩率动态调整阈值
- 不同阶段有不同的阈值（第一阶段宽松，第二阶段中等，第三阶段严格）

**问题**：
- 这不是 Trend Gate 的目的
- 我们关心的是**最终性能**，不是训练过程中的性能

---

## ✅ 正确理解

### Trend Gate 的本质

**用小规模数据预测大规模数据的结果**

- **小规模数据**：200 对样本（Trend Set）
- **大规模数据**：1000 对样本（Final Set）
- **目的**：如果 200 对的结果不好，那么 1000 对的结果也不会好

### 阈值应该是固定的

**阈值针对的是最终结果，不是训练过程**

- 阈值应该基于：**最终 1000 对样本的预期结果**
- 不是基于：训练进度或压缩率

### 工作流程

```
1. 定义最终性能阈值（基于 baseline 和预期）
   ├─ absrel 上升 < 10%
   ├─ delta1 下降 < 3%
   └─ visloc_acc 下降 < 5%

2. 在 200 对样本上运行轻量化后的模型
   ├─ 计算精度指标
   └─ 计算性能指标

3. 检查是否在阈值内
   ├─ 如果 200 对的结果在阈值内 → 预测 1000 对也会在阈值内
   └─ 如果 200 对的结果超出阈值 → 预测 1000 对也会超出阈值

4. 决策
   ├─ 通过 → 上服务器跑 1000 对
   └─ 失败 → 调整参数，重新验证
```

---

## 🔧 正确的实现思路

### 1. 阈值配置（固定）

```yaml
guardrails:
  accuracy:
    # 最终性能阈值（固定）
    final_thresholds:
      absrel_max_increase_pct: 10.0
      delta1_max_decrease_pct: 3.0
      visloc_acc_max_decrease_pct: 5.0
    
    # 不同方法可能有不同的阈值（但都是针对最终结果）
    distillation:
      absrel_max_increase_pct: 5.0   # 蒸馏要求更严格
      delta1_max_decrease_pct: 2.0
    quantization:
      fp16:
        absrel_max_increase_pct: 1.0  # FP16 要求最严格
        delta1_max_decrease_pct: 1.0
      int8_ptq:
        absrel_max_increase_pct: 10.0 # INT8 允许更大下降
        delta1_max_decrease_pct: 3.0
    pruning:
      absrel_max_increase_pct: 8.0    # 剪枝允许中等下降
      delta1_max_decrease_pct: 3.0
```

### 2. Trend Gate 检查逻辑

```python
def check_accuracy_guardrails(self, current_metrics, method_type):
    """
    精度护栏检查（固定阈值）
    
    逻辑：
    1. 根据方法类型获取固定阈值
    2. 计算当前指标（200对样本）与 baseline 的差异
    3. 检查是否在阈值内
    4. 如果通过，预测 1000 对样本也会在阈值内
    """
    # 获取固定阈值（针对最终结果）
    thresholds = self.get_final_thresholds(method_type)
    
    # 检查 absrel
    baseline_absrel = self.baseline_ref['depth']['absrel']
    current_absrel = current_metrics['absrel']
    increase_pct = (current_absrel - baseline_absrel) / baseline_absrel * 100
    
    if increase_pct > thresholds['absrel_max_increase_pct']:
        return False, f"200对样本上 absrel 上升 {increase_pct:.2f}%，预测1000对也会超出阈值"
    
    # 检查 delta1
    # ... 类似逻辑
    
    return True, "200对样本结果在阈值内，预测1000对也会在阈值内"
```

---

## 🎯 关键区别

### 错误理解 vs 正确理解

| 方面 | 错误理解 | 正确理解 |
|------|---------|---------|
| **阈值来源** | 根据训练进度/压缩率动态调整 | 固定阈值（针对最终结果） |
| **验证对象** | 训练过程中的性能 | 最终性能（1000对样本） |
| **预测目标** | 训练趋势 | 大规模数据结果 |
| **阈值变化** | 不同阶段不同阈值 | 不同方法不同阈值（但都是固定的） |

---

## 💡 重新理解两个门禁

### Smoke Gate（正确性验证）

**目的**：验证轻量化后的模型能否正常运行

**验证内容**：
- 模型能否加载
- 模型能否运行推理
- 输出格式是否正确
- 输出数值是否合理

**不关心**：性能好坏，只关心能否运行

---

### Trend Gate（趋势预测）

**目的**：用 200 对样本预测 1000 对样本的结果

**验证内容**：
- 在 200 对样本上计算精度和性能指标
- 与 baseline 对比
- 检查是否在固定阈值内
- 如果通过，预测 1000 对也会在阈值内

**关心**：最终性能，用小规模数据预测大规模数据

---

## 🔧 实现要点

### 1. 阈值应该是固定的

- 不同方法（K/Q/P）可能有不同的阈值
- 但每个方法的阈值是固定的（不随训练进度变化）

### 2. 预测逻辑

- 如果 200 对样本的结果在阈值内 → 预测 1000 对也会在阈值内
- 如果 200 对样本的结果超出阈值 → 预测 1000 对也会超出阈值

### 3. 不需要分段阈值

- 不需要根据训练进度调整阈值
- 不需要根据压缩率调整阈值
- 只需要固定的最终性能阈值

---

## 📋 正确的配置格式

```yaml
guardrails:
  accuracy:
    # 蒸馏：固定阈值（针对最终结果）
    distillation:
      absrel_max_increase_pct: 5.0
      delta1_max_decrease_pct: 2.0
      visloc_acc_max_decrease_pct: 3.0
    
    # 量化：固定阈值（针对最终结果）
    quantization:
      fp16:
        absrel_max_increase_pct: 1.0
        delta1_max_decrease_pct: 1.0
      int8_ptq:
        absrel_max_increase_pct: 10.0
        delta1_max_decrease_pct: 3.0
    
    # 剪枝：固定阈值（针对最终结果）
    pruning:
      absrel_max_increase_pct: 8.0
      delta1_max_decrease_pct: 3.0
```

---

*修正完成时间: 2025-12-27*

