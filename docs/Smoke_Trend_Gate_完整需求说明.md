# Smoke Gate 和 Trend Gate 完整需求说明

> **创建日期**: 2025-12-27  
> **来源**: 用户明确需求  
> **目的**: 详细记录两个验证门禁的完整需求和改进方向

---

## 🎯 核心目标

### 总体目标

在工作电脑（性能不高）上，通过两个验证门禁，确保轻量化后的模型：
1. **能够正确运行**（Smoke Gate）
2. **性能下降在可接受范围内**（Trend Gate）

**关键约束**：
- 运行环境：工作电脑（性能不高）
- 运行时间：不能太长（Smoke Gate: 2-5分钟，Trend Gate: 30-60分钟）
- 验证对象：**轻量化后的模型**（不是验证脚本本身）
- 验证范围：**三种轻量化方法**（蒸馏 K、量化 Q、剪枝 P）

---

## 📋 第一个门禁：Smoke Gate（轻量化正确性验证）

### 1.1 核心目的

**验证轻量化后的模型能否在服务器上正确运行到底**

不是验证脚本本身，而是要：
- **运行轻量化后的模型**
- **验证模型输出是否正确**
- **确保模型不会在服务器上崩溃**

### 1.2 验证内容

#### 必须验证的项目

1. **轻量化过程验证**（新增）
   - ✅ 蒸馏（K）：Student 模型能否成功加载和运行
   - ✅ 量化（Q）：量化过程是否成功，量化后模型能否运行
   - ✅ 剪枝（P）：剪枝过程是否成功，剪枝后模型能否运行

2. **Schema 断言**（已有）
   - 输出字段、dtype、shape 是否正确
   - 必需字段是否存在

3. **Golden 对比**（已有）
   - 与 baseline 输出对比，确保数值一致性
   - 不同方法有不同的容差（FP16 严格，INT8 宽松）

4. **稳定性检查**（已有）
   - NaN/Inf 率必须为 0
   - 崩溃率必须为 0
   - 断言失败率必须为 0

### 1.3 运行环境要求

- **设备**：工作电脑（性能不高）
- **数据规模**：16 对样本（Smoke Set）
- **运行时间**：2-5 分钟
- **验证对象**：轻量化后的模型（蒸馏/量化/剪枝后的模型）

### 1.4 支持的轻量化方法

| 方法 | 代码 | 验证内容 |
|------|------|----------|
| **蒸馏** | K | Student 模型加载、运行、输出格式 |
| **量化** | Q | 量化过程、量化后模型运行、输出格式 |
| **剪枝** | P | 剪枝过程、剪枝后模型运行、输出格式 |

### 1.5 使用示例

```bash
# 验证蒸馏后的模型
python scripts/smoke_gate.py --method K --variant student --checkpoint student.pth

# 验证量化后的模型（FP16）
python scripts/smoke_gate.py --method Q --variant fp16

# 验证量化后的模型（INT8）
python scripts/smoke_gate.py --method Q --variant int8 --checkpoint quantized.pth

# 验证剪枝后的模型
python scripts/smoke_gate.py --method P --variant pruned_40 --flops-reduction 40 --checkpoint pruned.pth
```

---

## 📊 第二个门禁：Trend Gate（性能下降检测）

### 2.1 核心目的

**保证轻量化后模型的输出效能是合理的**

验证：
- 精度下降是否在可接受范围内
- 性能变化是否合理
- 不同轻量化方法的输出是否满足要求

### 2.2 验证内容

#### 必须验证的项目

1. **精度护栏**（已有，需改进）
   - absrel、delta1、visloc_acc 的下降阈值
   - **需要支持分段/非线性阈值**（见 2.4）

2. **性能护栏**（已有）
   - 延迟变化（量化/剪枝应该降低延迟）
   - 显存变化（量化应该降低显存）
   - 延迟方差（不能太大）

3. **不同方法的阈值**（已有，需改进）
   - 蒸馏：按训练阶段分段阈值
   - 量化：按量化精度（FP16/INT8）不同阈值
   - 剪枝：按剪枝率分段阈值

### 2.3 运行环境要求

- **设备**：工作电脑（性能不高）
- **数据规模**：200 对样本（Trend Set）
- **运行时间**：30-60 分钟
- **验证对象**：轻量化后的模型（蒸馏/量化/剪枝后的模型）

### 2.4 阈值配置要求（重要改进）

#### 当前问题

- ❌ 阈值是固定的（如 50%）
- ❌ 没有考虑不同阶段的不同要求
- ❌ 没有考虑不同场景（蒸馏/量化/剪枝）的差异

