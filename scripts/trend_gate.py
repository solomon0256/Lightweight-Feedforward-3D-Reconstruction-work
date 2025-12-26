#!/usr/bin/env python3
"""
Trend Gate 验证脚本
==================
验证 PQK 性能趋势：早期预警阈值检查

Usage:
    # 运行趋势验证
    python scripts/trend_gate.py --method Q --variant fp16 --num-pairs 200
    
    # 与 baseline 对比
    python scripts/trend_gate.py --method Q --variant fp16 --compare-baseline
"""

import os
import sys
import json
import yaml
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
import numpy as np

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TrendGate:
    """Trend Gate 验证器 - 早期预警"""
    
    def __init__(self, contract_path: str = "config/eval_contract.yaml"):
        """加载评测合同"""
        with open(contract_path, 'r', encoding='utf-8') as f:
            self.contract = yaml.safe_load(f)
        
        self.trend_config = self.contract['validation_sets']['trend']
        self.guardrails = self.contract['guardrails']
        self.baseline_ref = self.contract['baseline_reference']
        
        # 结果存储
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "passed": False,
            "checks": {},
            "comparison": {}
        }
    
    def load_baseline(self) -> Dict[str, Any]:
        """加载 baseline 结果"""
        baseline_path = self.baseline_ref['source']
        with open(baseline_path, 'r') as f:
            return json.load(f)
    
    def check_accuracy_guardrails(
        self,
        current_metrics: Dict[str, float],
        method_type: str = "fp16"
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        精度护栏检查
        
        Args:
            current_metrics: 当前指标
            method_type: 方法类型 (fp16, int8_ptq, pruning, distillation)
            
        Returns:
            (passed, details)
        """
        # 获取对应方法的阈值
        if method_type in self.guardrails['accuracy']:
            thresholds = self.guardrails['accuracy'][method_type]
        else:
            # 默认使用 int8 阈值
            thresholds = self.guardrails['accuracy']['int8_ptq']
        
        baseline = self.baseline_ref
        checks = {}
        all_passed = True
        
        # 检查 absrel
        if 'absrel' in current_metrics:
            baseline_absrel = baseline['depth']['absrel']
            current_absrel = current_metrics['absrel']
            increase_pct = (current_absrel - baseline_absrel) / baseline_absrel * 100
            
            max_increase = thresholds.get('absrel_max_increase_pct', 10.0)
            passed = increase_pct <= max_increase
            
            checks['absrel'] = {
                "baseline": baseline_absrel,
                "current": current_absrel,
                "change_pct": increase_pct,
                "threshold_pct": max_increase,
                "passed": passed
            }
            
            if not passed:
                all_passed = False
        
        # 检查 delta1
        if 'delta1' in current_metrics:
            baseline_delta1 = baseline['depth']['delta1']
            current_delta1 = current_metrics['delta1']
            decrease_pct = (baseline_delta1 - current_delta1) / baseline_delta1 * 100
            
            max_decrease = thresholds.get('delta1_max_decrease_pct', 3.0)
            passed = decrease_pct <= max_decrease
            
            checks['delta1'] = {
                "baseline": baseline_delta1,
                "current": current_delta1,
                "change_pct": -decrease_pct,  # 负数表示下降
                "threshold_pct": max_decrease,
                "passed": passed
            }
            
            if not passed:
                all_passed = False
        
        # 检查 visloc acc
        if 'acc_0.25m_2deg' in current_metrics:
            baseline_acc = baseline['pose_visloc']['acc_0.25m_2deg']
            current_acc = current_metrics['acc_0.25m_2deg']
            decrease_pct = (baseline_acc - current_acc) / baseline_acc * 100
            
            max_decrease = thresholds.get('visloc_acc_max_decrease_pct', 5.0)
            passed = decrease_pct <= max_decrease
            
            checks['visloc_acc'] = {
                "baseline": baseline_acc,
                "current": current_acc,
                "change_pct": -decrease_pct,
                "threshold_pct": max_decrease,
                "passed": passed
            }
            
            if not passed:
                all_passed = False
        
        result = {
            "method_type": method_type,
            "checks": checks,
            "passed": all_passed
        }
        
        self.results['checks']['accuracy'] = result
        return all_passed, result
    
    def check_performance_guardrails(
        self,
        current_perf: Dict[str, float],
        expected_improvement: bool = True
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        性能护栏检查
        
        Args:
            current_perf: 当前性能指标
            expected_improvement: 是否期望性能提升（量化/剪枝应该更快）
            
        Returns:
            (passed, details)
        """
        baseline = self.baseline_ref
        perf_guardrails = self.guardrails['performance']
        
        checks = {}
        all_passed = True
        
        # 检查延迟
        if 't_pair_p50_ms' in current_perf:
            baseline_latency = baseline['performance']['t_pair_p50_ms']
            current_latency = current_perf['t_pair_p50_ms']
            
            speedup = baseline_latency / current_latency if current_latency > 0 else 0
            improved = current_latency < baseline_latency
            
            if perf_guardrails['latency_must_decrease'] and expected_improvement:
                passed = improved
            else:
                passed = True
            
            checks['latency'] = {
                "baseline_ms": baseline_latency,
                "current_ms": current_latency,
                "speedup": speedup,
                "improved": improved,
                "passed": passed
            }
            
            if not passed:
                all_passed = False
        
        # 检查延迟方差
        if 't_pair_std_ms' in current_perf and 't_pair_mean_ms' in current_perf:
            current_cv = current_perf['t_pair_std_ms'] / current_perf['t_pair_mean_ms']
            # 假设 baseline CV 约 3.4% (12/355)
            baseline_cv = 0.034
            
            max_ratio = perf_guardrails['latency_variance_max_ratio']
            passed = current_cv <= baseline_cv * max_ratio
            
            checks['latency_variance'] = {
                "current_cv": current_cv,
                "baseline_cv": baseline_cv,
                "max_ratio": max_ratio,
                "passed": passed
            }
            
            if not passed:
                all_passed = False
        
        # 检查显存
        if 'vram_peak_gb' in current_perf:
            baseline_vram = baseline['performance']['vram_peak_gb']
            current_vram = current_perf['vram_peak_gb']
            
            reduction = (baseline_vram - current_vram) / baseline_vram * 100
            improved = current_vram < baseline_vram
            
            checks['vram'] = {
                "baseline_gb": baseline_vram,
                "current_gb": current_vram,
                "reduction_pct": reduction,
                "improved": improved,
                "passed": True  # VRAM 不是硬性要求
            }
        
        result = {
            "checks": checks,
            "passed": all_passed
        }
        
        self.results['checks']['performance'] = result
        return all_passed, result
    
    def generate_comparison_report(
        self,
        current_metrics: Dict[str, float],
        current_perf: Dict[str, float]
    ) -> Dict[str, Any]:
        """生成与 baseline 的对比报告"""
        baseline = self.baseline_ref
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "depth": {},
            "pose": {},
            "performance": {}
        }
        
        # 深度对比
        for metric in ['absrel', 'delta1', 'rmse']:
            if metric in current_metrics:
                b_val = baseline['depth'].get(metric, 0)
                c_val = current_metrics[metric]
                change = (c_val - b_val) / b_val * 100 if b_val != 0 else 0
                
                report['depth'][metric] = {
                    "baseline": b_val,
                    "current": c_val,
                    "change_pct": round(change, 2)
                }
        
        # 性能对比
        for metric in ['t_pair_p50_ms', 'vram_peak_gb']:
            if metric in current_perf:
                b_val = baseline['performance'].get(metric, 0)
                c_val = current_perf[metric]
                change = (c_val - b_val) / b_val * 100 if b_val != 0 else 0
                
                report['performance'][metric] = {
                    "baseline": b_val,
                    "current": c_val,
                    "change_pct": round(change, 2)
                }
        
        self.results['comparison'] = report
        return report
    
    def run_gate(
        self,
        current_metrics: Dict[str, float],
        current_perf: Dict[str, float],
        method_type: str = "fp16"
    ) -> Tuple[bool, Dict]:
        """
        运行完整的 Trend Gate
        
        Args:
            current_metrics: 当前质量指标
            current_perf: 当前性能指标
            method_type: 方法类型
            
        Returns:
            (all_passed, full_results)
        """
        print("\n" + "="*60)
        print("📊 TREND GATE - 趋势预警")
        print("="*60)
        
        all_passed = True
        
        # 1. 精度护栏
        print(f"\n[1/2] 精度护栏检查 (method: {method_type})...")
        acc_passed, acc_info = self.check_accuracy_guardrails(
            current_metrics, method_type
        )
        
        for metric, info in acc_info['checks'].items():
            status = "✅" if info['passed'] else "❌"
            print(f"  {status} {metric}: {info['baseline']:.4f} → {info['current']:.4f} "
                  f"({info['change_pct']:+.2f}%, threshold: {info['threshold_pct']}%)")
        
        if not acc_passed:
            all_passed = False
        
        # 2. 性能护栏
        print("\n[2/2] 性能护栏检查...")
        perf_passed, perf_info = self.check_performance_guardrails(current_perf)
        
        for metric, info in perf_info['checks'].items():
            status = "✅" if info['passed'] else "❌"
            if metric == 'latency':
                print(f"  {status} {metric}: {info['baseline_ms']:.0f}ms → {info['current_ms']:.0f}ms "
                      f"(speedup: {info['speedup']:.2f}x)")
            elif metric == 'vram':
                print(f"  {status} {metric}: {info['baseline_gb']:.2f}GB → {info['current_gb']:.2f}GB "
                      f"({info['reduction_pct']:+.1f}%)")
            else:
                print(f"  {status} {metric}: passed={info['passed']}")
        
        if not perf_passed:
            all_passed = False
        
        # 3. 生成对比报告
        print("\n[对比报告]")
        report = self.generate_comparison_report(current_metrics, current_perf)
        
        print("  深度指标:")
        for metric, info in report['depth'].items():
            arrow = "↑" if info['change_pct'] > 0 else "↓"
            print(f"    {metric}: {info['baseline']:.4f} → {info['current']:.4f} "
                  f"({arrow}{abs(info['change_pct']):.2f}%)")
        
        print("  性能指标:")
        for metric, info in report['performance'].items():
            arrow = "↑" if info['change_pct'] > 0 else "↓"
            print(f"    {metric}: {info['baseline']:.2f} → {info['current']:.2f} "
                  f"({arrow}{abs(info['change_pct']):.2f}%)")
        
        # 总结
        print("\n" + "-"*60)
        self.results['passed'] = all_passed
        
        if all_passed:
            print("🎉 TREND GATE 通过！可以上服务器跑 Final Set")
            print("   建议：保存当前配置和结果，准备大规模评测")
        else:
            print("🚫 TREND GATE 失败！")
            print("   原因：精度或性能触发早停阈值")
            print("   建议：检查压缩配置，调整超参后重试")
            print("   ⚠️  不要上服务器！避免浪费资源")
        
        print("-"*60 + "\n")
        
        return all_passed, self.results
    
    def save_results(self, output_path: str):
        """保存验证结果"""
        with open(output_path, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"结果已保存到: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Trend Gate 验证")
    parser.add_argument("--method", type=str, default="Q",
                       help="PQK 方法 (P/Q/K)")
    parser.add_argument("--variant", type=str, default="fp16",
                       help="变体 (fp16, int8, pruned_50, etc.)")
    parser.add_argument("--method-type", type=str, default="fp16",
                       choices=["fp16", "int8_ptq", "pruning", "distillation"],
                       help="方法类型（用于选择阈值）")
    parser.add_argument("--num-pairs", type=int, default=200,
                       help="趋势集样本数")
    parser.add_argument("--output", type=str,
                       help="结果输出路径")
    
    args = parser.parse_args()
    
    # 加载 Trend Gate
    gate = TrendGate()
    
    # TODO: 实际运行评测并获取指标
    # model = load_model(args.method, args.variant)
    # metrics, perf = run_trend_evaluation(model, args.num_pairs)
    # passed, results = gate.run_gate(metrics, perf, args.method_type)
    
    # Demo: 使用模拟数据演示
    print("\n[Demo Mode] 使用模拟数据演示 Trend Gate")
    
    demo_metrics = {
        "absrel": 0.1180,  # 略高于 baseline 0.1168
        "delta1": 0.8970,  # 略低于 baseline 0.8995
        "rmse": 0.1460,
        "acc_0.25m_2deg": 58.5  # 略低于 baseline 59.8
    }
    
    demo_perf = {
        "t_pair_p50_ms": 180,  # FP16 更快
        "t_pair_mean_ms": 185,
        "t_pair_std_ms": 8,
        "vram_peak_gb": 1.8,   # FP16 更省显存
    }
    
    passed, results = gate.run_gate(demo_metrics, demo_perf, args.method_type)
    
    # 保存结果
    if args.output:
        gate.save_results(args.output)


if __name__ == "__main__":
    main()
