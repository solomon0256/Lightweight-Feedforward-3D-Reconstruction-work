#!/usr/bin/env python3
"""快速发送实验通知"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.experiment_notifier import notify_completion

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--exp', type=str, default='K-only_real_data')
    parser.add_argument('--status', type=str, default='running', choices=['running', 'success', 'failed'])
    parser.add_argument('--message', type=str, default='')
    args = parser.parse_args()
    
    details = {}
    if args.message:
        details['message'] = args.message
    
    notify_completion(args.exp, args.status, details)

