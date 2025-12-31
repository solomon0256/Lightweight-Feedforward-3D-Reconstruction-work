#!/bin/bash
# 实验状态监测脚本

DURATION=600  # 10分钟 = 600秒
INTERVAL=30   # 每30秒监测一次
LOG_FILE="/workspace/Lightweight-Feedforward-3D-Reconstruction-work/logs/monitor.log"
TRAIN_LOG="/workspace/Lightweight-Feedforward-3D-Reconstruction-work/logs/distill_training_real.log"

echo "============================================================"
echo "开始监测实验状态 (持续10分钟)"
echo "============================================================"
echo "监测间隔: ${INTERVAL}秒"
echo "总时长: ${DURATION}秒 (10分钟)"
echo "日志文件: ${LOG_FILE}"
echo "============================================================"
echo ""

start_time=$(date +%s)
end_time=$((start_time + DURATION))
iteration=0

while [ $(date +%s) -lt $end_time ]; do
    iteration=$((iteration + 1))
    elapsed=$(($(date +%s) - start_time))
    remaining=$((DURATION - elapsed))
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ========== 监测 #${iteration} (已运行${elapsed}秒，剩余${remaining}秒) ==========" | tee -a "$LOG_FILE"
    
    # 1. GPU状态
    echo "--- GPU状态 ---" | tee -a "$LOG_FILE"
    nvidia-smi --query-gpu=index,name,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw --format=csv,noheader,nounits | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    
    # 2. 进程状态
    echo "--- 训练进程状态 ---" | tee -a "$LOG_FILE"
    ps aux | grep "train_distill" | grep -v grep | head -3 | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    
    # 3. CPU和内存
    echo "--- 系统资源 ---" | tee -a "$LOG_FILE"
    echo "CPU使用率: $(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1}')%" | tee -a "$LOG_FILE"
    free -h | grep Mem | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    
    # 4. 训练进度
    echo "--- 训练进度 ---" | tee -a "$LOG_FILE"
    if [ -f "$TRAIN_LOG" ]; then
        # 最新epoch
        latest_epoch=$(tail -100 "$TRAIN_LOG" | grep -oP "Epoch \K[0-9]+/[0-9]+" | tail -1)
        if [ ! -z "$latest_epoch" ]; then
            echo "最新Epoch: $latest_epoch" | tee -a "$LOG_FILE"
        fi
        
        # 最新loss
        latest_loss=$(tail -100 "$TRAIN_LOG" | grep -oP "Train: \K[0-9.]+" | tail -1)
        latest_val=$(tail -100 "$TRAIN_LOG" | grep -oP "Val: \K[0-9.]+" | tail -1)
        if [ ! -z "$latest_loss" ]; then
            echo "Train Loss: $latest_loss" | tee -a "$LOG_FILE"
            echo "Val Loss: $latest_val" | tee -a "$LOG_FILE"
        fi
        
        # 检查错误
        error_count=$(tail -200 "$TRAIN_LOG" | grep -i "error\|exception\|failed" | wc -l)
        if [ $error_count -gt 0 ]; then
            echo "⚠️ 发现 $error_count 个错误/异常" | tee -a "$LOG_FILE"
            tail -200 "$TRAIN_LOG" | grep -i "error\|exception\|failed" | tail -3 | tee -a "$LOG_FILE"
        else
            echo "✅ 无错误" | tee -a "$LOG_FILE"
        fi
    else
        echo "⚠️ 训练日志不存在" | tee -a "$LOG_FILE"
    fi
    echo "" | tee -a "$LOG_FILE"
    
    # 5. 磁盘使用
    echo "--- 磁盘使用 ---" | tee -a "$LOG_FILE"
    df -h /workspace | tail -1 | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    
    # 6. 检查点文件
    echo "--- 检查点状态 ---" | tee -a "$LOG_FILE"
    checkpoint_dir="/workspace/Lightweight-Feedforward-3D-Reconstruction-work/outputs/checkpoints"
    if [ -d "$checkpoint_dir" ]; then
        ls -lh "$checkpoint_dir"/*.pth 2>/dev/null | tail -3 | tee -a "$LOG_FILE"
        checkpoint_count=$(ls -1 "$checkpoint_dir"/*.pth 2>/dev/null | wc -l)
        echo "检查点数量: $checkpoint_count" | tee -a "$LOG_FILE"
    else
        echo "检查点目录不存在" | tee -a "$LOG_FILE"
    fi
    echo "" | tee -a "$LOG_FILE"
    
    echo "============================================================" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    
    # 等待下一次监测
    if [ $(date +%s) -lt $end_time ]; then
        sleep $INTERVAL
    fi
done

echo "============================================================"
echo "监测完成！"
echo "============================================================"
echo "监测报告已保存到: $LOG_FILE"

