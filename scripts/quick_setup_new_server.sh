#!/bin/bash
# ===========================================
# 新服务器快速配置脚本
# ===========================================
# 用法: bash scripts/quick_setup_new_server.sh [repo-url]
# 如果项目已存在，会自动pull更新

set -e  # 遇错即停

REPO_URL="${1:-https://github.com/your-username/Lightweight-Feedforward-3D-Reconstruction-work.git}"
PROJECT_DIR="/root/Lightweight-Feedforward-3D-Reconstruction-work"

echo "=============================================="
echo "新服务器快速配置脚本"
echo "=============================================="
echo "项目目录: $PROJECT_DIR"
echo "仓库URL: $REPO_URL"
echo ""

# Step 1: 检查/克隆项目
echo "[1/6] 检查项目目录..."
if [ -d "$PROJECT_DIR" ]; then
    echo "  项目目录已存在，更新代码..."
    cd "$PROJECT_DIR"
    git pull || echo "  警告: git pull失败，继续..."
else
    echo "  克隆项目..."
    cd /root
    git clone "$REPO_URL" Lightweight-Feedforward-3D-Reconstruction-work
    cd "$PROJECT_DIR"
fi

# Step 2: 初始化submodule
echo ""
echo "[2/6] 初始化submodule..."
git submodule update --init --recursive || {
    echo "  警告: submodule初始化失败，尝试删除后重新初始化..."
    rm -rf third_party/dust3r
    git submodule update --init --recursive
}

# Step 3: 检查Python
echo ""
echo "[3/6] 检查Python..."
python3 --version || { echo "错误: Python3未找到"; exit 1; }

# Step 4: 检查CUDA
echo ""
echo "[4/6] 检查CUDA..."
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    echo "  警告: nvidia-smi未找到，GPU可能不可用"
fi

# Step 5: 安装PyTorch
echo ""
echo "[5/6] 安装PyTorch with CUDA 12.1..."
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121 || {
    echo "  警告: pip安装失败，尝试conda..."
    conda install pytorch torchvision pytorch-cuda=12.1 -c pytorch -c nvidia -y || {
        echo "  错误: PyTorch安装失败"
        exit 1
    }
}

# Step 6: 安装DUSt3R依赖
echo ""
echo "[6/6] 安装DUSt3R依赖..."
if [ -f "third_party/dust3r/requirements.txt" ]; then
    pip install -r third_party/dust3r/requirements.txt
else
    echo "  警告: requirements.txt不存在，跳过..."
fi

# 额外依赖
pip install roma einops pillow scipy trimesh tqdm

# 创建必要的__init__.py
mkdir -p third_party/dust3r/croco/models
touch third_party/dust3r/croco/models/__init__.py

# 验证安装
echo ""
echo "=============================================="
echo "验证安装..."
echo "=============================================="
python3 -c "
import torch
print(f'PyTorch: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'CUDA version: {torch.version.cuda}')
    print(f'GPU: {torch.cuda.get_device_name(0)}')
" || {
    echo "  警告: PyTorch验证失败"
}

# 完成
echo ""
echo "=============================================="
echo "✅ 配置完成！"
echo "=============================================="
echo ""
echo "下一步："
echo "  1. 下载模型权重（可选）:"
echo "     cd $PROJECT_DIR && python3 scripts/download_weights.py"
echo ""
echo "  2. 验证环境:"
echo "     cd $PROJECT_DIR && python3 scripts/verify_environment.py"
echo ""
echo "  3. 运行测试:"
echo "     cd $PROJECT_DIR && python3 scripts/test_dust3r_baseline.py --device cuda"
echo ""

