#!/bin/bash
# ===========================================
# DUSt3R-PQK 服务器端一键设置脚本
# ===========================================
# 用法: bash scripts/setup_server.sh
# 前提: 已 clone 本项目到服务器

set -e  # 遇错即停

echo "=============================================="
echo "DUSt3R-PQK 服务器设置"
echo "=============================================="

# 检测项目根目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "项目目录: $PROJECT_ROOT"

# Step 1: 检查 Python 版本
echo ""
echo "[1/5] 检查 Python..."
python3 --version || { echo "ERROR: Python3 not found"; exit 1; }

# Step 2: 检查 CUDA
echo ""
echo "[2/5] 检查 CUDA..."
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=name,memory.total --format=csv
else
    echo "WARNING: nvidia-smi not found, GPU may not be available"
fi

# Step 3: 安装 PyTorch
echo ""
echo "[3/5] 安装 PyTorch with CUDA..."
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# Step 4: 安装 DUSt3R 依赖
echo ""
echo "[4/5] 安装 DUSt3R 依赖..."
pip install -r third_party/dust3r/requirements.txt

# 额外依赖
pip install roma einops pillow scipy trimesh

# 创建必要的 __init__.py（CRoCo models 需要）
touch third_party/dust3r/croco/models/__init__.py

# Step 5: 下载模型权重
echo ""
echo "[5/5] 下载模型权重..."
python3 scripts/download_weights.py

# 完成
echo ""
echo "=============================================="
echo "✅ 设置完成！"
echo "=============================================="
echo ""
echo "运行 baseline 测试:"
echo "  python scripts/test_dust3r_baseline.py"
echo ""
echo "或者运行完整评测:"
echo "  python scripts/baseline_eval.py --config config/eval.yaml"
