# 🚀 服务器部署与还原指南

> **当前阶段**: 轻量化验证脚本完成，准备服务器运行  
> **最后更新**: 2025-12-29  
> **状态**: ✅ 可部署

---

## ⚡ 快速还原 (复制粘贴即可)

```bash
# 1. 克隆项目 (包含 submodule)
git clone --recursive https://github.com/solomon0256/Lightweight-Feedforward-3D-Reconstruction-work.git
cd Lightweight-Feedforward-3D-Reconstruction-work

# 2. 一键设置环境
bash scripts/setup_server.sh

# 3. 验证 baseline
python scripts/test_dust3r_baseline.py --device cuda
```

**预期输出**: `✅ BASELINE 验证通过！`

---

## 📋 工作流程

```
┌─────────────────────────────────────────────────────────────┐
│                      服务器工作流程                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 创建服务器实例 (A100/RTX 4090)                           │
│           │                                                 │
│           ▼                                                 │
│  2. 还原项目 (git clone --recursive)                        │
│           │                                                 │
│           ▼                                                 │
│  3. 运行 setup_server.sh                                    │
│           │                                                 │
│           ▼                                                 │
│  4. 验证 baseline (test_dust3r_baseline.py)                 │
│           │                                                 │
│           ▼                                                 │
│  5. 执行任务 (训练/评测/实验)                                 │
│           │                                                 │
│           ▼                                                 │
│  6. 保存结果 (git add/commit/push)                          │
│           │                                                 │
│           ▼                                                 │
│  7. 销毁服务器实例                                           │
│           │                                                 │
│           ▼                                                 │
│  (下次任务时重复 1-7)                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 详细步骤

### 步骤 1: 克隆项目

```bash
git clone --recursive https://github.com/solomon0256/Lightweight-Feedforward-3D-Reconstruction-work.git
cd Lightweight-Feedforward-3D-Reconstruction-work
```

> ⚠️ **必须加 `--recursive`**，否则 dust3r 和 croco submodule 不会下载！

如果忘记加 `--recursive`，补救方法：
```bash
git submodule update --init --recursive
```

### 步骤 2: 安装环境

```bash
# 方法 A: 使用一键脚本 (推荐)
bash scripts/setup_server.sh

# 方法 B: 手动安装
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
```

### 步骤 3: 验证 Baseline

```bash
python scripts/test_dust3r_baseline.py --device cuda
```

**正常输出**:
```
✅ BASELINE 验证通过！

📊 测试结果:
  模型参数: 571.2M
  推理时间: ~0.5s (A100) / ~1.8s (RTX 3060)
  峰值显存: 2.77 GB
```

### 步骤 4: 本地验证（在本地工作站执行）

**⚠️ 重要：在服务器运行完整轻量化前，先在本地验证代码正确性！**

#### 4.1 验证轻量化可行性

```bash
# 验证蒸馏、量化、剪枝能否成功运行
python scripts/verify_lightweight_feasibility.py
```

**预期输出**:
```
[PASS] 蒸馏验证通过
[PASS] 量化验证通过
[PASS] 剪枝验证通过
```

#### 4.2 验证性能预测

```bash
# 预测轻量化后的性能指标
python scripts/verify_performance.py
```

**预期输出**:
```
参数量: 285.6M (压缩比: 0.50)
推理时间: 180ms (加速比: 1.96)
稀疏度: 40.0%
```

#### 4.3 运行Smoke Gate和Trend Gate

```bash
# Smoke Gate: 快速正确性检查
python scripts/smoke_gate.py

# Trend Gate: 性能趋势检查
python scripts/trend_gate.py
```

**全部通过后，推送到GitHub**:
```bash
git add .
git commit -m "local validation passed"
git push
```

### 步骤 5: 服务器运行轻量化（在服务器执行）

**在服务器上克隆最新代码后，运行完整轻量化流程：**

#### 5.1 蒸馏训练 (K-only)

```bash
# 完整蒸馏训练
python scripts/train_distill.py --exp-config expconfigs/distill.yaml

# 或使用dry-run快速测试（仅用于验证）
python scripts/train_distill.py --exp-config expconfigs/distill.yaml --dry-run --max-epochs 2
```

**输出**: `outputs/checkpoints/student_fp32_best.pth`

#### 5.2 量化 (Q-only 或 K→Q)

```bash
# PTQ量化（快速）
python scripts/quantize.py --exp-config expconfigs/quant.yaml --mode ptq

# QAT量化（精度更高，需要训练）
python scripts/quantize.py --exp-config expconfigs/quant.yaml --mode qat

