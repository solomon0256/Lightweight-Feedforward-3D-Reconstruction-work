#!/usr/bin/env python3
"""
10分钟训练监测脚本
每1分钟检查一次训练状态、GPU占用、进度等
"""

import sys
import time
import subprocess
import re
from pathlib import Path
from datetime import datetime, timedelta

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

def get_gpu_info():
    """获取GPU信息"""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,temperature.gpu', 
             '--format=csv,noheader,nounits'],
            capture_output=True,
            text=True,
            check=True,
            timeout=5
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
        return {'error': str(e)}
    return {}

def get_training_process():
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
            if 'train_distill.py' in line and 'grep' not in line and 'monitor' not in line:
                parts = line.split()
                if len(parts) >= 11:
                    return {
                        'running': True,
                        'pid': parts[1],
                        'cpu': parts[2],
                        'mem': parts[3],
                        'time': parts[9] if len(parts) > 9 else 'N/A',
                    }
    except Exception as e:
        return {'error': str(e)}
    return {'running': False}

def get_training_progress():
    """获取训练进度"""
    log_dir = PROJECT_ROOT / 'logs'
    log_files = list(log_dir.glob('distill_training_real*.log'))
    
    if not log_files:
        return {'status': 'no_log_file'}
    
    # 选择最新的日志文件
    log_file = max(log_files, key=lambda p: p.stat().st_mtime)
    
    epochs = []
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            # 匹配: Epoch 6/30 | Train: 0.0159 | Val: 0.0165
            match = re.search(r'Epoch (\d+)/(\d+) \| Train: ([\d.]+) \| Val: ([\d.]+)', line)
            if match:
                epochs.append({
                    'epoch': int(match.group(1)),
                    'total': int(match.group(2)),
                    'train_loss': float(match.group(3)),
                    'val_loss': float(match.group(4)),
                })
    
    if not epochs:
        return {'status': 'no_epochs', 'log_file': log_file.name}
    
    latest = epochs[-1]
    return {
        'status': 'training',
        'log_file': log_file.name,
        'current_epoch': latest['epoch'],
        'total_epochs': latest['total'],
        'train_loss': latest['train_loss'],
        'val_loss': latest['val_loss'],
        'progress_pct': (latest['epoch'] / latest['total']) * 100,
        'total_epochs_completed': len(set(e['epoch'] for e in epochs)),
    }

def get_checkpoint_info():
    """获取检查点信息"""
    checkpoint_dir = PROJECT_ROOT / 'outputs' / 'checkpoints'
    if not checkpoint_dir.exists():
        return {'checkpoints': 0}
    
    checkpoints = list(checkpoint_dir.glob('*.pth'))
    if not checkpoints:
        return {'checkpoints': 0}
    
    latest = max(checkpoints, key=lambda p: p.stat().st_mtime)
    return {
        'checkpoints': len(checkpoints),
        'latest': latest.name,
        'latest_size_mb': round(latest.stat().st_size / (1024 * 1024), 2),
        'latest_time': datetime.fromtimestamp(latest.stat().st_mtime).strftime('%H:%M:%S'),
    }

