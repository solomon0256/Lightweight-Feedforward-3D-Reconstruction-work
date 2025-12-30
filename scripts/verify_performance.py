#!/usr/bin/env python3
"""
轻量化性能验证脚本

用途：
- 在工作电脑上预计轻量化后的性能是否符合预期
- 测量参数量、推理速度、精度（基于1个样本快速测）

运行示例：
    python scripts/verify_performance.py
    python scripts/verify_performance.py --method distill
    python scripts/verify_performance.py --config config/verify_targets.yaml
"""

import argparse
import sys
import yaml
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

import torch
import torch.nn as nn
import numpy as np

# 添加项目根目录到路径
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.baseline_eval import load_dust3r_model, setup_dust3r_paths
from scripts.models import create_student_model
from scripts.utils.model_stats import count_parameters
from scripts.utils.timer import Timer


# ============ 工具函数 ============

def load_baseline_metrics() -> Dict[str, float]:
    """加载baseline性能指标"""
    baseline_path = PROJECT_ROOT / 'logs' / 'baseline_complete.json'
    if baseline_path.exists():
        with open(baseline_path, 'r', encoding='utf-8') as f:
            baseline_data = json.load(f)
            return {
                'params_M': baseline_data.get('model_stats', {}).get('params_M', 571.17),
                'latency_ms': baseline_data.get('performance', {}).get('t_pair_p50_ms', 353.07),
                'vram_GB': baseline_data.get('performance', {}).get('vram_peak_gb', 2.76),
                'visloc_cm': baseline_data.get('pose_visloc', {}).get('median_t_cm', 1.85),
            }
    else:
        # 默认值
        return {
            'params_M': 571.17,
            'latency_ms': 353.07,
            'vram_GB': 2.76,
            'visloc_cm': 1.85,
        }


def measure_inference_time(model: nn.Module, img1: torch.Tensor, img2: torch.Tensor, 
                          device: str = 'cuda', num_runs: int = 10, is_dust3r: bool = False) -> float:
    """测量推理时间（毫秒）"""
    model.eval()
    model = model.to(device)
    img1 = img1.to(device)
    img2 = img2.to(device)
    
    # 预热
    with torch.no_grad():
        for _ in range(3):
            if is_dust3r:
                view1 = {'img': img1, 'instance': ['0'], 'idx': [0]}
                view2 = {'img': img2, 'instance': ['1'], 'idx': [1]}
                _ = model(view1, view2)
            else:
                _ = model(img1, img2)
    
    # 测量
    timer = Timer(warmup=0, sync_cuda=True)
    with torch.no_grad():
        for _ in range(num_runs):
            timer.start()
            if is_dust3r:
                view1 = {'img': img1, 'instance': ['0'], 'idx': [0]}
                view2 = {'img': img2, 'instance': ['1'], 'idx': [1]}
                _ = model(view1, view2)
            else:
                _ = model(img1, img2)
            timer.stop()
    
    result = timer.get_result()
    return result.p50_ms


def quick_accuracy_test(model: nn.Module, img1: torch.Tensor, img2: torch.Tensor,
                       device: str = 'cuda', is_dust3r: bool = False) -> Dict[str, float]:
    """
    快速精度测试（1个样本，仅供参考）
    
    注意：1个样本的精度没有统计意义，只能验证模型能跑
    """
    model.eval()
    model = model.to(device)
    img1 = img1.to(device)
    img2 = img2.to(device)
    
    try:
        with torch.no_grad():
            if is_dust3r:
                # 修复：添加必需的 'instance' 和 'idx' 键，与 measure_inference_time 保持一致
                view1 = {'img': img1, 'instance': ['0'], 'idx': [0]}
                view2 = {'img': img2, 'instance': ['1'], 'idx': [1]}
                output1, output2 = model(view1, view2)
                output = output1  # 取第一个view的输出
            else:
                output = model(img1, img2)
        
        # 简单检查输出是否合理（参考verify_lightweight_feasibility.py的实现）
        if isinstance(output, dict):
            output_tensor = output.get('pts3d')
            if output_tensor is None:
                # 尝试其他键
                output_tensor = output.get('depth') or list(output.values())[0]
        else:
            output_tensor = output
        
        # 检查数值范围（直接使用，不转换，与verify_lightweight_feasibility.py一致）
        if output_tensor.numel() > 0:
            has_nan = torch.isnan(output_tensor).any().item()
            has_inf = torch.isinf(output_tensor).any().item()
            
            if has_nan or has_inf:
                return {
                    'valid': False,
                    'message': '输出包含NaN/Inf'
                }
            
            # 简单统计
            mean_val = output_tensor.mean().item()
            std_val = output_tensor.std().item()
            
            return {
                'valid': True,
                'mean': mean_val,
                'std': std_val,
                'message': '输出数值合理'
            }
        else:
            return {
                'valid': False,
                'message': '输出tensor为空'
            }
    except Exception as e:
        return {
            'valid': False,
            'message': f'推理失败: {str(e)}'
        }


