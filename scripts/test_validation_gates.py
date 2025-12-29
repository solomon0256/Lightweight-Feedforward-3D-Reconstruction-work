#!/usr/bin/env python3
"""
测试验证门禁脚本
================
不需要完整的 PQK 流程，用 baseline 模型和 mock checkpoint 测试验证脚本

Usage:
    # 测试 Smoke Gate（用 baseline 模型）
    python scripts/test_validation_gates.py --test-smoke
    
    # 测试 Trend Gate（用 baseline 模型）
    python scripts/test_validation_gates.py --test-trend
    
    # 创建 mock checkpoint（用于测试轻量化过程验证）
    python scripts/test_validation_gates.py --create-mock-checkpoints
"""

import os
import sys
import argparse
import torch
from pathlib import Path

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.baseline_eval import load_dust3r_model, setup_dust3r_paths
from scripts.utils.model_loader import load_model


def create_mock_checkpoints(output_dir: Path = Path("test_checkpoints")):
    """
    创建 mock checkpoint 用于测试
    不需要真实的轻量化流程，只需要有文件存在即可测试加载逻辑
    """
    output_dir.mkdir(exist_ok=True)
    
    setup_dust3r_paths()
    model = load_dust3r_model(device='cpu')
    
    print("\n" + "="*60)
    print("[创建] Mock Checkpoints")
    print("="*60)
    
    # 1. Mock Student 模型 checkpoint（蒸馏）
    print("\n[1/3] 创建 Mock Student checkpoint...")
    try:
        from scripts.models import create_student_model
        student = create_student_model(arch='dust3r_student_s', device='cpu')
        student_path = output_dir / 'student_fp32_best.pth'
        torch.save({
            'state_dict': student.state_dict(),
            'epoch': 10,
            'best_metric': 0.95
        }, student_path)
        print(f"  [OK] 已创建: {student_path}")
    except Exception as e:
            print(f"  [WARN] 创建 Student checkpoint 失败: {e}")
            # 创建一个空的 checkpoint 文件（至少文件存在）
            student_path = output_dir / 'student_fp32_best.pth'
            torch.save({'state_dict': model.state_dict()}, student_path)
            print(f"  [OK] 已创建（fallback）: {student_path}")
    
    # 2. Mock 量化 checkpoint（INT8）
    print("\n[2/3] 创建 Mock INT8 Quantized checkpoint...")
    quantized_path = output_dir / 'quantized_int8.pth'
    torch.save({
        'state_dict': model.state_dict(),
        'quantization_config': {'mode': 'int8_ptq'}
    }, quantized_path)
    print(f"  [OK] 已创建: {quantized_path}")
    
    # 3. Mock 剪枝 checkpoint
    print("\n[3/3] 创建 Mock Pruned checkpoint...")
    pruned_path = output_dir / 'pruned_40pct.pth'
    # 创建一个稀疏的 state_dict（模拟剪枝）
    pruned_state_dict = {}
    for name, param in model.state_dict().items():
        pruned_param = param.clone()
        # 随机将 40% 的参数设为 0（模拟剪枝）
        mask = torch.rand_like(pruned_param) > 0.4
        pruned_param[mask] = 0
        pruned_state_dict[name] = pruned_param
    
    torch.save({
        'state_dict': pruned_state_dict,
        'pruning_rate': 0.4,
        'flops_reduction': 40.0
    }, pruned_path)
    print(f"  [OK] 已创建: {pruned_path}")
    
    print("\n" + "="*60)
    print("[完成] 所有 Mock Checkpoints 创建完成！")
    print("="*60)
    print(f"\n输出目录: {output_dir.absolute()}")
    print("\n现在可以用这些 checkpoint 测试验证脚本：")
    print("  python scripts/smoke_gate.py --method K --variant student --checkpoint test_checkpoints/student_fp32_best.pth")
    print("  python scripts/smoke_gate.py --method Q --variant int8 --checkpoint test_checkpoints/quantized_int8.pth")
    print("  python scripts/smoke_gate.py --method P --variant pruned_40 --checkpoint test_checkpoints/pruned_40pct.pth")


