#!/bin/bash
# ===========================================
# 快速传输：只传输代码，排除大文件
# ===========================================
# 在新服务器上执行此脚本

set -e

OLD_HOST="154.57.34.99"
OLD_PORT="16878"
TARGET_DIR="/root/Lightweight-Feedforward-3D-Reconstruction-work"

echo "=============================================="
echo "快速传输：只传输代码（排除大文件）"
echo "=============================================="
echo "旧服务器: $OLD_HOST:$OLD_PORT"
echo "目标目录: $TARGET_DIR"
echo ""
echo "排除的目录（大文件）:"
echo "  - datasets/"
echo "  - outputs/"
echo "  - checkpoints/"
echo "  - logs/"
echo "  - .git/objects/ (只传输.git/config等元数据)"
echo ""

# 创建目标目录
mkdir -p "$TARGET_DIR"
cd /root

echo "[1/3] 传输代码文件（排除大目录）..."
rsync -avz --progress \
    --exclude='datasets/' \
    --exclude='outputs/' \
    --exclude='checkpoints/' \
    --exclude='logs/' \
    --exclude='.git/objects/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.venv/' \
    --exclude='venv/' \
    -e "ssh -p $OLD_PORT" \
    root@$OLD_HOST:/root/Lightweight-Feedforward-3D-Reconstruction-work/ \
    "$TARGET_DIR/" || {
    echo "  ✗ rsync失败，使用tar备用方案..."
    ssh -p $OLD_PORT root@$OLD_HOST "cd /root/Lightweight-Feedforward-3D-Reconstruction-work && tar czf - --exclude='datasets' --exclude='outputs' --exclude='checkpoints' --exclude='logs' --exclude='.git/objects' ." | \
        tar xzf - -C "$TARGET_DIR/"
}

echo ""
echo "[2/3] 初始化git（如果需要）..."
cd "$TARGET_DIR"
if [ -d ".git" ]; then
    echo "  ✓ Git目录已传输"
    # 重新获取git对象（如果需要）
    git fetch --unshallow 2>/dev/null || echo "  ⚠ Git对象不完整，但不影响使用"
else
    echo "  ⚠ Git目录未传输，可能需要重新克隆"
fi

echo ""
echo "[3/3] 初始化submodule..."
if [ -f ".gitmodules" ]; then
    git submodule update --init --recursive || echo "  ⚠ Submodule初始化失败"
else
    echo "  ⚠ 没有submodule配置"
fi

echo ""
echo "=============================================="
echo "✅ 代码传输完成！"
echo "=============================================="
echo ""
echo "项目位置: $TARGET_DIR"
echo "大小: $(du -sh $TARGET_DIR | cut -f1)"
echo ""
echo "下一步："
echo "  1. 配置环境:"
echo "     cd $TARGET_DIR && bash scripts/setup_server.sh"
echo ""
echo "  2. 数据集和checkpoints需要单独下载/传输（如果需要）"
echo ""

