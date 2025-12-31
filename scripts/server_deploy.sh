#!/bin/bash
# ===========================================
# 服务器自动部署脚本
# ===========================================
# 用法: 在服务器上执行 bash scripts/server_deploy.sh

set -e  # 遇错即停

echo "=============================================="
echo "服务器自动部署脚本"
echo "=============================================="

# 检查当前目录
CURRENT_DIR=$(pwd)
echo "当前目录: $CURRENT_DIR"

# 检查是否在项目根目录
if [ ! -f "requirements.txt" ]; then
    echo "错误: 不在项目根目录，请先 cd 到项目目录"
    exit 1
fi

# 步骤1: 检查submodule
echo ""
echo "[1/4] 检查submodule..."
if [ ! -d "third_party/dust3r" ] || [ -z "$(ls -A third_party/dust3r 2>/dev/null)" ]; then
    echo "  Submodule未下载，正在更新..."
    git submodule update --init --recursive
else
    echo "  Submodule已存在"
fi

# 步骤2: 检查Python
echo ""
echo "[2/4] 检查Python..."
python3 --version || { echo "错误: Python3未找到"; exit 1; }

# 步骤3: 检查CUDA
echo ""
echo "[3/4] 检查CUDA..."
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    echo "  警告: nvidia-smi未找到，GPU可能不可用"
fi

# 步骤4: 安装依赖
echo ""
echo "[4/4] 安装依赖..."
echo "  安装PyTorch..."
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121 || {
    echo "  警告: PyTorch安装失败，尝试使用conda..."
    conda install pytorch torchvision pytorch-cuda=12.1 -c pytorch -c nvidia -y || {
        echo "  错误: PyTorch安装失败"
        exit 1
    }
}

echo "  安装项目依赖..."
pip install -r requirements.txt || {
    echo "  警告: 部分依赖安装失败，继续..."
}

# 步骤5: 下载模型权重（可选）
echo ""
read -p "是否现在下载模型权重? (y/n, 默认n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "  下载模型权重..."
    python scripts/download_weights.py || {
        echo "  警告: 模型权重下载失败，可以稍后手动下载"
    }
fi

# 完成
echo ""
echo "=============================================="
echo "✅ 部署完成！"
echo "=============================================="
echo ""
echo "验证环境:"
echo "  python -c \"import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}')\""
echo ""
echo "运行baseline测试:"
echo "  python scripts/test_dust3r_baseline.py --device cuda"
echo ""