def get_system_resources():
    """获取系统资源"""
    try:
        # CPU和内存
        result = subprocess.run(
            ['free', '-h'],
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        lines = result.stdout.split('\n')
        mem_line = lines[1] if len(lines) > 1 else ''
        mem_parts = mem_line.split()
        
        return {
            'mem_total': mem_parts[1] if len(mem_parts) > 1 else 'N/A',
            'mem_used': mem_parts[2] if len(mem_parts) > 2 else 'N/A',
            'mem_available': mem_parts[6] if len(mem_parts) > 6 else 'N/A',
        }
    except Exception as e:
        return {'error': str(e)}

def print_status(check_num, total_checks, gpu_info, process_info, progress_info, checkpoint_info, system_info):
    """打印状态"""
    print(f"\n{'='*80}")
    print(f"[检查 #{check_num}/{total_checks}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}")
    
    # GPU信息
    print("\n📊 GPU状态:")
    if 'error' in gpu_info:
        print(f"  ❌ 获取GPU信息失败: {gpu_info['error']}")
    else:
        print(f"  GPU使用率: {gpu_info.get('gpu_util', 0):.1f}%")
        print(f"  显存使用率: {gpu_info.get('mem_util', 0):.1f}%")
        print(f"  显存使用: {gpu_info.get('mem_used_mb', 0):.0f}MB / {gpu_info.get('mem_total_mb', 0):.0f}MB")
        print(f"  功耗: {gpu_info.get('power_w', 0):.1f}W")
        print(f"  温度: {gpu_info.get('temp_c', 0):.0f}°C")
    
    # 训练进程
    print("\n🔄 训练进程:")
    if 'error' in process_info:
        print(f"  ❌ 获取进程信息失败: {process_info['error']}")
    elif process_info.get('running'):
        print(f"  ✅ 运行中 (PID: {process_info.get('pid', 'N/A')})")
        print(f"  CPU: {process_info.get('cpu', 'N/A')}%")
        print(f"  内存: {process_info.get('mem', 'N/A')}%")
        print(f"  运行时间: {process_info.get('time', 'N/A')}")
    else:
        print(f"  ⚠️  未找到训练进程")
    
    # 训练进度
    print("\n📈 训练进度:")
    if progress_info.get('status') == 'no_log_file':
        print(f"  ⚠️  未找到训练日志文件")
    elif progress_info.get('status') == 'no_epochs':
        print(f"  ⚠️  日志文件存在但无epoch记录: {progress_info.get('log_file', 'N/A')}")
    elif progress_info.get('status') == 'training':
        print(f"  ✅ 训练中")
        print(f"  日志文件: {progress_info.get('log_file', 'N/A')}")
        print(f"  当前Epoch: {progress_info.get('current_epoch', 'N/A')}/{progress_info.get('total_epochs', 'N/A')} ({progress_info.get('progress_pct', 0):.1f}%)")
        print(f"  训练Loss: {progress_info.get('train_loss', 0):.6f}")
        print(f"  验证Loss: {progress_info.get('val_loss', 0):.6f}")
        print(f"  已完成Epoch数: {progress_info.get('total_epochs_completed', 0)}")
    
    # 检查点
    print("\n💾 检查点:")
    if checkpoint_info.get('checkpoints', 0) == 0:
        print(f"  ⚠️  无检查点")
    else:
        print(f"  ✅ 检查点数量: {checkpoint_info.get('checkpoints', 0)}")
        print(f"  最新: {checkpoint_info.get('latest', 'N/A')}")
        print(f"  大小: {checkpoint_info.get('latest_size_mb', 0):.2f}MB")
        print(f"  时间: {checkpoint_info.get('latest_time', 'N/A')}")
    
    # 系统资源
    print("\n💻 系统资源:")
    if 'error' in system_info:
        print(f"  ❌ 获取系统信息失败: {system_info['error']}")
    else:
        print(f"  内存: {system_info.get('mem_used', 'N/A')} / {system_info.get('mem_total', 'N/A')}")
        print(f"  可用内存: {system_info.get('mem_available', 'N/A')}")
    
    print(f"{'='*80}\n")

def main():
    duration_minutes = 10
    interval_seconds = 60  # 每1分钟检查一次
    total_checks = duration_minutes
    
    print("="*80)
    print("开始10分钟训练监测")
    print("="*80)
    print(f"监测时长: {duration_minutes}分钟")
    print(f"检查间隔: {interval_seconds}秒")
    print(f"总检查次数: {total_checks}次")
    print("="*80)
    
    start_time = datetime.now()
    check_num = 0
    
    try:
        while True:
            check_num += 1
            elapsed = (datetime.now() - start_time).total_seconds() / 60
            
            # 收集信息
            gpu_info = get_gpu_info()
            process_info = get_training_process()
            progress_info = get_training_progress()
            checkpoint_info = get_checkpoint_info()
            system_info = get_system_resources()
            
            # 打印状态
            print_status(check_num, total_checks, gpu_info, process_info, progress_info, checkpoint_info, system_info)
            
            # 检查是否达到时间
            if elapsed >= duration_minutes:
                print(f"\n✅ 监测完成（{duration_minutes}分钟）")
                break
            
            # 等待下一次检查
            if check_num < total_checks:
                wait_seconds = interval_seconds
                print(f"等待 {wait_seconds} 秒后进行下一次检查...\n")
                time.sleep(wait_seconds)
    
    except KeyboardInterrupt:
        print("\n\n⚠️  监测被用户中断")
    
    # 最终总结
    print("\n" + "="*80)
    print("监测总结")
    print("="*80)
    final_gpu = get_gpu_info()
    final_process = get_training_process()
    final_progress = get_training_progress()
    
    print(f"\n最终状态:")
    if 'error' not in final_gpu:
        print(f"  GPU使用率: {final_gpu.get('gpu_util', 0):.1f}%")
    if final_process.get('running'):
        print(f"  训练进程: ✅ 运行中")
    else:
        print(f"  训练进程: ⚠️  未运行")
    if final_progress.get('status') == 'training':
        print(f"  训练进度: Epoch {final_progress.get('current_epoch', 'N/A')}/{final_progress.get('total_epochs', 'N/A')}")
    print("="*80)

if __name__ == '__main__':
    main()


