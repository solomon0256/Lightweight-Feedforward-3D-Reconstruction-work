#!/usr/bin/env python3
"""
带完整验证的实验运行脚本

功能：
- 实验前完整验证
- 运行实验
- 实验完成后发送通知
- 详细日志记录

使用方法：
    python3 scripts/run_experiment_with_verification.py --exp K-only
    python3 scripts/run_experiment_with_verification.py --exp Q-only
    python3 scripts/run_experiment_with_verification.py --exp K-to-Q
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

from scripts.verify_experiment_setup import ExperimentVerifier
from scripts.experiment_notifier import notify_completion

def run_verification(exp_name: str, project_root: Path) -> bool:
    """运行实验前验证"""
    print("="*80)
    print(f"实验前完整验证: {exp_name}")
    print("="*80)
    
    verifier = ExperimentVerifier(project_root)
    
    if exp_name == "K-only":
        ok = verifier.verify_k_only_setup()
    elif exp_name == "Q-only":
        ok = verifier.verify_q_only_setup()
    elif exp_name == "K-to-Q":
        ok = verifier.verify_k_to_q_setup()
    else:
        print(f"未知实验: {exp_name}")
        return False
    
    # 生成报告
    report_path = verifier.generate_report()
    
    # 打印摘要
    print("\n" + "="*80)
    print("验证摘要")
    print("="*80)
    print(f"错误: {len(verifier.errors)} 个")
    print(f"警告: {len(verifier.warnings)} 个")
    print(f"信息: {len(verifier.info)} 条")
    
    if verifier.errors:
        print("\n❌ 发现错误，请修复后再开始实验！")
        for error in verifier.errors:
            print(f"  {error}")
        return False
    elif verifier.warnings:
        print("\n⚠️ 发现警告，请检查后继续")
        for warning in verifier.warnings:
            print(f"  {warning}")
        return True
    else:
        print("\n✅ 所有验证通过，可以开始实验！")
        return True

def run_experiment(exp_name: str, project_root: Path) -> int:
    """运行实验"""
    print("="*80)
    print(f"开始运行实验: {exp_name}")
    print("="*80)
    
    if exp_name == "K-only":
        cmd = [
            "python3", "scripts/train_distill.py",
            "--exp-config", "expconfigs/distill.yaml"
        ]
    elif exp_name == "Q-only":
        cmd = [
            "python3", "scripts/quantize.py",
            "--exp-config", "expconfigs/quant.yaml",
            "--mode", "auto"
        ]
    elif exp_name == "K-to-Q":
        # 检查K-only是否完成
        student_path = project_root / "outputs" / "checkpoints" / "student_fp32_best.pth"
        if not student_path.exists():
            print("❌ 错误: K-only实验未完成，请先运行K-only实验")
            notify_completion(
                "K-to-Q",
                "failed",
                {"error": "K-only实验未完成，缺少student_fp32_best.pth"}
            )
            return 1
        
        cmd = [
            "python3", "scripts/quantize.py",
            "--exp-config", "expconfigs/quant.yaml",
            "--mode", "auto",
            "--model-weights", str(student_path)
        ]
    else:
        print(f"未知实验: {exp_name}")
        return 1
    
    # 发送开始通知
    notify_completion(
        exp_name,
        "running",
        {
            "start_time": datetime.now().isoformat(),
            "command": " ".join(cmd)
        }
    )
    
    # 运行实验
    try:
        result = subprocess.run(cmd, cwd=project_root, check=True)
        
        # 发送成功通知
        notify_completion(
            exp_name,
            "success",
            {
                "end_time": datetime.now().isoformat(),
                "exit_code": result.returncode
            }
        )
        
        return 0
    except subprocess.CalledProcessError as e:
        # 发送失败通知
        notify_completion(
            exp_name,
            "failed",
            {
                "end_time": datetime.now().isoformat(),
                "exit_code": e.returncode,
                "error": str(e)
            }
        )
        return e.returncode
    except Exception as e:
        # 发送失败通知
        notify_completion(
            exp_name,
            "failed",
            {
                "end_time": datetime.now().isoformat(),
                "error": str(e)
            }
        )
        return 1

def main():
    parser = argparse.ArgumentParser(description="带完整验证的实验运行脚本")
    parser.add_argument("--exp", choices=["K-only", "Q-only", "K-to-Q"], required=True,
                        help="实验名称")
    parser.add_argument("--skip-verification", action="store_true",
                        help="跳过验证（不推荐）")
    parser.add_argument("--project-root", type=str, default=None,
                        help="项目根目录")
    
    args = parser.parse_args()
    
    # 确定项目根目录
    if args.project_root:
        project_root = Path(args.project_root)
    else:
        project_root = Path(__file__).resolve().parent.parent
    
    # 实验前验证
    if not args.skip_verification:
        if not run_verification(args.exp, project_root):
            print("\n❌ 验证失败，实验已取消")
            return 1
        print("\n" + "="*80)
        input("验证通过，按Enter继续运行实验（或Ctrl+C取消）...")
    
    # 运行实验
    exit_code = run_experiment(args.exp, project_root)
    
    return exit_code

if __name__ == "__main__":
    sys.exit(main())

