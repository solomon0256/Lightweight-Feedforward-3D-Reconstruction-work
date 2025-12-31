#!/usr/bin/env python3
"""
定期发送训练进度通知

每隔指定时间（默认10分钟）检查训练状态并发送进度通知
"""

import sys
import time
import re
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# 添加项目根目录到路径
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.experiment_notifier import notify_completion

def get_gpu_info() -> Dict[str, Any]:
    """获取GPU信息"""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,temperature.gpu', 
             '--format=csv,noheader,nounits'],
            capture_output=True,
            text=True,
            check=True
        )
        parts = result.stdout.strip().split(', ')
        if len(parts) >= 6:
            return {
                'gpu_util': float(parts[0]),
                'mem_util': float(parts[1]),
                'mem_used_mb': float(parts[2]),
                'mem_total_mb': float(parts[3]),
                'power_w': float(parts[4]),
                'temp_c': float(parts[5]),
            }
    except Exception as e:
        print(f"[WARN] 获取GPU信息失败: {e}")
    return {}

def get_training_progress(log_file: Path) -> Dict[str, Any]:
    """从训练日志获取进度信息"""
    if not log_file.exists():
        return {}
    
    epochs = []
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            # 匹配: Epoch 6/30 | Train: 0.0159 | Val: 0.0165
            match = re.search(r'Epoch (\d+)/30', line)
            if match:
                epoch_num = int(match.group(1))
                # 提取loss
                train_match = re.search(r'Train: ([\d.]+)', line)
                val_match = re.search(r'Val: ([\d.]+)', line)
                train_loss = float(train_match.group(1)) if train_match else None
                val_loss = float(val_match.group(1)) if val_match else None
                epochs.append({
                    'epoch': epoch_num,
                    'train_loss': train_loss,
                    'val_loss': val_loss,
                    'line': line.strip()
                })
    
    if not epochs:
        return {}
    
    latest = epochs[-1]
    first = epochs[0] if len(epochs) > 1 else latest
    
    # 计算每个epoch的平均时间（如果日志有时间戳）
    # 这里使用估算：假设每个epoch约10分钟
    per_epoch_minutes = 10.0
    
    current_epoch = latest['epoch']
    total_epochs = 30
    remaining_epochs = total_epochs - current_epoch
    remaining_minutes = remaining_epochs * per_epoch_minutes
    remaining_hours = remaining_minutes / 60
    
    # 估算完成时间
    finish_time = datetime.now() + timedelta(minutes=remaining_minutes)
    
    return {
        'current_epoch': current_epoch,
        'total_epochs': total_epochs,
        'progress_pct': (current_epoch / total_epochs) * 100,
        'train_loss': latest['train_loss'],
        'val_loss': latest['val_loss'],
        'per_epoch_minutes': per_epoch_minutes,
        'remaining_epochs': remaining_epochs,
        'remaining_hours': remaining_hours,
        'remaining_minutes': remaining_minutes,
        'finish_time': finish_time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_epochs_completed': len(set(e['epoch'] for e in epochs)),
    }

