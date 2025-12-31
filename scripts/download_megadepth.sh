#!/bin/bash
# ===========================================
# MegaDepth数据集下载和预处理脚本
# ===========================================
# 用法: bash scripts/download_megadepth.sh
# 输出: 实时进度写入 /tmp/megadepth_download.log

set -e

LOG_FILE="/tmp/megadepth_download.log"
PROJECT_ROOT="/root/Lightweight-Feedforward-3D-Reconstruction-work"
DATASET_DIR="${PROJECT_ROOT}/datasets/megadepth"
PROCESSED_DIR="${DATASET_DIR}_processed"
PAIRS_URL="https://download.europe.naverlabs.com/ComputerVision/DUSt3R/megadepth_pairs.npz"
MEGADEPTH_OFFICIAL_URL="https://www.cs.cornell.edu/projects/megadepth/"

# 清空日志
> "$LOG_FILE"

echo "============================================" | tee -a "$LOG_FILE"
echo "MegaDepth数据集下载和预处理" | tee -a "$LOG_FILE"
echo "时间: $(date)" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"
echo ""

cd "$PROJECT_ROOT"

# Step 1: 创建目录
echo "[1/5] 创建目录..." | tee -a "$LOG_FILE"
mkdir -p "$DATASET_DIR"
mkdir -p "$PROCESSED_DIR"

# Step 2: 下载pairs文件
echo "" | tee -a "$LOG_FILE"
echo "[2/5] 下载预计算的图像对列表..." | tee -a "$LOG_FILE"
PAIRS_FILE="${DATASET_DIR}/megadepth_pairs.npz"
if [ ! -f "$PAIRS_FILE" ]; then
    echo "  下载地址: $PAIRS_URL" | tee -a "$LOG_FILE"
    wget -c --progress=bar:force "$PAIRS_URL" -O "$PAIRS_FILE" 2>&1 | tee -a "$LOG_FILE"
    echo "  ✅ pairs文件下载完成" | tee -a "$LOG_FILE"
else
    echo "  ✅ pairs文件已存在: $PAIRS_FILE" | tee -a "$LOG_FILE"
fi

# Step 3: 提示下载原始MegaDepth数据
echo "" | tee -a "$LOG_FILE"
echo "[3/5] 原始MegaDepth数据下载说明..." | tee -a "$LOG_FILE"
echo "  注意: MegaDepth原始数据需要从官方网站手动下载" | tee -a "$LOG_FILE"
echo "  下载地址: $MEGADEPTH_OFFICIAL_URL" | tee -a "$LOG_FILE"
echo "  下载后，请将数据解压到: $DATASET_DIR" | tee -a "$LOG_FILE"
echo "  目录结构应该是: $DATASET_DIR/<scene_id>/dense<subscene>/..." | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "  如果数据已下载，按Enter继续预处理..." | tee -a "$LOG_FILE"
echo "  否则请先下载数据，然后重新运行此脚本" | tee -a "$LOG_FILE"
read -t 10 -p "  等待10秒后自动继续，或按Enter立即继续..." || true
echo "" | tee -a "$LOG_FILE"

# Step 4: 检查原始数据是否存在
echo "[4/5] 检查原始数据..." | tee -a "$LOG_FILE"
if [ ! -d "$DATASET_DIR" ] || [ -z "$(ls -A "$DATASET_DIR" 2>/dev/null)" ]; then
    echo "  ❌ 错误: $DATASET_DIR 目录不存在或为空" | tee -a "$LOG_FILE"
    echo "  请先下载MegaDepth原始数据" | tee -a "$LOG_FILE"
    exit 1
fi

# 检查是否有场景目录
SCENE_COUNT=$(find "$DATASET_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l)
if [ "$SCENE_COUNT" -eq 0 ]; then
    echo "  ❌ 错误: 未找到任何场景目录" | tee -a "$LOG_FILE"
    echo "  请确认数据已正确解压到 $DATASET_DIR" | tee -a "$LOG_FILE"
    exit 1
fi

echo "  ✅ 找到 $SCENE_COUNT 个场景目录" | tee -a "$LOG_FILE"

# Step 5: 运行预处理脚本
echo "" | tee -a "$LOG_FILE"
echo "[5/5] 运行预处理脚本..." | tee -a "$LOG_FILE"
PREPROCESS_SCRIPT="${PROJECT_ROOT}/third_party/dust3r/datasets_preprocess/preprocess_megadepth.py"

if [ ! -f "$PREPROCESS_SCRIPT" ]; then
    echo "  ❌ 错误: 预处理脚本不存在: $PREPROCESS_SCRIPT" | tee -a "$LOG_FILE"
    exit 1
fi

echo "  预处理脚本: $PREPROCESS_SCRIPT" | tee -a "$LOG_FILE"
echo "  输入目录: $DATASET_DIR" | tee -a "$LOG_FILE"
echo "  pairs文件: $PAIRS_FILE" | tee -a "$LOG_FILE"
echo "  输出目录: $PROCESSED_DIR" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

python3 "$PREPROCESS_SCRIPT" \
    --megadepth_dir "$DATASET_DIR" \
    --precomputed_pairs "$PAIRS_FILE" \
    --output_dir "$PROCESSED_DIR" \
    2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"
echo "✅ 预处理完成！时间: $(date)" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "处理后的数据位置: $PROCESSED_DIR" | tee -a "$LOG_FILE"
echo "日志文件: $LOG_FILE" | tee -a "$LOG_FILE"