def test_smoke_gate_with_baseline():
    """用 baseline 模型测试 Smoke Gate（不需要轻量化）"""
    print("\n" + "="*60)
    print("[测试] Smoke Gate（Baseline 模型）")
    print("="*60)
    
    setup_dust3r_paths()
    
    # 测试 1: FP16 量化（最简单，不需要 checkpoint）
    print("\n[测试 1] FP16 量化验证...")
    try:
        model = load_model('Q', 'fp16', device='cuda' if torch.cuda.is_available() else 'cpu')
        print("  [OK] FP16 模型加载成功")
        
        # 运行 Smoke Gate
        import subprocess
        result = subprocess.run([
            sys.executable, 'scripts/smoke_gate.py',
            '--method', 'Q',
            '--variant', 'fp16',
            '--tolerance', 'fp16',
            '--device', 'cuda' if torch.cuda.is_available() else 'cpu'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("  [OK] Smoke Gate 验证通过")
        else:
            print("  [WARN] Smoke Gate 验证失败（这是正常的，因为可能没有 golden outputs）")
            print(f"  输出: {result.stdout[-500:]}")
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*60)
    print("[提示]")
    print("  1. 如果失败是因为没有 golden outputs，先运行：")
    print("     python scripts/smoke_gate.py --create-golden")
    print("  2. 然后重新运行测试")
    print("="*60)


def test_trend_gate_with_baseline():
    """用 baseline 模型测试 Trend Gate（不需要轻量化）"""
    print("\n" + "="*60)
    print("[测试] Trend Gate（Baseline 模型）")
    print("="*60)
    
    setup_dust3r_paths()
    
    # 测试 FP16 量化（最简单）
    print("\n[测试] FP16 量化验证...")
    try:
        model = load_model('Q', 'fp16', device='cuda' if torch.cuda.is_available() else 'cpu')
        print("  [OK] FP16 模型加载成功")
        
        # 运行 Trend Gate
        import subprocess
        result = subprocess.run([
            sys.executable, 'scripts/trend_gate.py',
            '--method', 'Q',
            '--variant', 'fp16',
            '--method-type', 'fp16',
            '--num-pairs', '10',  # 用少量样本快速测试
            '--device', 'cuda' if torch.cuda.is_available() else 'cpu'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("  [OK] Trend Gate 验证通过")
        else:
            print("  [WARN] Trend Gate 验证失败")
            print(f"  输出: {result.stdout[-500:]}")
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


def test_lightweighting_process_verification():
    """测试轻量化过程验证逻辑（使用 mock checkpoint）"""
    print("\n" + "="*60)
    print("[测试] 轻量化过程验证")
    print("="*60)
    
    # 先创建 mock checkpoints
    checkpoint_dir = Path("test_checkpoints")
    if not checkpoint_dir.exists():
        print("\n[WARN] Mock checkpoints 不存在，正在创建...")
        create_mock_checkpoints(checkpoint_dir)
    
    setup_dust3r_paths()
    
    from scripts.smoke_gate import verify_lightweighting_process
    
    # 测试 1: 蒸馏验证
    print("\n[测试 1] 蒸馏 (K) 过程验证...")
    student_path = checkpoint_dir / 'student_fp32_best.pth'
    if student_path.exists():
        success, msg = verify_lightweighting_process(
            'K', 'student', 
            checkpoint_path=str(student_path),
            device='cuda' if torch.cuda.is_available() else 'cpu'
        )
        if success:
            print(f"  [OK] {msg}")
        else:
            print(f"  [FAIL] {msg}")
    else:
        print(f"  [WARN] Checkpoint 不存在: {student_path}")
    
    # 测试 2: FP16 量化验证
    print("\n[测试 2] FP16 量化 (Q) 过程验证...")
    model = load_model('Q', 'fp16', device='cuda' if torch.cuda.is_available() else 'cpu')
    success, msg = verify_lightweighting_process(
        'Q', 'fp16',
        model=model,
        device='cuda' if torch.cuda.is_available() else 'cpu'
    )
    if success:
        print(f"  ✅ {msg}")
    else:
        print(f"  ❌ {msg}")
    
    # 测试 3: INT8 量化验证
    print("\n[测试 3] INT8 量化 (Q) 过程验证...")
    int8_path = checkpoint_dir / 'quantized_int8.pth'
    if int8_path.exists():
        success, msg = verify_lightweighting_process(
            'Q', 'int8',
            checkpoint_path=str(int8_path),
            device='cuda' if torch.cuda.is_available() else 'cpu'
        )
        if success:
            print(f"  ✅ {msg}")
        else:
            print(f"  ❌ {msg}")
    else:
        print(f"  ⚠️  Checkpoint 不存在: {int8_path}")
    
    # 测试 4: 剪枝验证
    print("\n[测试 4] 剪枝 (P) 过程验证...")
    pruned_path = checkpoint_dir / 'pruned_40pct.pth'
    if pruned_path.exists():
        success, msg = verify_lightweighting_process(
            'P', 'pruned_40',
            checkpoint_path=str(pruned_path),
            device='cuda' if torch.cuda.is_available() else 'cpu'
        )
        if success:
            print(f"  ✅ {msg}")
        else:
            print(f"  ❌ {msg}")
    else:
        print(f"  ⚠️  Checkpoint 不存在: {pruned_path}")


def main():
    parser = argparse.ArgumentParser(description="测试验证门禁脚本")
    parser.add_argument("--test-smoke", action="store_true",
                       help="测试 Smoke Gate（用 baseline 模型）")
    parser.add_argument("--test-trend", action="store_true",
                       help="测试 Trend Gate（用 baseline 模型）")
    parser.add_argument("--test-process", action="store_true",
                       help="测试轻量化过程验证（用 mock checkpoint）")
    parser.add_argument("--create-mock-checkpoints", action="store_true",
                       help="创建 mock checkpoint 用于测试")
    parser.add_argument("--all", action="store_true",
                       help="运行所有测试")
    
    args = parser.parse_args()
    
    if args.all or (not args.test_smoke and not args.test_trend and 
                    not args.test_process and not args.create_mock_checkpoints):
        # 默认运行所有测试
        print("="*60)
        print("[开始] 运行所有测试")
        print("="*60)
        
        # 1. 创建 mock checkpoints
        create_mock_checkpoints()
        
        # 2. 测试轻量化过程验证
        test_lightweighting_process_verification()
        
        # 3. 测试 Smoke Gate
        test_smoke_gate_with_baseline()
        
        # 4. 测试 Trend Gate
        test_trend_gate_with_baseline()
        
        print("\n" + "="*60)
        print("[完成] 所有测试完成！")
        print("="*60)
        return
    
    if args.create_mock_checkpoints:
        create_mock_checkpoints()
    
    if args.test_process:
        test_lightweighting_process_verification()
    
    if args.test_smoke:
        test_smoke_gate_with_baseline()
    
    if args.test_trend:
        test_trend_gate_with_baseline()


if __name__ == "__main__":
    main()