def get_process_info() -> Dict[str, Any]:
    """获取训练进程信息"""
    try:
        result = subprocess.run(
            ['ps', 'aux'],
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        lines = result.stdout.split('\n')
        for line in lines:
            # 匹配train_distill.py进程，排除grep和notifier进程
            if ('train_distill.py' in line or 'train_distill' in line) and 'grep' not in line and 'periodic_progress_notifier' not in line and 'send_notification' not in line:
                parts = line.split()
                if len(parts) >= 11:
                    try:
                        return {
                            'cpu_percent': float(parts[2]),
                            'mem_percent': float(parts[3]),
                            'cpu_time': parts[9] if len(parts) > 9 else 'N/A',
                            'running': True,
                        }
                    except (ValueError, IndexError):
                        continue
    except subprocess.TimeoutExpired:
        print(f"[WARN] 获取进程信息超时")
    except Exception as e:
        print(f"[WARN] 获取进程信息失败: {e}")
    return {'running': False}

def get_checkpoint_info() -> Dict[str, Any]:
    """获取检查点信息"""
    checkpoint_dir = PROJECT_ROOT / 'outputs' / 'checkpoints'
    if not checkpoint_dir.exists():
        return {}
    
    checkpoints = list(checkpoint_dir.glob('*.pth'))
    if not checkpoints:
        return {}
    
    # 获取最新检查点
    latest = max(checkpoints, key=lambda p: p.stat().st_mtime)
    size_mb = latest.stat().st_size / (1024 * 1024)
    
    return {
        'checkpoint_count': len(checkpoints),
        'latest_checkpoint': latest.name,
        'latest_size_mb': round(size_mb, 2),
        'latest_time': datetime.fromtimestamp(latest.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
    }

def send_progress_notification(interval_minutes: int = 10, log_file_name: str = None):
    """发送进度通知"""
    if log_file_name is None:
        # 自动检测最新的训练日志文件
        log_dir = PROJECT_ROOT / 'logs'
        log_files = list(log_dir.glob('distill_training_real*.log'))
        if log_files:
            # 选择最新的日志文件
            log_file = max(log_files, key=lambda p: p.stat().st_mtime)
        else:
            # 默认文件名
            log_file = PROJECT_ROOT / 'logs' / 'distill_training_real_v2.log'
    else:
        log_file = PROJECT_ROOT / 'logs' / log_file_name
    
    # 收集信息
    gpu_info = get_gpu_info()
    progress = get_training_progress(log_file)
    process_info = get_process_info()
    checkpoint_info = get_checkpoint_info()
    
    # 构建通知详情
    details = {
        'message': '训练进度更新',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    
    # GPU信息
    if gpu_info:
        details['gpu'] = {
            'utilization': f"{gpu_info['gpu_util']:.1f}%",
            'memory_utilization': f"{gpu_info['mem_util']:.1f}%",
            'memory_used': f"{gpu_info['mem_used_mb']:.0f}MB",
            'memory_total': f"{gpu_info['mem_total_mb']:.0f}MB",
            'power': f"{gpu_info['power_w']:.1f}W",
            'temperature': f"{gpu_info['temp_c']:.0f}°C",
        }
    
    # 训练进度
    if progress:
        details['progress'] = {
            'current_epoch': f"{progress['current_epoch']}/{progress['total_epochs']}",
            'progress_percent': f"{progress['progress_pct']:.1f}%",
            'train_loss': f"{progress['train_loss']:.6f}" if progress['train_loss'] else 'N/A',
            'val_loss': f"{progress['val_loss']:.6f}" if progress['val_loss'] else 'N/A',
            'remaining_epochs': progress['remaining_epochs'],
            'remaining_time': f"{progress['remaining_hours']:.1f}小时 ({progress['remaining_minutes']:.0f}分钟)",
            'estimated_finish': progress['finish_time'],
            'per_epoch_time': f"{progress['per_epoch_minutes']:.1f}分钟",
        }
    
    # 进程信息
    if process_info:
        details['process'] = {
            'running': process_info['running'],
            'cpu_percent': f"{process_info.get('cpu_percent', 0):.1f}%",
            'mem_percent': f"{process_info.get('mem_percent', 0):.1f}%",
        }
    
    # 检查点信息
    if checkpoint_info:
        details['checkpoints'] = checkpoint_info
    
    # 发送通知
    notify_completion('K-only_real_data', 'running', details)
    
    # 打印摘要
    print(f"\n{'='*80}")
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 进度通知已发送")
    if progress:
        print(f"  进度: {progress['current_epoch']}/{progress['total_epochs']} ({progress['progress_pct']:.1f}%)")
        print(f"  剩余时间: {progress['remaining_hours']:.1f}小时")
        print(f"  预计完成: {progress['finish_time']}")
    if gpu_info:
        print(f"  GPU使用率: {gpu_info['gpu_util']:.1f}%")
    print(f"{'='*80}\n")

def main():
    import argparse
    parser = argparse.ArgumentParser(description='定期发送训练进度通知')
    parser.add_argument('--interval', type=int, default=10, help='通知间隔（分钟）')
    parser.add_argument('--once', action='store_true', help='只发送一次，不循环')
    parser.add_argument('--duration', type=int, default=None, help='监测持续时间（分钟），None表示无限循环')
    parser.add_argument('--log-file', type=str, default=None, help='训练日志文件名（默认自动检测最新）')
    args = parser.parse_args()
    
    if args.once:
        # 只发送一次
        send_progress_notification(args.interval, args.log_file)
    else:
        # 循环发送
        start_time = datetime.now()
        duration_minutes = args.duration
        if duration_minutes:
            print(f"开始定期发送进度通知（每{args.interval}分钟，持续{duration_minutes}分钟）")
        else:
            print(f"开始定期发送进度通知（每{args.interval}分钟）")
        print(f"按Ctrl+C停止")
        print("="*80)
        
        try:
            iteration = 0
            while True:
                iteration += 1
                elapsed_minutes = (datetime.now() - start_time).total_seconds() / 60
                
                # 发送通知
                send_progress_notification(args.interval, args.log_file)
                
                # 检查是否达到持续时间
                if duration_minutes and elapsed_minutes >= duration_minutes:
                    print(f"\n监测时间已到（{duration_minutes}分钟），停止发送通知")
                    break
                
                # 等待下一次通知
                time.sleep(args.interval * 60)
        except KeyboardInterrupt:
            print("\n停止发送通知")

if __name__ == '__main__':
    main()

