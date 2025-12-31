#!/bin/bash
# ===========================================
# 服务器部署完整脚本 - 一键执行所有步骤
# ===========================================
# 用法: bash scripts/服务器部署完整脚本.sh
# 注意: 此脚本会执行环境设置、验证、数据准备等所有步骤

set -e  # 遇错即停

PROJECT_ROOT="/root/Lightweight-Feedforward-3D-Reconstruction-work"
LOG_FILE="/tmp/deployment_$(date +%Y%m%d_%H%M%S).log"

echo "============================================" | tee "$LOG_FILE"
echo "服务器部署完整脚本" | tee -a "$LOG_FILE"
echo "开始时间: $(date)" | tee -a "$LOG_FILE"
echo "日志文件: $LOG_FILE" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"
echo ""

cd "$PROJECT_ROOT" || { echo "错误: 无法进入项目目录 $PROJECT_ROOT" | tee -a "$LOG_FILE"; exit 1; }

# ===========================================
# 阶段1: 环境设置
# ===========================================
echo "" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"
echo "阶段1: 环境设置" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"

echo "[1.1] 检查Python..." | tee -a "$LOG_FILE"
python3 --version | tee -a "$LOG_FILE"

echo "[1.2] 检查GPU..." | tee -a "$LOG_FILE"
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=name,memory.total --format=csv | tee -a "$LOG_FILE"
else
    echo "警告: nvidia-smi未找到，GPU可能不可用" | tee -a "$LOG_FILE"
fi

echo "[1.3] 运行setup_server.sh..." | tee -a "$LOG_FILE"
if [ -f "scripts/setup_server.sh" ]; then
    bash scripts/setup_server.sh 2>&1 | tee -a "$LOG_FILE"
else
    echo "错误: setup_server.sh不存在" | tee -a "$LOG_FILE"
    exit 1
fi

# ===========================================
# 阶段2: 环境验证
# ===========================================
echo "" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"
echo "阶段2: 环境验证" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"

echo "[2.1] 验证Teacher模型..." | tee -a "$LOG_FILE"
python scripts/test_dust3r_baseline.py --device cuda 2>&1 | tee -a "$LOG_FILE"

echo "[2.2] 验证Student模型..." | tee -a "$LOG_FILE"
python3 -c "
import torch
import sys
sys.path.insert(0, '.')
from scripts.models import DUSt3RStudent, StudentConfig

config = StudentConfig.from_scale('s')
model = DUSt3RStudent(config=config)
view1 = {'img': torch.randn(1, 3, 512, 384)}
view2 = {'img': torch.randn(1, 3, 512, 384)}
out1, out2 = model(view1, view2)
print('✅ Student模型测试通过')
print(f'参数量: {sum(p.numel() for p in model.parameters())/1e6:.2f}M')
" 2>&1 | tee -a "$LOG_FILE"

# ===========================================
# 阶段3: 数据集准备（提示）
# ===========================================
echo "" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"
echo "阶段3: 数据集准备" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"

echo "[3.1] MegaDepth数据集准备..." | tee -a "$LOG_FILE"
echo "提示: MegaDepth数据集需要手动下载" | tee -a "$LOG_FILE"
echo "步骤1: 从官网下载原始数据: https://www.cs.cornell.edu/projects/megadepth/" | tee -a "$LOG_FILE"
echo "步骤2: 解压到: $PROJECT_ROOT/datasets/megadepth" | tee -a "$LOG_FILE"
echo "步骤3: 运行: bash scripts/download_megadepth.sh" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "或使用tmux后台运行:" | tee -a "$LOG_FILE"
echo "  tmux new -s megadepth" | tee -a "$LOG_FILE"
echo "  bash scripts/download_megadepth.sh" | tee -a "$LOG_FILE"

# ===========================================
# 完成
# ===========================================
echo "" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"
echo "✅ 环境设置完成！" | tee -a "$LOG_FILE"
echo "结束时间: $(date)" | tee -a "$LOG_FILE"
echo "日志文件: $LOG_FILE" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "下一步:" | tee -a "$LOG_FILE"
echo "1. 准备MegaDepth数据集（见上方提示）" | tee -a "$LOG_FILE"
echo "2. 运行Dry-run测试: python scripts/train_distill.py --exp-config distill.yaml --dry-run --max-epochs 2" | tee -a "$LOG_FILE"
echo "3. 启动正式训练: python scripts/train_distill.py --exp-config distill.yaml" | tee -a "$LOG_FILE"

