# DUSt3R Baseline 还原完整记录

> **日期**: 2025-12-23  
> **状态**: ✅ 完成  
> **测试环境**: Windows 11, Python 3.13, PyTorch 2.9.1+cpu

---

## 一、目标

在本地电脑上完整还原 DUSt3R baseline，验证代码能正常运行，然后推送到 GitHub。服务器端只需 clone 仓库并运行设置脚本即可复现。

---

## 二、完成的工作

### 2.1 代码准备

| 步骤 | 操作 | 结果 |
|------|------|------|
| 1 | 将 DUSt3R 添加为 git submodule | `git submodule add https://github.com/naver/dust3r.git third_party/dust3r` |
| 2 | 初始化 CRoCo submodule | `git submodule update --init --recursive` |
| 3 | 安装依赖 | `pip install -r third_party/dust3r/requirements.txt` |

### 2.2 解决的问题

#### 问题 1: `No module named 'models.dpt_block'`

**原因**: CRoCo 的 `models/` 目录缺少 `__init__.py`

**解决方案**: 在脚本中自动创建：
```python
croco_models_init = os.path.join(CROCO_PATH, "models", "__init__.py")
if not os.path.exists(croco_models_init):
    open(croco_models_init, 'w').close()
```

#### 问题 2: Python 路径顺序

**原因**: `sys.path` 插入顺序影响模块查找

**解决方案**: 必须先插入 DUST3R_PATH，再插入 CROCO_PATH：
```python
sys.path.insert(0, CROCO_PATH)
sys.path.insert(0, DUST3R_PATH)  # 最终在最前面
```

### 2.3 创建的脚本

#### `scripts/test_dust3r_baseline.py`
- 完整的 baseline 验证脚本
- 自动检测 CUDA/CPU
- 4 个测试步骤：加载模型 → 创建图像 → 推理 → 验证输出
- 自动创建缺失的 `__init__.py`

#### `scripts/download_weights.py`
- 从 HuggingFace 下载模型权重
- 权重缓存在 `~/.cache/huggingface/hub/`

#### `scripts/setup_server.sh`
- 服务器端一键设置脚本
- 安装 PyTorch + CUDA 12.1
- 安装 DUSt3R 依赖
- 下载模型权重

---

## 三、测试结果

### 3.1 本地测试 (CPU)

```
============================================================
  DUSt3R Baseline 验证
============================================================

PyTorch: 2.9.1+cpu
Device: cpu

[1/4] 加载模型...
✓ 模型加载成功
  参数量: 571,171,208 (571.2M)
  加载耗时: 5.6s

[2/4] 创建测试图像...
✓ 测试图像已创建
  尺寸: 512x384

[3/4] 运行推理...
  图像对数量: 2
✓ 推理完成
  耗时: 13.48s

[4/4] 验证输出格式...
✓ 输出格式正确
  pred1 keys: ['pts3d', 'conf']
  pts3d shape: torch.Size([2, 384, 512, 3])
  conf shape: torch.Size([2, 384, 512])
  pts3d range: [-0.302, 0.606]
  conf range: [1.001, 11.153]

============================================================
  ✅ BASELINE 验证通过！
============================================================
```

### 3.2 关键指标

| 指标 | 值 |
|------|-----|
| 模型参数量 | 571.2M |
| 模型大小 | ~1.1GB (safetensors) |
| CPU 推理时间 | 13.5s / 图像对 |
| 输出 pts3d 形状 | [batch, 384, 512, 3] |
| 输出 conf 形状 | [batch, 384, 512] |

---

## 四、项目结构

```
Lightweight-Feedforward-3D-Reconstruction-work/
├── .gitmodules                    # git submodule 配置
├── third_party/
│   └── dust3r/                    # DUSt3R 官方代码 (submodule)
│       ├── dust3r/                # 核心模块
│       │   ├── model.py           # AsymmetricCroCo3DStereo
│       │   ├── inference.py       # 推理函数
│       │   └── ...
│       └── croco/                 # CRoCo 子模块 (submodule)
│           └── models/            # 需要 __init__.py
├── scripts/
│   ├── test_dust3r_baseline.py    # ✅ Baseline 验证
│   ├── download_weights.py        # ✅ 模型下载
│   ├── setup_server.sh            # ✅ 服务器设置
│   ├── baseline_eval.py           # 完整评测脚本
│   ├── train_distill.py           # 蒸馏训练
│   └── quantize.py                # 量化脚本
├── config/
│   ├── eval.yaml                  # 评测配置
│   └── workload.yaml              # 工作负载配置
├── checkpoints/                   # 模型权重 (git 忽略)
├── docs/
│   ├── baseline_restoration_guide.md
│   └── BASELINE_RESTORATION_COMPLETE.md  # 本文件
└── worklogs/                      # 工作日志
```