# ============ 验证函数 ============

def verify_distillation_performance(device: str = 'cuda', 
                                   targets: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    验证蒸馏后的性能
    
    Args:
        device: 设备
        targets: 目标值配置
    
    Returns:
        性能报告
    """
    print("\n[蒸馏] 性能验证")
    print("=" * 60)
    
    try:
        # 1. 创建Student模型（不训练）
        print("  创建Student模型...")
        student = create_student_model(arch='dust3r_student_s', device=device)
        
        # 2. 测量参数量
        total_params, trainable_params = count_parameters(student)
        params_M = total_params / 1e6
        
        print(f"  参数量: {params_M:.2f}M")
        
        # 3. 创建虚拟输入
        img1 = torch.randn(1, 3, 512, 384).to(device)
        img2 = torch.randn(1, 3, 512, 384).to(device)
        
        # 4. 测量推理速度（Student模型不是DUSt3R格式）
        print("  测量推理速度...")
        latency_ms = measure_inference_time(student, img1, img2, device=device, is_dust3r=False)
        print(f"  推理时间: {latency_ms:.2f}ms")
        
        # 5. 快速精度测试
        print("  快速精度测试（1个样本，仅供参考）...")
        accuracy_result = quick_accuracy_test(student, img1, img2, device=device, is_dust3r=False)
        print(f"  {accuracy_result['message']}")
        
        # 6. 加载baseline
        baseline = load_baseline_metrics()
        
        # 7. 计算压缩比
        compression_ratio = baseline['params_M'] / params_M if params_M > 0 else 0
        speedup = baseline['latency_ms'] / latency_ms if latency_ms > 0 else 0
        
        # 8. 对比目标值
        checks = {}
        if targets:
            if targets.get('params_M') is not None:
                target_params = targets['params_M']
                passed = params_M <= target_params
                checks['params_M'] = {
                    'baseline': baseline['params_M'],
                    'actual': params_M,
                    'target': target_params,
                    'passed': passed
                }
            
            if targets.get('latency_ms') is not None:
                target_latency = targets['latency_ms']
                passed = latency_ms <= target_latency
                checks['latency_ms'] = {
                    'baseline': baseline['latency_ms'],
                    'actual': latency_ms,
                    'target': target_latency,
                    'passed': passed
                }
            
            if targets.get('speedup') is not None:
                target_speedup = targets['speedup']
                passed = speedup >= target_speedup
                checks['speedup'] = {
                    'baseline': 1.0,
                    'actual': speedup,
                    'target': target_speedup,
                    'passed': passed
                }
        
        return {
            'method': 'distillation',
            'params_M': params_M,
            'latency_ms': latency_ms,
            'compression_ratio': compression_ratio,
            'speedup': speedup,
            'accuracy': accuracy_result,
            'checks': checks,
            'baseline': baseline
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'method': 'distillation',
            'error': str(e)
        }


def verify_quantization_performance(device: str = 'cuda',
                                   targets: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    验证量化后的性能
    
    Args:
        device: 设备
        targets: 目标值配置
    
    Returns:
        性能报告
    """
    print("\n[量化] 性能验证")
    print("=" * 60)
    
    try:
        # 1. 设置路径
        setup_dust3r_paths()
        
        # 2. 加载baseline模型
        print("  加载baseline模型...")
        baseline_model = load_dust3r_model(device=device)
        
        # 3. 应用INT8动态量化（实际量化方法，DUSt3R不支持FP16）
        print("  应用动态量化（INT8）...")
        # 量化模型只能在CPU上运行（PyTorch限制）
        original_device = next(baseline_model.parameters()).device
        model_cpu = baseline_model.cpu()
        # 只量化Linear层，避免Conv层的问题
        quantized_model = torch.quantization.quantize_dynamic(
            model_cpu,
            {torch.nn.Linear},
            dtype=torch.qint8
        )
        # 量化后的模型必须保持在CPU上
        
        # 4. 参数量（不变）
        total_params, _ = count_parameters(quantized_model)
        params_M = total_params / 1e6
        print(f"  参数量: {params_M:.2f}M (与baseline相同)")
        
        # 5. 创建虚拟输入（CPU上）
        img1 = torch.randn(1, 3, 512, 384)
        img2 = torch.randn(1, 3, 512, 384)
        
        # 6. 测量推理速度（量化模型在CPU上，需要view格式）
        print("  测量推理速度...")
        latency_ms = measure_inference_time(quantized_model, img1, img2, device='cpu', is_dust3r=True)
        print(f"  推理时间: {latency_ms:.2f}ms")
        
        # 7. 快速精度测试
        print("  快速精度测试（1个样本，仅供参考）...")
        accuracy_result = quick_accuracy_test(quantized_model, img1, img2, device='cpu', is_dust3r=True)
        print(f"  {accuracy_result['message']}")
        
        # 8. 加载baseline
        baseline = load_baseline_metrics()
        
        # 9. 计算加速比
        speedup = baseline['latency_ms'] / latency_ms if latency_ms > 0 else 0
        
        # 10. 对比目标值
        checks = {}
        if targets:
            if targets.get('latency_ms') is not None:
                target_latency = targets['latency_ms']
                passed = latency_ms <= target_latency
                checks['latency_ms'] = {
                    'baseline': baseline['latency_ms'],
                    'actual': latency_ms,
                    'target': target_latency,
                    'passed': passed
                }
            
            if targets.get('speedup') is not None:
                target_speedup = targets['speedup']
                passed = speedup >= target_speedup
                checks['speedup'] = {
                    'baseline': 1.0,
                    'actual': speedup,
                    'target': target_speedup,
                    'passed': passed
                }
        
        return {
            'method': 'quantization',
            'params_M': params_M,
            'latency_ms': latency_ms,
            'speedup': speedup,
            'accuracy': accuracy_result,
            'checks': checks,
            'baseline': baseline
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'method': 'quantization',
            'error': str(e)
        }


def verify_pruning_performance(device: str = 'cuda', target_sparsity: float = 0.4,
                              targets: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    验证剪枝后的性能
    
    Args:
        device: 设备
        target_sparsity: 目标稀疏度
        targets: 目标值配置
    
    Returns:
        性能报告
    """
    print("\n[剪枝] 性能验证")
    print("=" * 60)
    
    try:
        # 1. 设置路径
        setup_dust3r_paths()
        
        # 2. 加载baseline模型
        print("  加载baseline模型...")
        model = load_dust3r_model(device=device)
        
        # 3. 应用剪枝
        print(f"  应用剪枝（目标稀疏度: {target_sparsity*100:.0f}%）...")
        import torch.nn.utils.prune as prune
        
        # 找到第一个Linear层进行剪枝
        pruned_module = None
        for name, module in model.named_modules():
            if isinstance(module, nn.Linear) and module.weight.numel() > 10000:
                pruned_module = (name, module)
                break
        
        if pruned_module is None:
            return {
                'method': 'pruning',
                'error': '未找到合适的剪枝层'
            }
        
        name, module = pruned_module
        prune.l1_unstructured(module, name='weight', amount=target_sparsity)
        
        # 4. 计算稀疏度
        total_params = module.weight.numel()
        zero_params = (module.weight == 0).sum().item()
        actual_sparsity = zero_params / total_params
        
        print(f"  实际稀疏度: {actual_sparsity*100:.1f}%")
        
        # 5. 参数量（不变，但稀疏度增加）
        total_params_model, _ = count_parameters(model)
        params_M = total_params_model / 1e6
        print(f"  参数量: {params_M:.2f}M (与baseline相同，但稀疏度增加)")
        
        # 6. 创建虚拟输入
        img1 = torch.randn(1, 3, 512, 384).to(device)
        img2 = torch.randn(1, 3, 512, 384).to(device)
        
        # 7. 测量推理速度（DUSt3R模型需要view格式）
        print("  测量推理速度...")
        latency_ms = measure_inference_time(model, img1, img2, device=device, is_dust3r=True)
        print(f"  推理时间: {latency_ms:.2f}ms")
        
        # 8. 快速精度测试
        print("  快速精度测试（1个样本，仅供参考）...")
        accuracy_result = quick_accuracy_test(model, img1, img2, device=device, is_dust3r=True)
        print(f"  {accuracy_result['message']}")
        
        # 9. 加载baseline
        baseline = load_baseline_metrics()
        
        # 10. 计算加速比
        speedup = baseline['latency_ms'] / latency_ms if latency_ms > 0 else 0
        
        # 11. 对比目标值
        checks = {}
        if targets:
            if targets.get('sparsity') is not None:
                target_sparsity_val = targets['sparsity']
                passed = actual_sparsity >= target_sparsity_val * 0.9  # 允许10%误差
                checks['sparsity'] = {
                    'target': target_sparsity_val,
                    'actual': actual_sparsity,
                    'passed': passed
                }
            
            if targets.get('latency_ms') is not None:
                target_latency = targets['latency_ms']
                passed = latency_ms <= target_latency
                checks['latency_ms'] = {
                    'baseline': baseline['latency_ms'],
                    'actual': latency_ms,
                    'target': target_latency,
                    'passed': passed
                }
        
        # 清理剪枝（恢复原状）
        prune.remove(module, 'weight')
        
        return {
            'method': 'pruning',
            'params_M': params_M,
            'sparsity': actual_sparsity,
            'latency_ms': latency_ms,
            'speedup': speedup,
            'accuracy': accuracy_result,
            'checks': checks,
            'baseline': baseline
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'method': 'pruning',
            'error': str(e)
        }


# ============ 主函数 ============

def main():
    parser = argparse.ArgumentParser(description='预计轻量化后的性能是否符合预期')
    parser.add_argument('--method', type=str, default='all',
                       choices=['all', 'distill', 'quantize', 'prune'],
                       help='验证方法: all, distill, quantize, prune')
    parser.add_argument('--config', type=str, default='config/verify_targets.yaml',
                       help='目标值配置文件路径')
    parser.add_argument('--device', type=str, default='cuda',
                       choices=['cuda', 'cpu'],
                       help='设备: cuda, cpu')
    parser.add_argument('--target-sparsity', type=float, default=0.4,
                       help='剪枝目标稀疏度 (默认: 0.4)')
    parser.add_argument('--output', type=str, default=None,
                       help='输出JSON报告路径')
    
    args = parser.parse_args()
    
    # 检查设备
    if args.device == 'cuda' and not torch.cuda.is_available():
        print("[WARN] CUDA不可用，使用CPU")
        args.device = 'cpu'
    
    # 加载目标值配置
    config_path = Path(args.config)
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            targets = config.get('targets', {})
    else:
        print(f"[WARN] 配置文件不存在: {config_path}，使用默认配置（不检查目标值）")
        targets = {}
    
    print("=" * 60)
    print("轻量化性能验证报告")
    print("=" * 60)
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'method': args.method,
        'device': args.device,
        'targets': targets,
        'performance': {}
    }
    
    all_passed = True
    
    # 验证蒸馏
    if args.method in ['all', 'distill']:
        distill_result = verify_distillation_performance(device=args.device, targets=targets)
        results['performance']['distillation'] = distill_result
        if 'error' in distill_result:
            all_passed = False
        elif distill_result.get('checks'):
            if not all(c.get('passed', True) for c in distill_result['checks'].values()):
                all_passed = False
    
    # 验证量化
    if args.method in ['all', 'quantize']:
        quant_result = verify_quantization_performance(device=args.device, targets=targets)
        results['performance']['quantization'] = quant_result
        if 'error' in quant_result:
            all_passed = False
        elif quant_result.get('checks'):
            if not all(c.get('passed', True) for c in quant_result['checks'].values()):
                all_passed = False
    
    # 验证剪枝
    if args.method in ['all', 'prune']:
        prune_result = verify_pruning_performance(device=args.device, 
                                                 target_sparsity=args.target_sparsity,
                                                 targets=targets)
        results['performance']['pruning'] = prune_result
        if 'error' in prune_result:
            all_passed = False
        elif prune_result.get('checks'):
            if not all(c.get('passed', True) for c in prune_result['checks'].values()):
                all_passed = False
    
    # 打印报告表格
    print("\n" + "=" * 60)
    print("性能对比表")
    print("=" * 60)
    print(f"{'指标':<20} {'Baseline':<15} {'实际值':<15} {'目标':<15} {'结果':<10}")
    print("-" * 60)
    
    for method_name, method_result in results['performance'].items():
        if 'error' in method_result:
            print(f"[{method_name}] 错误: {method_result['error']}")
            continue
        
        baseline = method_result.get('baseline', {})
        
        # 参数量
        if 'params_M' in method_result:
            params = method_result['params_M']
            baseline_params = baseline.get('params_M', 0)
            target = targets.get('params_M')
            target_str = f"<{target}" if target else "null"
            result_str = "--"
            if target:
                result_str = "[PASS]" if params <= target else "[FAIL]"
            print(f"{'params_M':<20} {baseline_params:<15.2f} {params:<15.2f} {target_str:<15} {result_str:<10}")
        
        # 推理时间
        if 'latency_ms' in method_result:
            latency = method_result['latency_ms']
            baseline_latency = baseline.get('latency_ms', 0)
            target = targets.get('latency_ms')
            target_str = f"<{target}" if target else "null"
            result_str = "--"
            if target:
                result_str = "✅ PASS" if latency <= target else "❌ FAIL"
            print(f"{'latency_ms':<20} {baseline_latency:<15.2f} {latency:<15.2f} {target_str:<15} {result_str:<10}")
        
        # 加速比
        if 'speedup' in method_result:
            speedup = method_result['speedup']
            target = targets.get('speedup')
            target_str = f">{target}x" if target else "null"
            result_str = "--"
            if target:
                result_str = "✅ PASS" if speedup >= target else "❌ FAIL"
            print(f"{'speedup':<20} {'1.0x':<15} {f'{speedup:.2f}x':<15} {target_str:<15} {result_str:<10}")
        
        # 精度说明
        print(f"{'(精度说明: 基于1个样本快速测，仅供参考)':<60}")
    
    # 总结
    print("\n" + "=" * 60)
    results['passed'] = all_passed
    if all_passed:
        check_count = sum(len(r.get('checks', {})) for r in results['performance'].values())
        print(f"[SUCCESS] 总结: 所有检查项通过")
    else:
        print(f"[FAIL] 总结: 部分检查项失败")
    print("=" * 60)
    
    # 保存结果
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n结果已保存到: {output_path}")
    else:
        # 默认保存路径
        logs_dir = PROJECT_ROOT / 'logs'
        logs_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = logs_dir / f'verify_performance_{timestamp}.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n结果已保存到: {output_path}")
    
    # 退出码
    sys.exit(0 if all_passed else 1)


if __name__ == '__main__':
    main()
