#!/bin/bash
# ===========================================
# 从旧服务器传输到新服务器
# ===========================================
# 用法: 在新服务器上执行此脚本
# 前提: 旧服务器和新服务器都可以SSH连接

set -e

OLD_HOST="154.57.34.99"
OLD_PORT="16878"
NEW_HOST="99.28.52.219"
NEW_PORT="25834"

# 尝试找到旧服务器上的项目位置
echo "=============================================="
echo "从旧服务器传输项目到新服务器"
echo "=============================================="
echo "旧服务器: $OLD_HOST:$OLD_PORT"
echo "新服务器: $NEW_HOST:$NEW_PORT"
echo ""

# 检查旧服务器上的项目位置
echo "[1/5] 检查旧服务器上的项目..."
OLD_PROJECT_PATH=""
if ssh -p $OLD_PORT root@$OLD_HOST "[ -d /root/Lightweight-Feedforward-3D-Reconstruction-work ]" 2>/dev/null; then
    OLD_PROJECT_PATH="/root/Lightweight-Feedforward-3D-Reconstruction-work"
    echo "  ✓ 找到项目: $OLD_PROJECT_PATH"
elif ssh -p $OLD_PORT root@$OLD_HOST "[ -d /workspace/Lightweight-Feedforward-3D-Reconstruction-work ]" 2>/dev/null; then
    OLD_PROJECT_PATH="/workspace/Lightweight-Feedforward-3D-Reconstruction-work"
    echo "  ✓ 找到项目: $OLD_PROJECT_PATH"
else
    echo "  ✗ 未找到项目，请手动指定路径"
    exit 1
fi

# 检查项目大小
echo ""
echo "[2/5] 检查项目大小..."
PROJECT_SIZE=$(ssh -p $OLD_PORT root@$OLD_HOST "du -sb $OLD_PROJECT_PATH 2>/dev/null | cut -f1")
if [ -z "$PROJECT_SIZE" ]; then
    echo "  ✗ 无法获取项目大小"
    exit 1
fi
SIZE_MB=$((PROJECT_SIZE / 1024 / 1024))
echo "  项目大小: ${SIZE_MB} MB"
echo "  预计传输时间: 约 $((SIZE_MB / 10)) 分钟（取决于网络速度）"

# 确认传输
echo ""
read -p "是否开始传输? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "传输已取消"
    exit 0
fi

# 创建目标目录
echo ""
echo "[3/5] 准备目标目录..."
mkdir -p /root/Lightweight-Feedforward-3D-Reconstruction-work
cd /root

# 使用rsync传输（显示进度）
echo ""
echo "[4/5] 开始传输（使用rsync，显示进度）..."
echo "  这可能需要几分钟，请耐心等待..."
rsync -avz --progress -e "ssh -p $OLD_PORT" \
    root@$OLD_HOST:$OLD_PROJECT_PATH/ \
    /root/Lightweight-Feedforward-3D-Reconstruction-work/ || {
    echo "  ✗ rsync传输失败，尝试使用tar+ssh..."
    # 备用方案：使用tar+ssh
    ssh -p $OLD_PORT root@$OLD_HOST "cd $OLD_PROJECT_PATH && tar czf - ." | \
        tar xzf - -C /root/Lightweight-Feedforward-3D-Reconstruction-work/
}

# 验证传输
echo ""
echo "[5/5] 验证传输..."
cd /root/Lightweight-Feedforward-3D-Reconstruction-work
if [ -f "scripts/setup_server.sh" ]; then
    echo "  ✓ 项目文件传输成功"
else
    echo "  ✗ 传输可能不完整，请检查"
    exit 1
fi

# 检查submodule
echo ""
echo "检查submodule..."
if [ -d "third_party/dust3r" ] && [ -f "third_party/dust3r/.git" ]; then
    echo "  ✓ submodule已包含"
else
    echo "  ⚠ submodule需要重新初始化"
    git submodule update --init --recursive || echo "  ⚠ submodule初始化失败，可能需要手动处理"
fi

# 完成
echo ""
echo "=============================================="
echo "✅ 传输完成！"
echo "=============================================="
echo ""
echo "项目位置: /root/Lightweight-Feedforward-3D-Reconstruction-work"
echo ""
echo "下一步："
echo "  1. 检查环境（可能需要重新安装依赖）:"
echo "     cd /root/Lightweight-Feedforward-3D-Reconstruction-work"
echo "     bash scripts/setup_server.sh"
echo ""

