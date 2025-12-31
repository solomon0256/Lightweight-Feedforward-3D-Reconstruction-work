#!/bin/bash
# ===========================================
# 完整7-Scenes数据集下载脚本
# ===========================================
# 用法: bash scripts/download_7scenes_complete.sh
# 输出: 实时进度写入 /tmp/7scenes_download.log

set -e

LOG_FILE="/tmp/7scenes_download.log"
DATASET_DIR="/root/Lightweight-Feedforward-3D-Reconstruction-work/datasets/7-scenes"
# 使用微软官方下载地址
BASE_URL="http://download.microsoft.com/download/2/8/5/28564B23-0828-408F-8631-23B1EFF1DAC8"

# 清空日志
> "$LOG_FILE"

echo "============================================" | tee -a "$LOG_FILE"
echo "开始下载完整7-Scenes数据集" | tee -a "$LOG_FILE"
echo "时间: $(date)" | tee -a "$LOG_FILE"
echo "下载地址: $BASE_URL" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"
echo ""

# 创建目录
mkdir -p "$DATASET_DIR"
cd "$DATASET_DIR"

# 下载函数 - 下载整个场景zip文件
download_scene() {
    local scene=$1
    local zip_file="${scene}.zip"
    local url="${BASE_URL}/${zip_file}"
    
    echo "[$(date +%H:%M:%S)] 开始下载场景: $scene" | tee -a "$LOG_FILE"
    echo "[$(date +%H:%M:%S)]   下载地址: $url" | tee -a "$LOG_FILE"
    
    # 下载整个场景zip（显示进度）
    if wget -c --progress=bar:force "$url" -O "$zip_file" 2>&1 | tee -a "$LOG_FILE"; then
        echo "[$(date +%H:%M:%S)]   $scene.zip 下载完成，开始解压..." | tee -a "$LOG_FILE"
        
        # 解压
        if unzip -q "$zip_file" 2>&1 | tee -a "$LOG_FILE"; then
            rm -f "$zip_file"
            echo "[$(date +%H:%M:%S)]   ✅ $scene 解压完成" | tee -a "$LOG_FILE"
        else
            echo "[$(date +%H:%M:%S)]   ❌ $scene 解压失败" | tee -a "$LOG_FILE"
            exit 1
        fi
    else
        echo "[$(date +%H:%M:%S)]   ❌ $scene 下载失败" | tee -a "$LOG_FILE"
        exit 1
    fi
    
    echo "[$(date +%H:%M:%S)] ✅ $scene 场景完成！" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
}

# 下载所有场景
for scene in chess fire heads office pumpkin redkitchen stairs; do
    download_scene "$scene"
done

# 验证下载结果
echo "============================================" | tee -a "$LOG_FILE"
echo "验证下载结果..." | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"

for scene in chess fire heads office pumpkin redkitchen stairs; do
    if [ -d "$scene" ]; then
        file_count=$(find "$scene" -name "*.color.png" 2>/dev/null | wc -l)
        echo "$scene: $file_count 张图像" | tee -a "$LOG_FILE"
    else
        echo "❌ $scene: 目录不存在" | tee -a "$LOG_FILE"
    fi
done

echo "" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"
echo "✅ 全部下载完成！时间: $(date)" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "数据位置: $DATASET_DIR" | tee -a "$LOG_FILE"
echo "日志文件: $LOG_FILE" | tee -a "$LOG_FILE"

