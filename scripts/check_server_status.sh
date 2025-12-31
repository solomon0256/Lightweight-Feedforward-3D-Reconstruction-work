#!/bin/bash
# 检查服务器状态脚本

echo "=============================================="
echo "服务器环境检查"
echo "=============================================="

echo ""
echo "1. 检查项目目录..."
if [ -d "/root/Lightweight-Feedforward-3D-Reconstruction-work" ]; then
    echo "  ✓ 项目目录存在: /root/Lightweight-Feedforward-3D-Reconstruction-work"
    ls -la /root/Lightweight-Feedforward-3D-Reconstruction-work | head -10
else
    echo "  ✗ 项目目录不存在"
fi

echo ""
echo "2. 检查workspace目录..."
if [ -d "/workspace" ]; then
    echo "  ✓ workspace目录存在"
    ls -la /workspace | head -15
else
    echo "  ✗ workspace目录不存在"
fi

echo ""
echo "3. 检查Python..."
python3 --version 2>/dev/null || echo "  ✗ Python3未找到"

echo ""
echo "4. 检查PyTorch..."
python3 -c "import torch; print(f'  ✓ PyTorch: {torch.__version__}'); print(f'  ✓ CUDA available: {torch.cuda.is_available()}')" 2>/dev/null || echo "  ✗ PyTorch未安装"

echo ""
echo "5. 检查已安装的Python包..."
pip list 2>/dev/null | grep -E "torch|numpy|einops|roma" | head -10 || echo "  pip未配置"

echo ""
echo "6. 检查CUDA..."
nvidia-smi --query-gpu=name,memory.total --format=csv 2>/dev/null || echo "  nvidia-smi未找到"

echo ""
echo "=============================================="
echo "检查完成"
echo "=============================================="

