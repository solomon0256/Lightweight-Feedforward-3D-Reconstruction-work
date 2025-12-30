#!/usr/bin/env python3
"""
实验完成通知脚本

功能：
- 监听实验完成状态
- 发送通知到指定文件
- 可以通过终端监听该文件

使用方法：
1. 在实验脚本中调用：experiment_notifier.notify_completion(experiment_name, status, details)
2. 在终端监听：tail -f logs/experiment_notifications.txt
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

def notify_completion(
    experiment_name: str,
    status: str,  # "success", "failed", "running"
    details: Optional[Dict[str, Any]] = None,
    log_file: str = "logs/experiment_notifications.txt"
):
    """
    发送实验完成通知
    
    Args:
        experiment_name: 实验名称（如 "K-only", "Q-only", "K→Q"）
        status: 状态（"success", "failed", "running"）
        details: 详细信息字典
        log_file: 通知文件路径
    """
    # 确保日志目录存在
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 构建通知消息
    notification = {
        "timestamp": datetime.now().isoformat(),
        "experiment": experiment_name,
        "status": status,
        "details": details or {}
    }
    
    # 写入文件（追加模式）
    with open(log_path, 'a', encoding='utf-8') as f:
        # 写入JSON格式（便于解析）
        f.write(json.dumps(notification, ensure_ascii=False, indent=2) + "\n")
        f.write("=" * 80 + "\n")
        
        # 写入人类可读格式
        f.write(f"[{notification['timestamp']}] {experiment_name}: {status.upper()}\n")
        if details:
            for key, value in details.items():
                f.write(f"  {key}: {value}\n")
        f.write("=" * 80 + "\n\n")
    
    # 同时写入标准输出（如果从脚本调用）
    print(f"\n{'='*80}")
    print(f"[{notification['timestamp']}] 实验完成通知: {experiment_name}")
    print(f"状态: {status.upper()}")
    if details:
        for key, value in details.items():
            print(f"  {key}: {value}")
    print(f"{'='*80}\n")
    
    return notification

def check_experiment_status(experiment_name: str, log_file: str = "logs/experiment_notifications.txt") -> Optional[Dict]:
    """
    检查实验状态
    
    Returns:
        最新的通知字典，如果不存在返回None
    """
    log_path = Path(log_file)
    if not log_path.exists():
        return None
    
    # 读取最后几行，查找对应实验的通知
    with open(log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 从后往前查找
    for i in range(len(lines) - 1, -1, -1):
        if experiment_name in lines[i] and "status" in lines[i].lower():
            # 尝试解析JSON
            try:
                # 找到JSON块
                for j in range(i, max(0, i-20), -1):
                    if lines[j].strip().startswith("{"):
                        json_str = ""
                        for k in range(j, min(len(lines), j+20)):
                            json_str += lines[k]
                            if lines[k].strip().endswith("}"):
                                return json.loads(json_str)
            except:
                pass
    
    return None

if __name__ == "__main__":
    # 测试
    notify_completion(
        "test_experiment",
        "success",
        {
            "checkpoint": "outputs/checkpoints/test.pth",
            "accuracy": "95.2%",
            "time": "2.5 hours"
        }
    )

