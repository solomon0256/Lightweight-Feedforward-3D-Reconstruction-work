# 环境恢复指南

> **创建时间**: 2025-12-25  
> **目的**: 当环境出问题（自动更新、依赖冲突等）时，按此文档恢复

---

## 📋 完整环境快照

### 硬件
| 项目 | 值 |
|------|-----|
| **GPU** | NVIDIA GeForce RTX 3060 Laptop GPU |
| **GPU 显存** | 6 GB |
| **CUDA** | 12.4 |
| **cuDNN** | 90100 |
| **驱动版本** | 572.83 |
| **计算能力** | 8.6 |
| **CPU** | 12th Gen Intel Core i7-12700H |
| **CPU 核心** | 14核 20线程 |
| **CPU 频率** | 2300 MHz (base) |
| **RAM** | 16 GB DDR5-4800 (2×8GB Samsung) |
| **OS** | Windows 11 专业版 (10.0.26200) |

### PyTorch 后端开关（重要！）
| 开关 | 当前值 | 说明 |
|------|--------|------|
| `cudnn.enabled` | `True` | cuDNN 启用 |
| `cudnn.benchmark` | `False` | 自动调优（关闭保证复现） |
| `cudnn.deterministic` | `False` | 确定性模式 |
| `cudnn.allow_tf32` | `True` | 允许 TF32 |
| `cuda.matmul.allow_tf32` | `False` | 矩阵乘法 TF32 |
| `cuda.matmul.allow_fp16_reduced_precision` | `True` | FP16 降精度 |
| `cuda.matmul.allow_bf16_reduced_precision` | `True` | BF16 降精度 |
| `mkl.is_available` | `True` | MKL 可用 |
| `mkldnn.is_available` | `True` | MKLDNN 可用 |
| `openmp.is_available` | `True` | OpenMP 可用 |

### 所有 92 个 pip 包
详见 `config/requirements_freeze.txt`（完整 pip freeze）

### 核心包版本
| 包 | 版本 | 重要性 |
|----|------|--------|
| Python | 3.13.6 | 🔴 关键 |
| PyTorch | 2.6.0+cu124 | 🔴 关键 |
| torchvision | 0.21.0+cu124 | 🔴 关键 |
| CUDA | 12.4 | 🔴 关键 |
| numpy | 2.2.6 | 🔴 关键 |
| scipy | 1.16.3 | 🟡 重要 |
| opencv-python | 4.12.0.88 | 🟡 重要 |
| einops | 0.8.1 | 🟡 重要 |
| roma | 1.5.4 | 🟡 重要 |
| pillow | 12.0.0 | 🟡 重要 |
| huggingface_hub | 1.2.3 | 🟡 重要 |
| gradio | 6.2.0 | 🟢 可选 |
| matplotlib | 3.10.8 | 🟢 可选 |
| pandas | 2.3.3 | 🟢 可选 |

### Git 版本
| 仓库 | Commit Hash |
|------|-------------|
| 主仓库 | `babb0331e16baacc28fe6862fca08f69d4c259fe` |
| DUSt3R | `4c24a6ebf04809f2cfe59915e51779c8984aaa40` |

---

## 🔧 恢复步骤

### 方法 1: 使用 requirements_freeze.txt（推荐）

```powershell
# 1. 创建新虚拟环境
python -m venv .venv_restored

# 2. 激活
.\.venv_restored\Scripts\Activate.ps1

# 3. 安装所有依赖（精确版本）
pip install -r config/requirements_freeze.txt
```

### 方法 2: 手动安装关键包

```powershell
# 1. 创建虚拟环境
python -m venv .venv

# 2. 激活
.\.venv\Scripts\Activate.ps1

# 3. 安装 PyTorch (CUDA 12.4)
pip install torch==2.6.0+cu124 torchvision==0.21.0+cu124 --index-url https://download.pytorch.org/whl/cu124

# 4. 安装其他依赖
pip install numpy==2.2.6 opencv-python==4.12.0.88 pillow==12.0.0 scipy==1.16.3
pip install matplotlib==3.10.8 einops==0.8.1 roma==1.5.4 tqdm==4.67.1
pip install gradio==6.2.0 psutil==7.2.0 huggingface-hub

# 5. 安装 DUSt3R（本地）
pip install -e third_party/dust3r
```

### 方法 3: 恢复 Git 版本

```powershell
# 主仓库
git checkout babb0331e16baacc28fe6862fca08f69d4c259fe

# DUSt3R submodule
cd third_party/dust3r
git checkout 4c24a6ebf04809f2cfe59915e51779c8984aaa40
cd ../..
```

---

## ⚠️ 常见问题

### Q1: PyTorch CUDA 版本不匹配
```
RuntimeError: CUDA error: no kernel image is available for execution on the device
```
**解决**: 确保 PyTorch CUDA 版本与系统 CUDA 匹配
```powershell
# 检查系统 CUDA
nvcc --version
nvidia-smi

# 重装正确版本
pip uninstall torch torchvision
pip install torch==2.6.0+cu124 torchvision==0.21.0+cu124 --index-url https://download.pytorch.org/whl/cu124
```

### Q2: DUSt3R 导入失败
```
ModuleNotFoundError: No module named 'dust3r'
```
**解决**: 重新安装 DUSt3R
```powershell
pip install -e third_party/dust3r
```

### Q3: numpy 版本冲突
**解决**: 强制安装指定版本
```powershell
pip install numpy==2.2.6 --force-reinstall
```

---

## 📁 相关文件

| 文件 | 说明 |
|------|------|
| `config/environment_snapshot.json` | 完整环境 JSON（机器可读） |
| `config/requirements_freeze.txt` | pip freeze 完整列表 |
| `config/ENVIRONMENT_RECOVERY.md` | 本文档 |

---

## ✅ 验证环境

运行以下脚本验证环境是否正确：

```python
# scripts/verify_environment.py
import torch
import sys

print("=== 环境验证 ===")
print(f"Python: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
print(f"PyTorch: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"CUDA version: {torch.version.cuda}")

# 测试 DUSt3R 加载
try:
    from dust3r.model import AsymmetricCroCo3DStereo
    print("✅ DUSt3R 可导入")
except ImportError as e:
    print(f"❌ DUSt3R 导入失败: {e}")

print("\n=== 验证完成 ===")
```

---

*最后更新: 2025-12-25*