---

## 五、服务器部署指南

### 5.1 克隆仓库

```bash
# 必须加 --recursive 以获取 submodule
git clone --recursive https://github.com/solomon0256/Lightweight-Feedforward-3D-Reconstruction-work.git
cd Lightweight-Feedforward-3D-Reconstruction-work
```

### 5.2 一键设置

```bash
bash scripts/setup_server.sh
```

该脚本会：
1. 检查 Python 版本
2. 检查 CUDA 可用性
3. 安装 PyTorch with CUDA 12.1
4. 安装 DUSt3R 依赖
5. 创建 `croco/models/__init__.py`
6. 下载模型权重

### 5.3 验证

```bash
python scripts/test_dust3r_baseline.py
# 或指定设备
python scripts/test_dust3r_baseline.py --device cuda
```

---

## 六、DUSt3R 使用方法

### 6.1 加载模型

```python
import sys
sys.path.insert(0, "third_party/dust3r")
sys.path.insert(0, "third_party/dust3r/croco")

from dust3r.model import AsymmetricCroCo3DStereo

# 从 HuggingFace 加载（自动下载）
model = AsymmetricCroCo3DStereo.from_pretrained(
    "naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt"
)
model = model.to("cuda")
model.eval()
```

### 6.2 运行推理

```python
from dust3r.utils.image import load_images
from dust3r.image_pairs import make_pairs
from dust3r.inference import inference

# 加载图像
imgs = load_images(["img1.png", "img2.png"], size=512)

# 创建图像对
pairs = make_pairs(imgs, scene_graph="complete", symmetrize=True)

# 推理
with torch.no_grad():
    output = inference(pairs, model, "cuda", batch_size=1)

# 获取结果
pts3d = output["pred1"]["pts3d"]  # [B, H, W, 3]
conf = output["pred1"]["conf"]    # [B, H, W]
```

### 6.3 可用模型

| 模型名 | 图像尺寸 | Head 类型 |
|--------|----------|-----------|
| `DUSt3R_ViTLarge_BaseDecoder_512_dpt` | 512 | DPT |
| `DUSt3R_ViTLarge_BaseDecoder_512_linear` | 512 | Linear |
| `DUSt3R_ViTLarge_BaseDecoder_224_linear` | 224 | Linear |

---

## 七、下一步计划

1. **租用 GPU 服务器** - A100 / RTX 4090
2. **运行 GPU 测试** - 验证 CUDA 推理速度
3. **准备数据集** - ScanNet / CO3D 子集
4. **开始蒸馏实验** - 训练 Student 模型
5. **量化实验** - PTQ / QAT

---

## 八、注意事项

### 8.1 模型权重

- 模型权重 (~1.1GB) 通过 HuggingFace 自动下载
- 缓存位置: `~/.cache/huggingface/hub/`
- **不要** 将权重上传到 GitHub

### 8.2 Git Submodule

```bash
# 如果 clone 时忘记 --recursive
git submodule update --init --recursive

# 更新 submodule 到最新
git submodule update --remote
```

### 8.3 CRoCo __init__.py

CRoCo 官方仓库没有 `models/__init__.py`，我们的脚本会自动创建。如果遇到 `No module named 'models.dpt_block'` 错误：

```bash
touch third_party/dust3r/croco/models/__init__.py
```

---

## 九、参考链接

- [DUSt3R 官方仓库](https://github.com/naver/dust3r)
- [CRoCo 官方仓库](https://github.com/naver/croco)
- [DUSt3R HuggingFace](https://huggingface.co/naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt)
- [DUSt3R 论文](https://arxiv.org/abs/2312.14132)

---

**文档作者**: GitHub Copilot  
**最后更新**: 2025-12-23
