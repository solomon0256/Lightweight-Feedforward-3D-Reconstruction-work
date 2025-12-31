#!/bin/bash
# 启动真实K-only实验脚本

set -e

cd /workspace/Lightweight-Feedforward-3D-Reconstruction-work

echo "============================================================"
echo "启动真实K-only实验"
echo "============================================================"

# 1. 检查Teacher模型
echo "[1/4] 检查Teacher模型..."
python3 -c "
from dust3r.model import AsymmetricCroCo3DStereo
model = AsymmetricCroCo3DStereo.from_pretrained('naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt')
params = sum(p.numel() for p in model.parameters())
print(f'✅ Teacher模型加载成功: {params/1e6:.2f}M参数')
" || {
    echo "❌ Teacher模型加载失败，但继续使用dummy Teacher"
}

# 2. 检查数据集
echo "[2/4] 检查数据集..."
if [ -f "datasets/train_pairs.lst" ] && [ -s "datasets/train_pairs.lst" ]; then
    TRAIN_COUNT=$(wc -l < datasets/train_pairs.lst)
    echo "✅ 训练数据: $TRAIN_COUNT pairs"
else
    echo "⚠️ 训练数据不存在，将使用dummy数据"
fi

if [ -f "datasets/val_pairs.lst" ] && [ -s "datasets/val_pairs.lst" ]; then
    VAL_COUNT=$(wc -l < datasets/val_pairs.lst)
    echo "✅ 验证数据: $VAL_COUNT pairs"
else
    echo "⚠️ 验证数据不存在，将使用dummy数据"
fi

# 3. 停止旧实验
echo "[3/4] 停止旧实验..."
tmux kill-session -t experiment 2>/dev/null || true
sleep 1

# 4. 启动新实验
echo "[4/4] 启动实验..."
tmux new-session -d -s experiment "python3 scripts/train_distill.py --exp-config expconfigs/distill.yaml 2>&1 | tee logs/distill_training_real.log"

echo ""
echo "============================================================"
echo "实验已启动！"
echo "============================================================"
echo "查看进度: tmux attach -t experiment"
echo "查看日志: tail -f logs/distill_training_real.log"
echo "查看GPU: watch -n 2 nvidia-smi"
echo "============================================================"

