# DUSt3R Baseline 手动还原指南

## 概述

本文档记录在云服务器上手动还原 DUSt3R baseline 的完整步骤。
**原则：先手动验证每一步，再考虑自动化。**

---

## 前置条件

### 硬件要求
- GPU: NVIDIA A100 / RTX 3090 / RTX 4090（推荐 ≥24GB 显存）
- RAM: ≥32GB
- 存储: ≥50GB（模型 + 数据集）

### 软件要求
- Ubuntu 20.04 / 22.04
- CUDA 12.1+
- Python 3.11

---

## 步骤 1: 环境准备

### 1.1 创建 Conda 环境

```bash
# 创建新环境
conda create -n dust3r python=3.11 -y
conda activate dust3r

# 安装 PyTorch with CUDA 12.1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

### 1.2 验证 CUDA

```bash
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}'); print(f'Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"
```

**预期输出：**
```
PyTorch: 2.x.x+cu121
CUDA: True
Device: NVIDIA A100-SXM4-40GB
```

---

## 步骤 2: 克隆代码

### 2.1 克隆项目仓库

```bash
# 克隆我们的项目
git clone https://github.com/<your-repo>/Lightweight-Feedforward-3D-Reconstruction-work.git
cd Lightweight-Feedforward-3D-Reconstruction-work

# DUSt3R 已作为 submodule 存在于 third_party/dust3r/
# 如果是新克隆，需要初始化 submodule
git submodule update --init --recursive
```

### 2.2 安装 DUSt3R 依赖

```bash
# 安装 DUSt3R 的依赖
pip install -r third_party/dust3r/requirements.txt

# 额外依赖（可能需要）
pip install roma einops pillow tqdm gradio trimesh scipy
```

---

## 步骤 3: 下载模型权重

### 3.1 使用 HuggingFace 自动下载

DUSt3R 使用 HuggingFace Hub，首次运行会自动下载模型：

```python
from dust3r.model import AsymmetricCroCo3DStereo

# 自动从 HuggingFace 下载 (~1.3GB)
model = AsymmetricCroCo3DStereo.from_pretrained("naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt")
```

### 3.2 手动下载（可选）

如果网络不稳定，可以手动下载：

```bash
# 创建 checkpoints 目录
mkdir -p checkpoints

# 从 HuggingFace 下载
# 方式 1: 使用 huggingface-cli
pip install huggingface_hub
huggingface-cli download naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt --local-dir checkpoints/DUSt3R_ViTLarge_BaseDecoder_512_dpt

# 方式 2: 使用 wget（需要知道直接链接）
# wget -O checkpoints/DUSt3R_ViTLarge_BaseDecoder_512_dpt.pth <direct_link>
```

### 3.3 验证模型文件

```bash
# 检查文件大小（约 1.3GB）
ls -lh checkpoints/
```

---

## 步骤 4: 运行验证脚本

### 4.1 运行完整验证

```bash
cd Lightweight-Feedforward-3D-Reconstruction-work

# 添加 DUSt3R 到 Python 路径
export PYTHONPATH="${PYTHONPATH}:$(pwd)/third_party/dust3r"

# 运行验证脚本
python scripts/test_dust3r_baseline.py
```

### 4.2 预期输出

```
============================================================
  DUSt3R Baseline 手动验证
============================================================

使用设备: cuda

[CHECK 1] 检查依赖导入...
  ✓ torch: 2.x.x
    CUDA available: True
    CUDA device: NVIDIA A100-SXM4-40GB
  ✓ numpy: 1.x.x
  ✓ dust3r.model
  ✓ dust3r.inference
  ✓ dust3r.utils.image
  ✓ dust3r.image_pairs

[CHECK 1] 通过

[CHECK 2] 检查模型加载...
  加载模型: naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt
  目标设备: cuda
  ✓ 模型加载成功
    总参数量: 512,xxx,xxx (512.xx M)
    可训练参数: 512,xxx,xxx

[CHECK 2] 通过

[CHECK 3] 准备测试图像...
  ✓ 创建测试图像

[CHECK 3] 通过

[CHECK 4] 运行推理...
  ✓ 推理完成
    耗时: x.xxxs

[CHECK 4] 通过

[CHECK 5] 检查输出格式...
  pts3d 形状: (batch, height, width, 3)
  conf 形状: (batch, height, width)

[CHECK 5] 通过

============================================================
  ✅ 所有检查通过！DUSt3R Baseline 验证成功
============================================================
```

---

## 步骤 5: 运行官方 Demo（可选）

### 5.1 启动 Gradio Demo

```bash
cd third_party/dust3r

python demo.py --model_name DUSt3R_ViTLarge_BaseDecoder_512_dpt
```

### 5.2 访问 Web 界面

打开浏览器访问 `http://localhost:7860`

---

## 常见问题

### Q1: CUDA out of memory

```
RuntimeError: CUDA out of memory
```

**解决方案：**
- 减小 batch_size 到 1
- 使用更小的图像尺寸（224 instead of 512）
- 使用 `torch.cuda.empty_cache()`

### Q2: 模型下载失败

```
Exception: tried to load xxx from huggingface, but failed
```

**解决方案：**
- 检查网络连接
- 设置 HuggingFace 镜像: `export HF_ENDPOINT=https://hf-mirror.com`
- 手动下载模型文件

### Q3: Missing dependencies

```
ModuleNotFoundError: No module named 'roma'
```

**解决方案：**
```bash
pip install roma einops pillow
```

### Q4: CRoCo 模块缺失

```
ModuleNotFoundError: No module named 'croco'
```

**解决方案：**
```bash
# CRoCo 是 DUSt3R 的 submodule
cd third_party/dust3r
git submodule update --init --recursive
```

---

## 下一步

验证成功后，记录以下信息：

| 项目 | 值 |
|------|-----|
| 服务器型号 | |
| GPU 型号 | |
| CUDA 版本 | |
| PyTorch 版本 | |
| 推理耗时 | |
| 显存占用 | |

然后继续：
1. 准备真实数据集（ScanNet / CO3D）
2. 运行完整 baseline 评测
3. 开始蒸馏实验
