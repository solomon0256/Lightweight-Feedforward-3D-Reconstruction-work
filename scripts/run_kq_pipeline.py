#!/usr/bin/env python3
"""
K→Q 联合流程脚本

用途：
- 串联蒸馏(K) → 量化(Q) 完整流程
- 一键执行工程主线实验

运行示例：
    python scripts/run_kq_pipeline.py --dry-run
    python scripts/run_kq_pipeline.py --skip-distill  # 跳过蒸馏，直接量化
"""

import argparse
import sys
import subprocess
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.config import ExperimentConfig, get_project_root
from scripts.utils.logger import ExperimentLog, save_experiment_log


def run_command(cmd: list, description: str) -> int:
    """运行命令并打印输出"""
    print(f"\n{'='*60}")
    print(f"[STEP] {description}")
    print(f"{'='*60}")
    print(f"Command: {' '.join(cmd)}\n")
    
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    
    if result.returncode != 0:
        print(f"[ERROR] {description} failed with code {result.returncode}")
    else:
        print(f"[OK] {description} completed successfully")
    
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description='DUSt3R K→Q Pipeline (Distillation → Quantization)',
    )
    parser.add_argument('--project-root', type=str, default=None)
    parser.add_argument('--dry-run', action='store_true',
                        help='干跑模式')
    parser.add_argument('--skip-baseline', action='store_true',
                        help='跳过 baseline 评测')
    parser.add_argument('--skip-distill', action='store_true',
                        help='跳过蒸馏（使用现有 student）')
    parser.add_argument('--skip-quant', action='store_true',
                        help='跳过量化')
    parser.add_argument('--distill-epochs', type=int, default=None,
                        help='蒸馏 epoch 数')
    parser.add_argument('--quant-mode', type=str, default='ptq',
                        choices=['ptq', 'qat', 'auto'])
    
    args = parser.parse_args()
    
    root = Path(args.project_root) if args.project_root else get_project_root()
    python_exe = sys.executable
    
    print("=" * 60)
    print("DUSt3R K→Q Pipeline")
    print("=" * 60)
    print(f"  Project root: {root}")
    print(f"  Dry run: {args.dry_run}")
    print(f"  Skip baseline: {args.skip_baseline}")
    print(f"  Skip distill: {args.skip_distill}")
    print(f"  Skip quant: {args.skip_quant}")
    print("=" * 60)
    
    start_time = datetime.now()
    results = {}
    
    # ============ Step 0: Baseline 评测 ============
    if not args.skip_baseline:
        cmd = [
            python_exe, str(root / 'scripts' / 'baseline_eval.py'),
            '--exp-config', 'distill.yaml',
        ]
        if args.dry_run:
            cmd.append('--dry-run')
        
        ret = run_command(cmd, "Baseline Teacher Evaluation (P0)")
        results['baseline'] = ret
        
        if ret != 0 and not args.dry_run:
            print("[WARN] Baseline failed, but continuing...")
    
    # ============ Step 1: 蒸馏训练 ============
    if not args.skip_distill:
        cmd = [
            python_exe, str(root / 'scripts' / 'train_distill.py'),
            '--exp-config', 'distill.yaml',
        ]
        if args.dry_run:
            cmd.append('--dry-run')
        if args.distill_epochs:
            cmd.extend(['--max-epochs', str(args.distill_epochs)])
        
        ret = run_command(cmd, "Knowledge Distillation Training (P1/K-only)")
        results['distill'] = ret
        
        if ret != 0:
            print("[ERROR] Distillation failed, cannot continue to quantization")
            if not args.dry_run:
                return 1
    
    # ============ Step 2: 量化 ============
    if not args.skip_quant:
        # 使用蒸馏产出的 student 进行量化
        student_weights = root / 'outputs' / 'checkpoints' / 'student_fp32_best.pth'
        
        cmd = [
            python_exe, str(root / 'scripts' / 'quantize.py'),
            '--exp-config', 'quant.yaml',
            '--mode', args.quant_mode,
            '--export-onnx',
        ]
        
        if student_weights.exists():
            cmd.extend(['--model-weights', str(student_weights)])
        
        if args.dry_run:
            cmd.append('--dry-run')
        
        ret = run_command(cmd, f"Quantization ({args.quant_mode.upper()}) (P3/K→Q)")
        results['quant'] = ret
    
    # ============ 总结 ============
    elapsed = datetime.now() - start_time
    
    print("\n" + "=" * 60)
    print("K→Q Pipeline Complete!")
    print("=" * 60)
    print(f"  Total time: {elapsed}")
    print(f"  Results:")
    for step, ret in results.items():
        status = "✅" if ret == 0 else "❌"
        print(f"    {status} {step}: {'success' if ret == 0 else 'failed'}")
    
    # 检查产出物
    print("\n  Output artifacts:")
    artifacts = [
        ('Baseline log', root / 'logs' / 'baseline_teacher_v1.json'),
        ('Student checkpoint', root / 'outputs' / 'checkpoints' / 'student_fp32_best.pth'),
        ('Distill log', root / 'logs' / 'K_only_42.json'),
        ('Quantized model', root / 'outputs' / 'checkpoints' / f'quantized_{args.quant_mode}.pth'),
        ('ONNX model', root / 'outputs' / f'student_{args.quant_mode}_int8.onnx'),
    ]
    
    for name, path in artifacts:
        exists = "✅" if path.exists() else "❌"
        print(f"    {exists} {name}: {path.name}")
    
    print("=" * 60)
    
    # 返回总体状态
    return 0 if all(r == 0 for r in results.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
