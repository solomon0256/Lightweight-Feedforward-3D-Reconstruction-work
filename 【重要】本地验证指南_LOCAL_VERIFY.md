# 【重要】本地验证指南

> **目的**：在服务器上运行之前，先在本地验证所有脚本能正常工作  
> **原则**：本地调试代码逻辑，服务器只负责计算

---

## 核心思路

```
┌─────────────────────────────────────────────────────────────┐
│                      本地电脑                                │
│                                                             │
│   1. 写代码                                                 │
│   2. 本地验证（跑1步，验证代码逻辑）                         │
│   3. 验证通过 → git push                                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      服务器                                  │
│                                                             │
│   1. git pull                                               │
│   2. 运行完整轻量化（跑100步/epochs）                        │
│   3. 收集结果                                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 为什么"跑1步"就够了？

轻量化代码的特点是：**每一步的逻辑完全一样，只是重复执行。**

```python
# 剪枝的循环
for step in range(100):
    weights = select_weights()      # 选权重
    importance = calc_importance()  # 算重要性
    prune(weights, importance)      # 剪掉不重要的
    # ↑ 每一步都是同样的代码
```

**如果第1步能跑通，第100步也能跑通。**

| 错误类型 | 第1步能发现吗 | 说明 |
|---------|-------------|------|
| 语法错误 | ✅ 能 | 第1步就报错 |
| API用法错误 | ✅ 能 | 第1步就报错 |
| 维度不匹配 | ✅ 能 | 第1步就报错 |
| 文件路径错误 | ✅ 能 | 第1步就报错 |
| 显存不足 | ⚠️ 不一定 | 服务器显存更大，问题更少 |
| 训练发散 | ❌ 不能 | 这是调参问题，不是代码bug |

---

## 本地验证步骤

### 第一步：环境检查

```powershell
# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 检查 PyTorch 和 CUDA
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}')"
```

### 第二步：验证模型能加载

```powershell
python -c "
import sys
sys.path.insert(0, 'third_party/dust3r')
sys.path.insert(0, 'third_party/dust3r/croco')
from dust3r.model import AsymmetricCroCo3DStereo
model = AsymmetricCroCo3DStereo.from_pretrained('naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt')
print('✅ 模型加载成功')
print(f'参数量: {sum(p.numel() for p in model.parameters()):,}')
"
```

### 第三步：验证轻量化脚本（重点）

**剪枝验证：**
```powershell
# --test 模式：只跑1步，验证代码逻辑
python scripts/prune.py --config expconfigs/prune.yaml --test
```

**量化验证：**
```powershell
python scripts/quantize.py --config expconfigs/quant.yaml --test
```

**蒸馏验证：**
```powershell
python scripts/train_distill.py --config expconfigs/distill.yaml --test
```

**联合训练验证：**
```powershell
python scripts/train_joint.py --config expconfigs/joint_pqk.yaml --test
```

### 第四步：确认所有验证通过

```
✅ 环境检查通过
✅ 模型加载成功
✅ 剪枝脚本验证通过
✅ 量化脚本验证通过
✅ 蒸馏脚本验证通过
✅ 联合训练脚本验证通过

→ 可以 git push，然后在服务器运行完整流程
```

---

## 服务器运行（完整计算）

本地验证全部通过后，在服务器上：

```bash
# 正式运行（不带 --test）
python scripts/prune.py --config expconfigs/prune.yaml
python scripts/quantize.py --config expconfigs/quant.yaml
python scripts/train_distill.py --config expconfigs/distill.yaml
```

---

## --test 模式做了什么？

| 参数 | 正常模式 | --test 模式 |
|------|---------|-------------|
| epochs | 100 | 1 |
| steps | 全部 | 1-2 |
| 数据量 | 全部 | 1-2张图 |
| 保存模型 | 是 | 可选 |
| 验证目的 | 获得结果 | 验证代码能跑 |

---

## 常见问题

### Q: 本地验证通过了，服务器还会出错吗？

**A:** 代码逻辑层面的错误不会再出现。可能出现的问题：
- 路径不同（已通过配置文件解决）
- 训练不收敛（调参问题，不是代码bug）

### Q: 为什么不在本地跑完整流程？

**A:** 
1. 本地显存不够（6GB vs 服务器24GB+）
2. 本地算力慢，跑完整流程要很久
3. 服务器按小时收费，应该只用来做"计算"，不用来"调试"

### Q: 我怎么知道验证通过了？

**A:** 脚本会输出：
```
[TEST MODE] 验证完成
✅ 剪枝逻辑正确
✅ 模型保存成功
✅ 可以在服务器运行完整流程
```

---

## 一句话总结

> **本地跑 `--test` 验证代码能跑通 → 服务器跑完整参数获得结果**
> 
> 省钱、省时间、减少在服务器上调试的痛苦。

---

*最后更新: 2025-12-23*