#### 改进要求

**1. 分段阈值（按训练阶段/压缩率）**

例如蒸馏：
- **第一阶段**（前 10% 训练）：允许较大下降（90-95% 保持）
  - absrel 上升 < 5%
  - delta1 下降 < 2%
- **第二阶段**（10%-50% 训练）：中等要求（90% 保持）
  - absrel 上升 < 3%
  - delta1 下降 < 1.5%
- **第三阶段**（50%-100% 训练）：严格要求（接近 baseline）
  - absrel 上升 < 1%
  - delta1 下降 < 1%

**2. 非线性阈值（按压缩率）**

例如剪枝：
- **剪枝 20% FLOPs**：delta1 下降 < 2%
- **剪枝 40% FLOPs**：delta1 下降 < 3%
- **剪枝 60% FLOPs**：delta1 下降 < 5%

**3. 不同场景不同阈值**

- **蒸馏**：一开始消耗大，后面会小（阈值从宽松到严格）
- **量化**：FP16 严格，INT8 宽松
- **剪枝**：按剪枝率线性/非线性调整

### 2.5 阈值配置格式（建议）

```yaml
guardrails:
  accuracy:
    # 蒸馏：按训练进度分段
    distillation:
      stages:
        - progress_range: [0, 0.1]      # 第一阶段
          absrel_max_increase_pct: 5.0
          delta1_max_decrease_pct: 2.0
          visloc_acc_max_decrease_pct: 3.0
        - progress_range: [0.1, 0.5]    # 第二阶段
          absrel_max_increase_pct: 3.0
          delta1_max_decrease_pct: 1.5
          visloc_acc_max_decrease_pct: 2.0
        - progress_range: [0.5, 1.0]    # 第三阶段
          absrel_max_increase_pct: 1.0
          delta1_max_decrease_pct: 1.0
          visloc_acc_max_decrease_pct: 1.0
    
    # 量化：按量化精度
    quantization:
      fp16:
        absrel_max_increase_pct: 1.0
        delta1_max_decrease_pct: 1.0
      int8_ptq:
        absrel_max_increase_pct: 10.0
        delta1_max_decrease_pct: 3.0
      int8_qat:
        absrel_max_increase_pct: 5.0
        delta1_max_decrease_pct: 2.0
    
    # 剪枝：按剪枝率（非线性）
    pruning:
      # 线性插值或分段配置
      flops_reduction_thresholds:
        - flops_reduction_pct: 20
          absrel_max_increase_pct: 5.0
          delta1_max_decrease_pct: 2.0
        - flops_reduction_pct: 40
          absrel_max_increase_pct: 8.0
          delta1_max_decrease_pct: 3.0
        - flops_reduction_pct: 60
          absrel_max_increase_pct: 12.0
          delta1_max_decrease_pct: 5.0
```

### 2.6 使用示例

```bash
# 验证蒸馏后的模型（指定训练进度）
python scripts/trend_gate.py --method K --variant student --progress 0.2 --checkpoint student_epoch10.pth

# 验证量化后的模型
python scripts/trend_gate.py --method Q --variant fp16

# 验证剪枝后的模型（指定剪枝率）
python scripts/trend_gate.py --method P --variant pruned_40 --flops-reduction 40 --checkpoint pruned.pth
```

---

## 🔧 需要实现的功能

### 功能 1: 轻量化过程验证（Smoke Gate）

**位置**: `scripts/smoke_gate.py`

**功能**:
```python
def verify_lightweighting_process(method: str, variant: str, model, 
                                 checkpoint_path: str = None) -> Tuple[bool, str]:
    """
    验证轻量化过程是否成功
    
    Args:
        method: 'K' (蒸馏), 'Q' (量化), 'P' (剪枝)
        variant: 变体名称
        model: 原始模型或轻量化后的模型
        checkpoint_path: checkpoint 路径
    
    Returns:
        (success, error_message)
    """
    if method == 'K':  # 蒸馏
        # 1. 检查 student 模型 checkpoint 是否存在
        # 2. 尝试加载 student 模型
        # 3. 检查 student 模型结构是否正确
        # 4. 检查 student 模型能否运行推理
        pass
    elif method == 'Q':  # 量化
        # 1. 检查量化过程是否成功（如果提供了量化后的模型）
        # 2. 检查量化后模型格式
        # 3. 检查量化兼容性（模型结构是否支持量化）
        pass
    elif method == 'P':  # 剪枝
        # 1. 检查剪枝过程是否成功
        # 2. 检查剪枝后模型结构
        # 3. 检查剪枝率是否符合预期
        pass
```

