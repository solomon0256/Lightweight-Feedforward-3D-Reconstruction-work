# DUSt3R 环境依赖调研

> 调研时间: 2025-12-22
> 来源: https://github.com/naver/dust3r

---

## � 工作环境说明

**本项目分为两个环境：**

| 环境 | 用途 | 系统 | GPU |
|-----|------|------|-----|
| 开发机（本机） | 写脚本、验证语法 | Windows | 不需要 |
| 运行机（云服务器） | 实际跑实验 | Linux | 高算力 GPU |

**因此：**
- 本机不安装 PyTorch/CUDA
- 只验证 Python 语法
- 准备好配置文件，部署到云服务器时使用

---

## �📋 官方要求摘要

### Python 版本
```
Python 3.11
```
（官方示例使用 conda create -n dust3r python=3.11）

### PyTorch 版本
```
pytorch-cuda=12.1  (CUDA 12.1)
```
（官方: `conda install pytorch torchvision pytorch-cuda=12.1 -c pytorch -c nvidia`）

### 核心依赖 (requirements.txt)
```
torch
torchvision
roma
gradio
matplotlib
tqdm
opencv-python
scipy
einops
trimesh
tensorboard
pyglet<2
huggingface-hub[torch]>=0.22
```

### 可选依赖 (requirements_optional.txt)
- HEIC 图像支持
- pyrender (深度图渲染)
- visloc 相关包

---

## ⚠️ 当前环境问题

### 当前 .venv 环境
- Python: **3.13.6** ❌ (官方要求 3.11)
- PyTorch: **未安装** ❌
- CUDA: **未确定**

### 问题分析
1. Python 版本过高 (3.13 vs 3.11)
   - 可能存在兼容性问题
   - 某些依赖可能不支持 Python 3.13

2. 需要确认本机 CUDA 版本
   - 决定安装哪个版本的 PyTorch

---

## 🔧 建议的环境搭建步骤

### 方案 A: 使用 Conda (推荐，与官方一致)
```bash
# 1. 创建新环境
conda create -n dust3r python=3.11 cmake=3.14.0
conda activate dust3r

# 2. 安装 PyTorch (根据本机 CUDA 版本选择)
# CUDA 12.1:
conda install pytorch torchvision pytorch-cuda=12.1 -c pytorch -c nvidia
# CUDA 11.8:
conda install pytorch torchvision pytorch-cuda=11.8 -c pytorch -c nvidia

# 3. 克隆 DUSt3R (作为子模块或单独目录)
git clone --recursive https://github.com/naver/dust3r
cd dust3r

# 4. 安装依赖
pip install -r requirements.txt
```

### 方案 B: 使用 venv + pip (当前状态)
```bash
# 1. 需要先安装 Python 3.11
# 2. 删除当前 .venv，重建
python3.11 -m venv .venv

# 3. 安装 PyTorch
# 查看: https://pytorch.org/get-started/locally/
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# 4. 安装其他依赖
pip install roma gradio matplotlib tqdm opencv-python scipy einops trimesh tensorboard pyglet huggingface-hub
```

---

## 📌 下一步行动

在继续任何代码工作之前，必须：

1. [ ] 确认本机 CUDA 版本 (`nvidia-smi`)
2. [ ] 决定使用 Conda 还是 venv
3. [ ] 安装正确版本的 Python (3.11)
4. [ ] 安装匹配的 PyTorch
5. [ ] 克隆/获取 DUSt3R 官方代码
6. [ ] 验证 DUSt3R 能正常导入

---

## 📊 总结

| 项目 | 官方要求 | 当前状态 | 需要操作 |
|-----|---------|---------|---------|
| Python | 3.11 | 3.13.6 | ⚠️ 降级 |
| PyTorch | pytorch-cuda=12.1 | 未安装 | ❌ 安装 |
| CUDA | 12.1 | 未确认 | ❓ 检查 |
| DUSt3R | 需要克隆 | 无 | ❌ 克隆 |

**结论**: 当前环境不具备运行 DUSt3R 的条件，需要重新搭建。
