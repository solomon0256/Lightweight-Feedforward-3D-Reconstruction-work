#!/bin/bash
# 7-Scenes完整数据集下载脚本
# 使用kapture官方工具一键下载

LOG=/tmp/7scenes_download.log
DEST=/root/Lightweight-Feedforward-3D-Reconstruction-work/datasets/7-scenes

echo "========================================" | tee $LOG
echo "7-Scenes 数据集下载开始" | tee -a $LOG
echo "时间: $(date)" | tee -a $LOG
echo "目标路径: $DEST" | tee -a $LOG
echo "========================================" | tee -a $LOG

# 安装kapture
echo "[1/3] 安装 kapture..." | tee -a $LOG
pip install kapture kapture-localization 2>&1 | tee -a $LOG

# 更新数据集列表
echo "[2/3] 更新数据集列表..." | tee -a $LOG
kapture_download_dataset.py --install_path $DEST update 2>&1 | tee -a $LOG

# 下载7-Scenes全部场景
echo "[3/3] 下载7-Scenes全部场景..." | tee -a $LOG
kapture_download_dataset.py --install_path $DEST install "7-scenes-*" 2>&1 | tee -a $LOG

echo "========================================" | tee -a $LOG
echo "下载完成！时间: $(date)" | tee -a $LOG
echo "========================================" | tee -a $LOG

# 验证
echo "验证下载结果:" | tee -a $LOG
ls -la $DEST/ | tee -a $LOG
