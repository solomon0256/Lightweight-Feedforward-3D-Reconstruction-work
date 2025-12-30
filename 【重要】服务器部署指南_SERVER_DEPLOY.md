# 🚀 服务器部署与还原指南

> **当前阶段**: Baseline 验证完成  
> **最后更新**: 2025-12-23  
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

### 步骤 4: 执行任务

根据当前阶段执行相应任务...

### 步骤 5: 保存工作

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

### 步骤 6: 销毁服务器

确认 `git push` 成功后，可以安全销毁服务器实例。

---

## 📁 项目结构

```
Lightweight-Feedforward-3D-Reconstruction-work/
├── SERVER_DEPLOY.md          # 👈 本文件 (服务器部署指南)
├── scripts/
│   ├── setup_server.sh       # 服务器一键设置
│   ├── test_dust3r_baseline.py  # Baseline 验证
│   ├── download_weights.py   # 下载模型权重
│   ├── prune.py              # 剪枝脚本
│   ├── quantize.py           # 量化脚本
│   └── train_distill.py      # 蒸馏训练
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
| Phase 1: 剪枝 | ⏳ 待开始 | - |
| Phase 2: 量化 | ⏳ 待开始 | - |
| Phase 3: 蒸馏 | ⏳ 待开始 | - |
| Phase 4: 联合优化 | ⏳ 待开始 | - |
| Phase 5: 评测 | ⏳ 待开始 | - |

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