### 功能 2: 分段阈值配置（Trend Gate）

**位置**: `config/eval_contract.yaml` + `scripts/utils/threshold_loader.py`

**功能**:
```python
def get_threshold_for_stage(method: str, variant: str, 
                           progress: float = None, 
                           flops_reduction: float = None) -> Dict:
    """
    根据方法、阶段、压缩率获取对应阈值
    
    Args:
        method: 'K' (蒸馏), 'Q' (量化), 'P' (剪枝)
        variant: 变体名称
        progress: 训练进度 (0-1)，用于蒸馏
        flops_reduction: FLOPs 减少百分比，用于剪枝
    
    Returns:
        阈值字典
    """
    # 1. 从 eval_contract.yaml 读取配置
    # 2. 根据 progress 或 flops_reduction 查找对应阶段的阈值
    # 3. 支持线性插值（如果配置了多个阶段）
    # 4. 返回阈值字典
```

### 功能 3: 更新 Trend Gate 检查逻辑

**位置**: `scripts/trend_gate.py`

**修改**:
```python
def check_accuracy_guardrails(self, current_metrics, method_type: str,
                             progress: float = None, 
                             flops_reduction: float = None):
    """
    精度护栏检查（支持分段阈值）
    
    Args:
        progress: 训练进度（用于蒸馏）
        flops_reduction: FLOPs 减少百分比（用于剪枝）
    """
    # 1. 使用 threshold_loader 获取对应阶段的阈值
    # 2. 根据 progress 或 flops_reduction 选择阈值
    # 3. 执行检查
```

---

## 📝 工作流程

### 完整验证流程

```
1. 完成轻量化（蒸馏/量化/剪枝）
   ↓
2. Smoke Gate 验证（2-5分钟）
   - 验证轻量化过程是否成功
   - 验证模型输出格式正确
   - 验证模型能正常运行
   ↓
3. Trend Gate 验证（30-60分钟）
   - 根据训练进度/压缩率选择阈值
   - 验证精度下降是否在阈值内
   - 验证性能变化是否合理
   ↓
4. 通过后上服务器跑 Final Set
```

### 不同轻量化方法的验证

#### 蒸馏（K）

```bash
# 训练过程中验证（按训练进度）
python scripts/trend_gate.py --method K --variant student --progress 0.1 --checkpoint student_epoch5.pth
python scripts/trend_gate.py --method K --variant student --progress 0.5 --checkpoint student_epoch15.pth
python scripts/trend_gate.py --method K --variant student --progress 1.0 --checkpoint student_final.pth
```

#### 量化（Q）

```bash
# FP16 量化
python scripts/smoke_gate.py --method Q --variant fp16
python scripts/trend_gate.py --method Q --variant fp16

# INT8 量化
python scripts/smoke_gate.py --method Q --variant int8 --checkpoint quantized_int8.pth
python scripts/trend_gate.py --method Q --variant int8 --checkpoint quantized_int8.pth
```

#### 剪枝（P）

```bash
# 剪枝 40% FLOPs
python scripts/smoke_gate.py --method P --variant pruned_40 --flops-reduction 40 --checkpoint pruned_40.pth
python scripts/trend_gate.py --method P --variant pruned_40 --flops-reduction 40 --checkpoint pruned_40.pth
```

---

## ✅ 完成标准

### Smoke Gate 完成标准

- [x] 支持三种轻量化方法（K/Q/P）的验证
- [x] 验证轻量化过程是否成功
- [x] 验证模型输出格式正确
- [x] 验证模型能正常运行
- [ ] **新增**：验证轻量化过程本身（能否成功进行轻量化）

### Trend Gate 完成标准

- [x] 支持精度护栏检查
- [x] 支持性能护栏检查
- [x] 支持不同方法的阈值配置
- [ ] **新增**：支持分段阈值（按训练进度/压缩率）
- [ ] **新增**：支持非线性阈值（按压缩率曲线）

---

## 📚 相关文档

- [PQK_验证机制_两道门禁.md](./PQK_验证机制_两道门禁.md) - 原始设计文档
- [Smoke_Trend_Gate_功能覆盖分析.md](./Smoke_Trend_Gate_功能覆盖分析.md) - 功能覆盖分析
- [下一步任务清单.md](./下一步任务清单.md) - 任务清单

---

*文档版本: v2.0 | 最后更新: 2025-12-27*

