#!/usr/bin/env python3
"""
Smoke Gate 验证脚本
==================
快速验证 PQK 脚本的正确性：Schema 断言 + Golden 对比

Usage:
    # 生成 golden outputs（只需运行一次）
    python scripts/smoke_gate.py --create-golden
    
    # 验证 FP16 版本
    python scripts/smoke_gate.py --method Q --variant fp16
    
    # 验证 INT8 版本
    python scripts/smoke_gate.py --method Q --variant int8 --tolerance int8
"""

import os
import sys
import json
import yaml
import argparse
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class SmokeGate:
    """Smoke Gate 验证器"""
    
    def __init__(self, contract_path: str = "config/eval_contract.yaml"):
        """加载评测合同"""
        with open(contract_path, 'r', encoding='utf-8') as f:
            self.contract = yaml.safe_load(f)
        
        self.smoke_config = self.contract['validation_sets']['smoke']
        self.schema_rules = self.contract['schema_assertions']
        self.golden_config = self.contract['golden_outputs']
        self.guardrails = self.contract['guardrails']
        
        # Golden 文件路径
        self.golden_path = Path(self.golden_config['file'])
        
        # 结果存储
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "passed": False,
            "checks": {}
        }
    
    def load_golden(self) -> List[Dict]:
        """加载 Golden outputs"""
        if not self.golden_path.exists():
            raise FileNotFoundError(
                f"Golden file not found: {self.golden_path}\n"
                "Run with --create-golden first!"
            )
        
        golden_data = []
        with open(self.golden_path, 'r') as f:
            for line in f:
                if line.strip():
                    golden_data.append(json.loads(line))
        
        return golden_data
    
    def check_schema(self, outputs: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Schema 断言检查
        
        Args:
            outputs: 模型输出字典
            
        Returns:
            (passed, error_messages)
        """
        errors = []
        
        # 1. 检查必需字段
        required_keys = self.schema_rules['required_output_keys']
        for key in required_keys:
            if key not in outputs:
                errors.append(f"Missing required key: {key}")
        
        # 2. 检查数值类型
        allowed_dtypes = self.schema_rules['allowed_dtypes']
        for key, value in outputs.items():
            if hasattr(value, 'dtype'):
                dtype_str = str(value.dtype).replace('torch.', '')
                if dtype_str not in allowed_dtypes:
                    errors.append(f"Invalid dtype for {key}: {dtype_str}")
        
        # 3. 检查 NaN/Inf
        for key, value in outputs.items():
            if hasattr(value, 'numpy'):
                arr = value.numpy() if hasattr(value, 'numpy') else value
                if isinstance(arr, np.ndarray):
                    if np.any(np.isnan(arr)):
                        errors.append(f"NaN detected in {key}")
                    if np.any(np.isinf(arr)):
                        errors.append(f"Inf detected in {key}")
        
        # 4. 数值合理性检查
        sanity = self.schema_rules['numeric_sanity']
        if 'pred_depth' in outputs or 'pred_pts3d_1' in outputs:
            # 深度检查
            depth_key = 'pred_depth' if 'pred_depth' in outputs else 'pred_pts3d_1'
            depth = outputs[depth_key]
            if hasattr(depth, 'numpy'):
                depth = depth.numpy() if hasattr(depth, 'numpy') else depth
            if isinstance(depth, np.ndarray):
                if depth.min() < sanity['depth_min']:
                    errors.append(f"Depth below minimum: {depth.min():.4f}")
                if depth.max() > sanity['depth_max']:
                    errors.append(f"Depth above maximum: {depth.max():.4f}")
        
        passed = len(errors) == 0
        self.results['checks']['schema'] = {
            "passed": passed,
            "errors": errors
        }
        
        return passed, errors
    
    def check_golden_comparison(
        self,
        current_results: List[Dict],
        tolerance_level: str = "fp16"
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        与 Golden outputs 对比
        
        Args:
            current_results: 当前运行结果（逐样本）
            tolerance_level: 容差级别 ("fp16" 或 "int8")
            
        Returns:
            (passed, comparison_details)
        """
        golden_data = self.load_golden()
        tolerances = self.golden_config['comparison_tolerance'][tolerance_level]
        
        comparison = {
            "tolerance_level": tolerance_level,
            "num_samples": len(golden_data),
            "deviations": [],
            "max_deviations": {}
        }
        
        # 需要对比的字段
        compare_fields = ['t_err_m', 'R_err_deg', 'absrel', 'rmse', 'delta1']
        
        all_passed = True
        max_devs = {field: 0.0 for field in compare_fields}
        
        for golden, current in zip(golden_data, current_results):
            sample_id = golden['sample_id']
            sample_devs = {"sample_id": sample_id}
            
            for field in compare_fields:
                if field not in golden or field not in current:
                    continue
                
                g_val = golden[field]
                c_val = current[field]
                
                # 计算相对偏差
                if g_val != 0:
                    rel_dev = abs(c_val - g_val) / abs(g_val)
                else:
                    rel_dev = abs(c_val - g_val)
                
                sample_devs[field] = {
                    "golden": g_val,
                    "current": c_val,
                    "rel_deviation": rel_dev
                }
                
                max_devs[field] = max(max_devs[field], rel_dev)
                
                # 检查是否超出容差
                tol_key = f"{field}_rtol"
                atol_key = f"{field}_atol"
                
                if tol_key in tolerances:
                    if rel_dev > tolerances[tol_key]:
                        all_passed = False
                        sample_devs[field]['exceeded'] = True
                elif atol_key in tolerances:
                    if abs(c_val - g_val) > tolerances[atol_key]:
                        all_passed = False
                        sample_devs[field]['exceeded'] = True
            
            comparison['deviations'].append(sample_devs)
        
        comparison['max_deviations'] = max_devs
        comparison['passed'] = all_passed
        
        self.results['checks']['golden_comparison'] = comparison
        
        return all_passed, comparison
    
    def check_stability(
        self,
        outputs_list: List[Dict[str, Any]]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        稳定性检查：NaN/Inf 率、崩溃率
        
        Args:
            outputs_list: 所有样本的输出列表
            
        Returns:
            (passed, stability_info)
        """
        nan_count = 0
        inf_count = 0
        crash_count = 0
        total = len(outputs_list)
        
        for outputs in outputs_list:
            if outputs is None:
                crash_count += 1
                continue
            
            for key, value in outputs.items():
                if hasattr(value, 'numpy'):
                    arr = value.numpy() if hasattr(value, 'numpy') else value
                    if isinstance(arr, np.ndarray):
                        if np.any(np.isnan(arr)):
                            nan_count += 1
                            break
                        if np.any(np.isinf(arr)):
                            inf_count += 1
                            break
        
        nan_rate = nan_count / total if total > 0 else 0
        inf_rate = inf_count / total if total > 0 else 0
        crash_rate = crash_count / total if total > 0 else 0
        
        stability = {
            "total_samples": total,
            "nan_count": nan_count,
            "inf_count": inf_count,
            "crash_count": crash_count,
            "nan_rate": nan_rate,
            "inf_rate": inf_rate,
            "crash_rate": crash_rate,
        }
        
        # 检查护栏
        guardrails = self.guardrails['stability']
        passed = (
            nan_rate <= guardrails['nan_inf_rate'] and
            inf_rate <= guardrails['nan_inf_rate'] and
            crash_rate <= guardrails['crash_rate']
        )
        
        stability['passed'] = passed
        self.results['checks']['stability'] = stability
        
        return passed, stability
    
    def run_gate(
        self,
        model_outputs: List[Dict[str, Any]],
        metrics_results: List[Dict],
        tolerance_level: str = "fp16"
    ) -> Tuple[bool, Dict]:
        """
        运行完整的 Smoke Gate
        
        Args:
            model_outputs: 模型原始输出列表
            metrics_results: 计算后的指标结果列表
            tolerance_level: 容差级别
            
        Returns:
            (all_passed, full_results)
        """
        print("\n" + "="*60)
        print("🔍 SMOKE GATE - 正确性验证")
        print("="*60)
        
        all_passed = True
        
        # 1. Schema 检查（用第一个样本）
        print("\n[1/3] Schema 断言检查...")
        if model_outputs:
            schema_passed, schema_errors = self.check_schema(model_outputs[0])
            if schema_passed:
                print("  ✅ Schema 检查通过")
            else:
                print("  ❌ Schema 检查失败:")
                for err in schema_errors:
                    print(f"     - {err}")
                all_passed = False
        else:
            print("  ⚠️ 无模型输出，跳过 Schema 检查")
        
        # 2. Golden 对比
        print(f"\n[2/3] Golden 对比检查 (tolerance: {tolerance_level})...")
        try:
            golden_passed, golden_info = self.check_golden_comparison(
                metrics_results, tolerance_level
            )
            if golden_passed:
                print("  ✅ Golden 对比通过")
                print(f"     最大偏差: {golden_info['max_deviations']}")
            else:
                print("  ❌ Golden 对比失败:")
                for dev in golden_info['deviations']:
                    for field, info in dev.items():
                        if isinstance(info, dict) and info.get('exceeded'):
                            print(f"     - {dev['sample_id']}.{field}: "
                                  f"golden={info['golden']:.4f}, "
                                  f"current={info['current']:.4f}")
                all_passed = False
        except FileNotFoundError as e:
            print(f"  ⚠️ {e}")
            print("  跳过 Golden 对比")
        
        # 3. 稳定性检查
        print("\n[3/3] 稳定性检查...")
        stability_passed, stability_info = self.check_stability(model_outputs)
        if stability_passed:
            print("  ✅ 稳定性检查通过")
            print(f"     NaN率: {stability_info['nan_rate']:.2%}, "
                  f"Inf率: {stability_info['inf_rate']:.2%}, "
                  f"崩溃率: {stability_info['crash_rate']:.2%}")
        else:
            print("  ❌ 稳定性检查失败:")
            print(f"     NaN: {stability_info['nan_count']}, "
                  f"Inf: {stability_info['inf_count']}, "
                  f"Crash: {stability_info['crash_count']}")
            all_passed = False
        
        # 总结
        print("\n" + "-"*60)
        self.results['passed'] = all_passed
        if all_passed:
            print("🎉 SMOKE GATE 通过！可以继续 Trend Gate")
        else:
            print("🚫 SMOKE GATE 失败！请检查上述错误后重试")
        print("-"*60 + "\n")
        
        return all_passed, self.results
    
    def save_results(self, output_path: str):
        """保存验证结果"""
        with open(output_path, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"结果已保存到: {output_path}")


def create_golden_outputs(
    model,
    smoke_samples: List,
    output_path: str = "runs/BASELINE_FREEZE/golden_smoke.jsonl"
):
    """
    创建 Golden outputs（只需运行一次）
    
    Args:
        model: DUSt3R 模型
        smoke_samples: 冒烟测试样本列表
        output_path: 输出路径
    """
    print("创建 Golden outputs...")
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    results = []
    for sample in smoke_samples:
        # TODO: 运行模型并计算指标
        # result = run_inference_and_eval(model, sample)
        # results.append(result)
        pass
    
    with open(output_path, 'w') as f:
        for result in results:
            f.write(json.dumps(result) + '\n')
    
    print(f"Golden outputs 已保存到: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Smoke Gate 验证")
    parser.add_argument("--create-golden", action="store_true",
                       help="创建 Golden outputs")
    parser.add_argument("--method", type=str, default="Q",
                       help="PQK 方法 (P/Q/K)")
    parser.add_argument("--variant", type=str, default="fp16",
                       help="变体 (fp16, int8, pruned_50, etc.)")
    parser.add_argument("--tolerance", type=str, default="fp16",
                       choices=["fp16", "int8"],
                       help="容差级别")
    parser.add_argument("--output", type=str,
                       help="结果输出路径")
    
    args = parser.parse_args()
    
    if args.create_golden:
        # TODO: 实现 golden 创建
        print("请实现 create_golden_outputs 函数")
        return
    
    # 加载 Smoke Gate
    gate = SmokeGate()
    
    # TODO: 加载模型和运行推理
    # model = load_model(args.method, args.variant)
    # outputs, metrics = run_smoke_inference(model)
    # passed, results = gate.run_gate(outputs, metrics, args.tolerance)
    
    print("\n[Demo Mode] Smoke Gate 框架已就绪")
    print("请集成实际的模型推理代码")
    
    # 保存结果
    if args.output:
        gate.save_results(args.output)


if __name__ == "__main__":
    main()
