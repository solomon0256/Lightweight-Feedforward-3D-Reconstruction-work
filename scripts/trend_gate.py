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
import torch

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 导入必要的模块
from scripts.baseline_eval import load_dust3r_model, setup_dust3r_paths, load_eval_pairs
from scripts.eval_depth_pose import run_evaluation
from scripts.utils.timer import BatchTimer, TimingResult
from scripts.utils.model_stats import get_model_stats


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
        method_type: str = "fp16",
        method: Optional[str] = None,
        variant: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        精度护栏检查（固定阈值，针对最终结果）
        
        Args:
            current_metrics: 当前指标（200对样本的结果）
            method_type: 方法类型 (fp16, int8_ptq, pruning, distillation)
            method: 轻量化方法 ('K'/'Q'/'P')，用于确定阈值来源
            variant: 变体名称，用于量化方法选择具体阈值
            
        Returns:
            (passed, details)
        """
        # 根据方法类型获取固定阈值（针对最终结果）
        thresholds = None
        
        # 优先使用 method 和 variant 确定阈值
        if method == 'K':
            # 蒸馏：使用 distillation 阈值
            if 'distillation' in self.guardrails['accuracy']:
                thresholds = self.guardrails['accuracy']['distillation']
        elif method == 'Q':
            # 量化：根据 variant 选择阈值
            if variant == 'fp16' and 'quantization' in self.guardrails['accuracy']:
                thresholds = self.guardrails['accuracy']['quantization'].get('fp16')
            elif variant == 'int8' and 'quantization' in self.guardrails['accuracy']:
                thresholds = self.guardrails['accuracy']['quantization'].get('int8_ptq')
            elif variant == 'int8_qat' and 'quantization' in self.guardrails['accuracy']:
                thresholds = self.guardrails['accuracy']['quantization'].get('int8_qat')
        elif method == 'P':
            # 剪枝：使用 pruning 阈值
            if 'pruning' in self.guardrails['accuracy']:
                thresholds = self.guardrails['accuracy']['pruning']
        
        # 如果未找到，尝试使用 method_type（向后兼容）
        if thresholds is None:
            if method_type in self.guardrails['accuracy']:
                thresholds = self.guardrails['accuracy'][method_type]
            else:
                # 默认使用 int8 阈值
                if 'quantization' in self.guardrails['accuracy']:
                    thresholds = self.guardrails['accuracy']['quantization'].get('int8_ptq')
                else:
                    thresholds = self.guardrails['accuracy'].get('int8_ptq', {
                        'absrel_max_increase_pct': 10.0,
                        'delta1_max_decrease_pct': 3.0,
                        'visloc_acc_max_decrease_pct': 5.0
                    })
        
        if thresholds is None:
            raise ValueError(f"无法找到方法 {method} (variant: {variant}, method_type: {method_type}) 的阈值配置")
        
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
        method_type: str = "fp16",
        method: Optional[str] = None,
        variant: Optional[str] = None
    ) -> Tuple[bool, Dict]:
        """
        运行完整的 Trend Gate
        
        Args:
            current_metrics: 当前质量指标（200对样本的结果）
            current_perf: 当前性能指标
            method_type: 方法类型（向后兼容）
            method: 轻量化方法 ('K'/'Q'/'P')
            variant: 变体名称
            
        Returns:
            (all_passed, full_results)
        """
        print("\n" + "="*60)
        print("📊 TREND GATE - 趋势预警")
        print("="*60)
        
        all_passed = True
        
        # 1. 精度护栏
        print(f"\n[1/2] 精度护栏检查 (method: {method_type})...")
        # 如果未提供 method 和 variant，从 method_type 推断
        inferred_method = method
        inferred_variant = variant
        if inferred_method is None or inferred_variant is None:
            if method_type == 'distillation':
                inferred_method = 'K'
                inferred_variant = 'student'
            elif method_type in ['fp16', 'int8_ptq', 'int8_qat']:
                inferred_method = 'Q'
                inferred_variant = method_type.replace('int8_ptq', 'int8').replace('int8_qat', 'int8_qat')
            elif method_type == 'pruning':
                inferred_method = 'P'
        
        acc_passed, acc_info = self.check_accuracy_guardrails(
            current_metrics, method_type, method=inferred_method, variant=inferred_variant
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


def run_trend_evaluation(model, num_pairs: int = 200, device: str = 'cuda') -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    运行 Trend Gate 评测
    
    Args:
        model: DUSt3R 模型
        num_pairs: 评测样本对数
        device: 设备
    
    Returns:
        (metrics, perf)
        - metrics: Dict[str, float] 质量指标（absrel, delta1, rmse, acc_0.25m_2deg）
        - perf: Dict[str, float] 性能指标（t_pair_p50_ms, t_pair_mean_ms, t_pair_std_ms, vram_peak_gb）
    """
    # 1. 从 workload.yaml 读取数据路径
    workload_path = PROJECT_ROOT / "config" / "workload.yaml"
    if not workload_path.exists():
        print(f"[ERROR] Workload config not found: {workload_path}")
        return {}, {}
    
    with open(workload_path, 'r', encoding='utf-8') as f:
        workload = yaml.safe_load(f)
    
    pairs_list_path = workload.get('data', {}).get('eval_pairs_list', '')
    if not pairs_list_path or not Path(pairs_list_path).exists():
        print(f"[ERROR] Pairs list not found: {pairs_list_path}")
        return {}, {}
    
    # 2. 加载 trend set（限制为 num_pairs）
    pairs = load_eval_pairs(pairs_list_path, limit=num_pairs)
    if not pairs:
        print("[ERROR] 无法加载 pairs")
        return {}, {}
    
    print(f"[INFO] 加载了 {len(pairs)} 个 pairs 用于 Trend Gate 评测")
    
    # 3. 运行评测（使用 run_evaluation()）
    # 注意：run_evaluation 需要 dataset_path，但我们只有 pairs 列表
    # 我们需要一个适配层，或者直接使用 evaluate_pair 循环
    from scripts.eval_depth_pose import evaluate_pair
    
    all_depth_metrics = []
    all_pose_metrics = []
    
    print("[INFO] 开始运行评测...")
    successful_evaluations = 0
    failed_evaluations = 0
    
    for i, (img1_path, img2_path) in enumerate(pairs):
        try:
            # 注意：Trend Gate 可能没有 GT，使用 None
            depth_m, pose_m = evaluate_pair(
                model, img1_path, img2_path,
                gt_depth1=None, gt_pose1=None, gt_pose2=None,
                device=device
            )
            all_depth_metrics.append(depth_m)
            all_pose_metrics.append(pose_m)
            successful_evaluations += 1
            
            if (i + 1) % 50 == 0:
                print(f"  已处理 {i + 1}/{len(pairs)} 个 pairs")
        except Exception as e:
            print(f"评测失败 [{i}]: {e}")
            failed_evaluations += 1
            # 不添加失败的结果，保持列表只包含有效结果
    
    # 检查是否有足够的成功结果
    if successful_evaluations == 0:
        print("[ERROR] 所有评测都失败了")
        return {}, {}
    
    if successful_evaluations < len(pairs) * 0.5:  # 如果失败率超过50%
        print(f"[WARN] 失败率过高 ({failed_evaluations}/{len(pairs)})，但继续处理")
    
    print(f"[INFO] 评测完成: 成功 {successful_evaluations} 个，失败 {failed_evaluations} 个")
    
    # 汇总质量指标
    def agg(metrics, key):
        vals = [m.get(key) for m in metrics if m.get(key) is not None and not np.isnan(m.get(key, np.nan))]
        return np.mean(vals) if vals else np.nan
    
    metrics = {
        'absrel': agg(all_depth_metrics, 'abs_rel'),
        'delta1': agg(all_depth_metrics, 'delta1'),
        'rmse': agg(all_depth_metrics, 'rmse'),
        'acc_0.25m_2deg': np.nan  # 需要从 VisLoc 结果获取，这里先设为 nan
    }
    
    # 4. 测量性能（使用 BatchTimer 和 get_model_stats()）
    print("[INFO] 测量性能指标...")
    
    # 准备输入数据（使用第一个 pair）
    if pairs:
        from dust3r.utils.image import load_images
        from dust3r.image_pairs import make_pairs
        from dust3r.inference import inference
        
        img1_path, img2_path = pairs[0]
        images = load_images([str(img1_path), str(img2_path)], size=512)
        test_pairs = make_pairs(images, scene_graph='complete', prefilter=None, symmetrize=True)
        
        # 测量延迟
        timer = BatchTimer(warmup=3, sync_cuda=(device == 'cuda'))
        
        with torch.no_grad():
            for _ in range(10):  # 测量 10 次
                timer.start()
                _ = inference(test_pairs, model, device, batch_size=1, verbose=False)
                timer.stop()
        
        timing = timer.get_stats()
        
        # 测量显存（如果使用 CUDA）
        vram_peak_gb = 0.0
        if device == 'cuda' and torch.cuda.is_available():
            input_shape = (1, 3, 512, 384)
            model_stats = get_model_stats(
                model,
                input_shape=input_shape,
                device=device,
                measure_vram_flag=True
            )
            vram_peak_gb = model_stats.vram_peak_gb if hasattr(model_stats, 'vram_peak_gb') else 0.0
        
        perf = {
            't_pair_p50_ms': timing.p50_ms if hasattr(timing, 'p50_ms') else timing.mean_ms,
            't_pair_mean_ms': timing.mean_ms,
            't_pair_std_ms': timing.std_ms,
            'vram_peak_gb': vram_peak_gb
        }
    else:
        perf = {
            't_pair_p50_ms': np.nan,
            't_pair_mean_ms': np.nan,
            't_pair_std_ms': np.nan,
            'vram_peak_gb': np.nan
        }
    
    print(f"[INFO] 评测完成")
    print(f"  质量指标: absrel={metrics['absrel']:.4f}, delta1={metrics['delta1']:.4f}")
    print(f"  性能指标: t_pair_p50={perf['t_pair_p50_ms']:.1f}ms, vram={perf['vram_peak_gb']:.2f}GB")
    
    return metrics, perf


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
    
    parser.add_argument("--device", type=str, default="cuda",
                       help="设备 (cuda/cpu)")
    parser.add_argument("--checkpoint", type=str, default=None,
                       help="模型 checkpoint 路径（用于量化/蒸馏/剪枝模型）")
    
    args = parser.parse_args()
    
    # 加载 Trend Gate
    gate = TrendGate()
    
    # 加载模型和运行评测
    print("\n" + "="*60)
    print(f"📊 Trend Gate 验证 - {args.method}/{args.variant}")
    print("="*60)
    
    from scripts.utils.model_loader import load_model
    
    try:
        model = load_model(
            args.method,
            args.variant,
            device=args.device,
            checkpoint_path=args.checkpoint
        )
        
        metrics, perf = run_trend_evaluation(model, args.num_pairs, device=args.device)
        
        # 更严格的检查：不仅检查字典是否为空，还检查是否有有效值
        if not metrics or not perf:
            print("[ERROR] 评测失败，无法获取结果")
            return
        
        # 检查metrics中是否有有效值（不是全部NaN）
        valid_metric_count = sum(1 for v in metrics.values() if not (isinstance(v, float) and np.isnan(v)))
        if valid_metric_count == 0:
            print("[ERROR] 所有指标都是NaN，评测失败")
            return
        
        # 检查perf中是否有有效值
        valid_perf_count = sum(1 for v in perf.values() if not (isinstance(v, float) and np.isnan(v)))
        if valid_perf_count == 0:
            print("[ERROR] 所有性能指标都是NaN，评测失败")
            return
        
        # 从 method 和 variant 推断 method_type（如果未提供）
        if args.method_type == "fp16" and args.method:
            if args.method == 'K':
                method_type = 'distillation'
            elif args.method == 'Q':
                if args.variant == 'fp16':
                    method_type = 'fp16'
                elif args.variant == 'int8':
                    method_type = 'int8_ptq'
            elif args.method == 'P':
                method_type = 'pruning'
            else:
                method_type = args.method_type
        else:
            method_type = args.method_type
        
        passed, results = gate.run_gate(
            metrics, 
            perf, 
            method_type,
            method=args.method,
            variant=args.variant
        )
        
        # 保存结果
        if args.output:
            gate.save_results(args.output)
        else:
            # 默认保存路径
            output_path = f"runs/trend_gate_{args.method}_{args.variant}.json"
            gate.save_results(output_path)
        
        if not passed:
            sys.exit(1)  # 失败时退出码为 1
        
    except Exception as e:
        print(f"[ERROR] 运行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
