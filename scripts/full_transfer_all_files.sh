#!/bin/bash
# ===========================================
# 完整传输：打包所有文件，传输到新服务器
# ===========================================
# 在新服务器上执行此脚本

set -e

OLD_HOST="154.57.34.99"
OLD_PORT="16878"
TARGET_DIR="/root/Lightweight-Feedforward-3D-Reconstruction-work"
COMPRESS_LEVEL=6  # 压缩级别（1-9，6是平衡点）

echo "=============================================="
echo "完整传输：打包所有文件到新服务器"
echo "=============================================="
echo "旧服务器: $OLD_HOST:$OLD_PORT"
echo "目标目录: $TARGET_DIR"
echo ""

# 检查旧服务器上的项目
echo "[1/4] 检查旧服务器项目..."
OLD_PROJECT="/root/Lightweight-Feedforward-3D-Reconstruction-work"
if ! ssh -p $OLD_PORT root@$OLD_HOST "[ -d $OLD_PROJECT ]" 2>/dev/null; then
    echo "  ✗ 项目目录不存在"
    exit 1
fi

# 检查大小
echo ""
echo "[2/4] 检查项目大小..."
PROJECT_SIZE=$(ssh -p $OLD_PORT root@$OLD_HOST "du -sb $OLD_PROJECT 2>/dev/null | cut -f1")
SIZE_GB=$((PROJECT_SIZE / 1024 / 1024 / 1024))
echo "  原始大小: ${SIZE_GB} GB"
echo "  压缩后预计: ~$((SIZE_GB * 2 / 5)) GB（取决于文件类型）"
echo "  预计传输时间: 约 $((SIZE_GB * 3)) 分钟（取决于网络速度）"

# 确认
echo ""
read -p "是否开始打包传输? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "已取消"
    exit 0
fi

# 创建目标目录
mkdir -p "$(dirname $TARGET_DIR)"
cd "$(dirname $TARGET_DIR)"

echo ""
echo "[3/4] 打包并传输（使用tar+gzip压缩）..."
echo "  这可能需要较长时间，请耐心等待..."
echo "  压缩和传输会同时进行，显示进度..."

# 使用tar压缩并传输（显示进度）
ssh -p $OLD_PORT root@$OLD_HOST "cd $OLD_PROJECT && tar czf - ." | \
    pv -s ${PROJECT_SIZE} | \
    tar xzf - -C "$TARGET_DIR" 2>/dev/null || {
    # 如果没有pv，使用普通方式
    echo "  使用标准传输（无进度条）..."
    ssh -p $OLD_PORT root@$OLD_HOST "cd $OLD_PROJECT && tar czf - ." | \
        tar xzf - -C "$TARGET_DIR"
}

echo ""
echo "[4/4] 验证传输..."
cd "$TARGET_DIR"
if [ -f "scripts/setup_server.sh" ] && [ -d ".git" ]; then
    echo "  ✓ 项目文件传输成功"
    echo "  最终大小: $(du -sh . | cut -f1)"
else
    echo "  ✗ 传输可能不完整"
    exit 1
fi

# 完成
echo ""
echo "=============================================="
echo "✅ 完整传输完成！"
echo "=============================================="
echo ""
echo "项目位置: $TARGET_DIR"
echo ""
echo "注意："
echo "  - 如果环境依赖已安装，可以直接使用"
echo "  - 如果环境需要重新配置，运行: bash scripts/setup_server.sh"
echo ""

