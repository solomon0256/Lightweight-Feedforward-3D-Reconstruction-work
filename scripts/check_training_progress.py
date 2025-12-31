#!/usr/bin/env python3
"""检查训练进度和预计完成时间"""

import re
from datetime import datetime, timedelta
from pathlib import Path

def parse_log_file(log_file):
    """解析训练日志，提取epoch信息"""
    epochs = []
    
    with open(log_file, 'r') as f:
        for line in f:
            # 匹配: Epoch 5/30 | Train: 0.0160 | Val: 0.0165
            match = re.search(r'Epoch (\d+)/30', line)
            if match:
                epoch_num = int(match.group(1))
                # 提取时间戳（如果有）
                time_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if time_match:
                    epoch_time = datetime.strptime(time_match.group(1), '%Y-%m-%d %H:%M:%S')
                else:
                    epoch_time = None
                epochs.append((epoch_num, epoch_time, line.strip()))
    
    return epochs

def calculate_progress(epochs):
    """计算进度和预计完成时间"""
    if not epochs:
        return None
    
    total_epochs = 30
    current_epoch = epochs[-1][0]
    progress_pct = (current_epoch / total_epochs) * 100
    
    # 计算每个epoch的平均时间
    if len(epochs) >= 2 and epochs[-1][1] and epochs[0][1]:
        total_time = (epochs[-1][1] - epochs[0][1]).total_seconds()
        epochs_elapsed = current_epoch - epochs[0][0]
        if epochs_elapsed > 0:
            per_epoch_seconds = total_time / epochs_elapsed
        else:
            per_epoch_seconds = 600  # 默认10分钟
    else:
        # 如果没有时间戳，使用估算
        per_epoch_seconds = 600  # 默认10分钟
    
    remaining_epochs = total_epochs - current_epoch
    remaining_seconds = remaining_epochs * per_epoch_seconds
    remaining_hours = remaining_seconds / 3600
    
    # 估算完成时间
    if epochs[-1][1]:
        finish_time = epochs[-1][1] + timedelta(seconds=remaining_seconds)
    else:
        finish_time = datetime.now() + timedelta(seconds=remaining_seconds)
    
    return {
        'current_epoch': current_epoch,
        'total_epochs': total_epochs,
        'progress_pct': progress_pct,
        'per_epoch_minutes': per_epoch_seconds / 60,
        'remaining_epochs': remaining_epochs,
        'remaining_hours': remaining_hours,
        'finish_time': finish_time,
    }

def main():
    log_file = Path('/workspace/Lightweight-Feedforward-3D-Reconstruction-work/logs/distill_training_real.log')
    
    if not log_file.exists():
        print("训练日志不存在")
        return
    
    epochs = parse_log_file(log_file)
    
    if not epochs:
        print("未找到epoch信息")
        return
    
    print("="*60)
    print("训练进度分析")
    print("="*60)
    print(f"\n当前Epoch: {epochs[-1][0]}/30")
    print(f"已完成Epochs: {len(set(e[0] for e in epochs))}")
    print(f"\n最近5个Epochs:")
    for epoch_num, epoch_time, line in epochs[-5:]:
        time_str = epoch_time.strftime('%H:%M:%S') if epoch_time else 'N/A'
        print(f"  Epoch {epoch_num}/30 ({time_str})")
    
    progress = calculate_progress(epochs)
    if progress:
        print(f"\n{'='*60}")
        print("进度统计")
        print(f"{'='*60}")
        print(f"当前进度: {progress['current_epoch']}/{progress['total_epochs']} = {progress['progress_pct']:.1f}%")
        print(f"每个Epoch约: {progress['per_epoch_minutes']:.1f}分钟")
        print(f"剩余Epochs: {progress['remaining_epochs']}")
        print(f"预计剩余时间: {progress['remaining_hours']:.1f}小时 ({progress['remaining_hours']*60:.0f}分钟)")
        print(f"预计完成时间: {progress['finish_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 判断是否今晚完成
        now = datetime.now()
        tonight = now.replace(hour=23, minute=59, second=59)
        if progress['finish_time'] < tonight:
            print(f"\n✅ 预计今晚 ({tonight.strftime('%H:%M')}) 前完成！")
        else:
            print(f"\n⚠️ 预计明天完成")
    
    print("="*60)

if __name__ == '__main__':
    main()