# 如果接在蒸馏后，指定student权重
python scripts/quantize.py --exp-config expconfigs/quant.yaml --mode ptq \
    --model-weights outputs/checkpoints/student_fp32_best.pth
```

**输出**: `outputs/checkpoints/quantized_int8.pth`

#### 5.3 剪枝 (P-only 或 K→P)

```bash
# 剪枝（使用student模型）
python scripts/prune.py --exp-config expconfigs/prune.yaml \
    --model-weights outputs/checkpoints/student_fp32_best.pth

# 或剪枝baseline模型
python scripts/prune.py --exp-config expconfigs/prune.yaml
```

**输出**: `outputs/checkpoints/pruned_40pct.pth`

#### 5.4 联合训练 (PQK)

```bash
# 联合训练（蒸馏+量化+剪枝）
python scripts/train_joint.py --config expconfigs/joint_pqk.yaml
```

### 步骤 6: 性能评估

```bash
# 评估轻量化后的模型性能
python scripts/baseline_eval.py --config config/eval.yaml \
    --model-path outputs/checkpoints/student_fp32_best.pth
```

**评估指标**:
- 参数量 (M)
- 推理时间 (ms)
- VisLoc精度 (cm)
- VRAM使用 (GB)

### 步骤 7: 保存工作

**任务完成后，务必保存所有结果到 GitHub！**

```bash
# 查看修改了什么
git status

# 添加所有修改
git add .

# 提交 (写清楚做了什么)
git commit -m "exp: [任务描述]"

# 推送到 GitHub
git push
```

### 步骤 8: 销毁服务器

确认 `git push` 成功后，可以安全销毁服务器实例。

---

## 📁 项目结构

```
Lightweight-Feedforward-3D-Reconstruction-work/
├── SERVER_DEPLOY.md          # 👈 本文件 (服务器部署指南)
├── scripts/
│   ├── setup_server.sh       # 服务器一键设置
│   ├── test_dust3r_baseline.py  # Baseline 验证
│   ├── verify_lightweight_feasibility.py  # 轻量化可行性验证
│   ├── verify_performance.py  # 性能预测验证
│   ├── smoke_gate.py        # Smoke Gate验证
│   ├── trend_gate.py         # Trend Gate验证
│   ├── prune.py              # 剪枝脚本
│   ├── quantize.py           # 量化脚本
│   ├── train_distill.py      # 蒸馏训练
│   └── train_joint.py        # 联合训练
├── third_party/
│   └── dust3r/               # DUSt3R 代码 (submodule)
│       └── croco/            # CRoCo 代码 (nested submodule)
├── checkpoints/              # 模型权重 (运行时下载)
├── outputs/                  # 实验输出
├── logs/                     # 日志
├── worklogs/                 # 工作日志
└── docs/                     # 文档
```

---

## 🎯 当前进度

| 阶段 | 状态 | 说明 |
|------|------|------|
| Phase 0: Baseline | ✅ 完成 | DUSt3R 571.2M, GPU 验证通过 |
| Phase 0.5: 验证脚本 | ✅ 完成 | 轻量化验证脚本已实现并测试通过 |
| Phase 1: 剪枝 | ✅ 脚本就绪 | `prune.py` 已实现，支持dry-run |
| Phase 2: 量化 | ✅ 脚本就绪 | `quantize.py` 已实现，支持PTQ/QAT |
| Phase 3: 蒸馏 | ✅ 脚本就绪 | `train_distill.py` 已实现，支持dry-run |
| Phase 4: 联合优化 | ✅ 脚本就绪 | `train_joint.py` 已实现 |
| Phase 5: 服务器运行 | ⏳ 待开始 | 等待在服务器上运行完整流程 |

---

## ⚠️ 注意事项

1. **每次任务结束必须 git push** - 服务器销毁后数据全部丢失！
2. **checkpoints/ 不会上传** - 模型权重会自动从 HuggingFace 下载
3. **outputs/ 中的重要结果需要手动保存** - 添加到 git 或下载到本地
4. **大文件使用 Git LFS** - 超过 100MB 的文件需要 LFS

---

## 🆘 常见问题

### Q: submodule 为空？
```bash
git submodule update --init --recursive
```

### Q: CUDA 不可用？
```bash
pip uninstall torch torchvision -y
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
```

### Q: 模型加载失败 "No module named 'models.dpt_block'"？
脚本会自动处理，如果仍然失败：
```bash
touch third_party/dust3r/croco/models/__init__.py
```

### Q: 如何查看 GPU 状态？
```bash
nvidia-smi
python -c "import torch; print(torch.cuda.is_available())"
```

---

## 📞 联系

如有问题，查看 `docs/` 目录下的详细文档，或检查 `worklogs/` 中的历史记录。
