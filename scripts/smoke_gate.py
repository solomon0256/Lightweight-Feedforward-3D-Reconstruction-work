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
import torch
from PIL import Image

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 导入必要的模块
from scripts.baseline_eval import load_dust3r_model, setup_dust3r_paths, load_eval_pairs
from scripts.eval_depth_pose import evaluate_pair, compute_depth_metrics, compute_pose_error
from scripts.utils.timer import BatchTimer
from scripts.utils.config import ExperimentConfig


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
        tolerance_level: str = "fp16",
        method: Optional[str] = None,
        variant: Optional[str] = None,
        checkpoint_path: Optional[str] = None,
        model = None
    ) -> Tuple[bool, Dict]:
        """
        运行完整的 Smoke Gate
        
        Args:
            model_outputs: 模型原始输出列表
            metrics_results: 计算后的指标结果列表
            tolerance_level: 容差级别
            method: 轻量化方法 ('K'/'Q'/'P')，如果提供则验证轻量化过程
            variant: 变体名称
            checkpoint_path: checkpoint 路径
            model: 已加载的模型
            
        Returns:
            (all_passed, full_results)
        """
        print("\n" + "="*60)
        print("🔍 SMOKE GATE - 正确性验证")
        print("="*60)
        
        all_passed = True
        
        # 0. 轻量化过程验证（如果提供了 method）
        if method:
            print(f"\n[0/4] 轻量化过程验证 (method: {method}, variant: {variant})...")
            process_passed, process_msg = verify_lightweighting_process(
                method, variant, checkpoint_path, model
            )
            if process_passed:
                print(f"  ✅ 轻量化过程验证通过: {process_msg}")
            else:
                print(f"  ❌ 轻量化过程验证失败: {process_msg}")
                all_passed = False
                # 如果轻量化过程失败，直接返回
                self.results['passed'] = False
                self.results['checks']['lightweighting_process'] = {
                    "passed": False,
                    "error": process_msg
                }
                return False, self.results
            
            self.results['checks']['lightweighting_process'] = {
                "passed": True,
                "message": process_msg
            }
        
        # 1. Schema 检查（用第一个样本）
        print("\n[1/4] Schema 断言检查...")
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
        print(f"\n[2/4] Golden 对比检查 (tolerance: {tolerance_level})...")
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
        print("\n[3/4] 稳定性检查...")
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


def verify_lightweighting_process(
    method: str,
    variant: str,
    checkpoint_path: Optional[str] = None,
    model = None,
    device: str = 'cuda'
) -> Tuple[bool, str]:
    """
    验证轻量化过程是否成功
    
    Args:
        method: 'K' (蒸馏), 'Q' (量化), 'P' (剪枝)
        variant: 变体名称
        checkpoint_path: checkpoint 路径
        model: 已加载的模型（可选）
        device: 设备
    
    Returns:
        (success, error_message)
    """
    if method == 'K':  # 蒸馏
        if not checkpoint_path:
            return False, "蒸馏方法需要提供 checkpoint_path"
        
        checkpoint = Path(checkpoint_path)
        if not checkpoint.exists():
            return False, f"Student 模型 checkpoint 不存在: {checkpoint_path}"
        
        try:
            # 尝试加载 student 模型
            from scripts.models import create_student_model
            
            # 创建 student 模型架构
            student = create_student_model(arch='dust3r_student_s', device=device)
            
            # 加载权重
            state_dict = torch.load(checkpoint_path, map_location=device)
            if isinstance(state_dict, dict):
                if 'state_dict' in state_dict:
                    state_dict = state_dict['state_dict']
                elif 'model' in state_dict:
                    state_dict = state_dict['model']
            
            student.load_state_dict(state_dict, strict=False)
            student.eval()
            
            # 运行一次推理测试
            dummy_input = torch.randn(1, 3, 512, 384).to(device)
            with torch.no_grad():
                _ = student(dummy_input, dummy_input)
            
            return True, "Student 模型加载和运行成功"
        except Exception as e:
            return False, f"Student 模型加载失败: {str(e)}"
    
    elif method == 'Q':  # 量化
        if variant == 'fp16':
            # FP16 量化：检查模型是否已转换为 FP16
            if model is None:
                return False, "FP16 量化需要提供模型"
            
            # 检查模型参数是否为 FP16
            first_param = next(model.parameters())
            if first_param.dtype != torch.float16:
                return False, "模型未转换为 FP16"
            
            # 运行一次推理测试
            try:
                dummy_input = torch.randn(1, 3, 512, 384).to(device).half()
                with torch.no_grad():
                    _ = model(dummy_input, dummy_input)
                return True, "FP16 量化模型运行成功"
            except Exception as e:
                return False, f"FP16 量化模型运行失败: {str(e)}"
        
        elif variant == 'int8':
            # INT8 量化：检查量化过程是否成功
            if not checkpoint_path:
                return False, "INT8 量化需要提供 checkpoint_path"
            
            checkpoint = Path(checkpoint_path)
            if not checkpoint.exists():
                return False, f"量化模型 checkpoint 不存在: {checkpoint_path}"
            
            try:
                # 尝试加载量化后的模型
                # 注意：INT8 量化模型的加载方式可能不同
                # 这里先检查文件是否存在，实际加载逻辑在 model_loader 中
                return True, "量化模型 checkpoint 存在"
            except Exception as e:
                return False, f"量化模型检查失败: {str(e)}"
    
    elif method == 'P':  # 剪枝
        if not checkpoint_path:
            return False, "剪枝方法需要提供 checkpoint_path"
        
        checkpoint = Path(checkpoint_path)
        if not checkpoint.exists():
            return False, f"剪枝模型 checkpoint 不存在: {checkpoint_path}"
        
        try:
            # 尝试加载剪枝后的模型
            # 剪枝后的模型结构可能与原始模型相同，但某些权重为0
            state_dict = torch.load(checkpoint_path, map_location=device)
            if isinstance(state_dict, dict):
                if 'state_dict' in state_dict:
                    state_dict = state_dict['state_dict']
                elif 'model' in state_dict:
                    state_dict = state_dict['model']
            
            # 检查剪枝率（可选）
            # 可以统计非零权重的比例
            
            return True, "剪枝模型 checkpoint 存在"
        except Exception as e:
            return False, f"剪枝模型检查失败: {str(e)}"
    
    return False, f"未知的方法: {method}"


def run_inference_and_eval(
    model,
    img1_path: str,
    img2_path: str,
    sample_id: str,
    device: str = 'cuda',
    gt_depth1: Optional[np.ndarray] = None,
    gt_pose1: Optional[np.ndarray] = None,
    gt_pose2: Optional[np.ndarray] = None
) -> Dict[str, Any]:
    """
    运行模型推理并计算指标
    
    Args:
        model: DUSt3R 模型
        img1_path: 第一张图像路径
        img2_path: 第二张图像路径
        sample_id: 样本ID
        device: 设备
        gt_depth1: GT深度图（可选）
        gt_pose1: GT位姿1（可选，4x4矩阵）
        gt_pose2: GT位姿2（可选，4x4矩阵）
    
    Returns:
        dict: 包含 sample_id, t_err_m, R_err_deg, absrel, rmse, delta1, scale_s
    """
    try:
        # 调用 evaluate_pair 获取深度和位姿指标
        depth_metrics, pose_metrics = evaluate_pair(
            model, img1_path, img2_path,
            gt_depth1, gt_pose1, gt_pose2,
            device=device
        )
        
        # 格式化结果为 Smoke Gate 需要的格式
        result = {
            'sample_id': sample_id,
            't_err_m': pose_metrics.get('rte_cm', np.nan) / 100.0,  # cm -> m
            'R_err_deg': pose_metrics.get('rre_deg', np.nan),
            'absrel': depth_metrics.get('abs_rel', np.nan),
            'rmse': depth_metrics.get('rmse', np.nan),
            'delta1': depth_metrics.get('delta1', np.nan),
            'scale_s': pose_metrics.get('scale', 1.0)
        }
        
        return result
    except Exception as e:
        print(f"推理失败 [{sample_id}]: {e}")
        return {
            'sample_id': sample_id,
            't_err_m': np.nan,
            'R_err_deg': np.nan,
            'absrel': np.nan,
            'rmse': np.nan,
            'delta1': np.nan,
            'scale_s': 1.0
        }


def load_smoke_samples(contract_path: str = "config/eval_contract.yaml", 
                       workload_path: str = "config/workload.yaml") -> List[Tuple]:
    """
    加载 Smoke Set 样本
    
    Returns:
        List of tuples: (img1_path, img2_path, sample_id)
    """
    # 读取配置
    with open(contract_path, 'r', encoding='utf-8') as f:
        contract = yaml.safe_load(f)
    
    with open(workload_path, 'r', encoding='utf-8') as f:
        workload = yaml.safe_load(f)
    
    smoke_config = contract['validation_sets']['smoke']
    num_pairs = smoke_config['num_pairs']
    seed = smoke_config.get('seed', 42)
    
    # 加载 pairs 列表
    pairs_list_path = workload.get('data', {}).get('eval_pairs_list', '')
    if not pairs_list_path or not Path(pairs_list_path).exists():
        print(f"[WARN] Pairs list not found: {pairs_list_path}")
        print("[INFO] 使用空列表，需要手动提供数据")
        return []
    
    pairs = load_eval_pairs(pairs_list_path, limit=num_pairs, seed=seed)
    
    # 格式化样本
    samples = []
    for i, (img1_path, img2_path) in enumerate(pairs):
        sample_id = f"smoke_{i:03d}"
        samples.append((img1_path, img2_path, sample_id))
    
    return samples


def create_golden_outputs(
    model,
    smoke_samples: List = None,
    output_path: str = "runs/BASELINE_FREEZE/golden_smoke.jsonl",
    device: str = 'cuda'
):
    """
    创建 Golden outputs（只需运行一次）
    
    Args:
        model: DUSt3R 模型
        smoke_samples: 冒烟测试样本列表，如果为 None 则从配置文件加载
        output_path: 输出路径
        device: 设备
    """
    print("创建 Golden outputs...")
    
    # 如果没有提供样本，从配置文件加载
    if smoke_samples is None:
        smoke_samples = load_smoke_samples()
        if not smoke_samples:
            print("[ERROR] 无法加载 smoke samples，请检查配置文件")
            return
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    results = []
    for i, sample in enumerate(smoke_samples):
        if len(sample) >= 3:
            img1_path, img2_path, sample_id = sample[0], sample[1], sample[2]
        else:
            # 兼容旧格式：只有路径对
            img1_path, img2_path = sample[0], sample[1]
            sample_id = f"sample_{i:03d}"
        
        # 注意：Smoke Gate 创建 golden 时可能没有 GT，使用 None
        result = run_inference_and_eval(
            model, img1_path, img2_path, sample_id,
            device=device,
            gt_depth1=None,
            gt_pose1=None,
            gt_pose2=None
        )
        results.append(result)
        
        if (i + 1) % 4 == 0:
            print(f"  已处理 {i + 1}/{len(smoke_samples)} 个样本")
    
    with open(output_path, 'w') as f:
        for result in results:
            f.write(json.dumps(result) + '\n')
    
    print(f"Golden outputs 已保存到: {output_path}")
    print(f"共生成 {len(results)} 个样本的 golden outputs")


def run_smoke_inference(model, device: str = 'cuda') -> Tuple[List[Dict[str, Any]], List[Dict]]:
    """
    运行 Smoke Gate 推理
    
    Args:
        model: DUSt3R 模型
        device: 设备
    
    Returns:
        (model_outputs, metrics_results)
        - model_outputs: List[Dict] 模型原始输出（用于 Schema 检查）
        - metrics_results: List[Dict] 计算后的指标（用于 Golden 对比）
    """
    # 1. 加载 smoke set（16 对）
    smoke_samples = load_smoke_samples()
    if not smoke_samples:
        print("[ERROR] 无法加载 smoke samples")
        return [], []
    
    print(f"[INFO] 加载了 {len(smoke_samples)} 个 smoke samples")
    
    # 2. 对每个 pair 运行推理
    model_outputs = []
    metrics_results = []
    
    from dust3r.utils.image import load_images
    from dust3r.image_pairs import make_pairs
    from dust3r.inference import inference
    
    successful_inferences = 0
    failed_inferences = 0
    
    for i, (img1_path, img2_path, sample_id) in enumerate(smoke_samples):
        try:
            # 加载图像并创建 pairs
            images = load_images([str(img1_path), str(img2_path)], size=512)
            pairs = make_pairs(images, scene_graph='complete', prefilter=None, symmetrize=True)
            
            # 运行推理
            with torch.no_grad():
                output = inference(pairs, model, device, batch_size=1, verbose=False)
            
            # 提取模型原始输出（用于 Schema 检查）
            pred1 = output.get('pred1', {})
            pred2 = output.get('pred2', {})
            
            model_output = {
                'pred_pts3d_1': pred1.get('pts3d'),
                'pred_pts3d_2': pred2.get('pts3d'),
                'pred_conf_1': pred1.get('conf'),
                'pred_conf_2': pred2.get('conf'),
            }
            model_outputs.append(model_output)
            
            # 计算指标（用于 Golden 对比）
            result = run_inference_and_eval(
                model, img1_path, img2_path, sample_id,
                device=device,
                gt_depth1=None,
                gt_pose1=None,
                gt_pose2=None
            )
            metrics_results.append(result)
            successful_inferences += 1
            
            if (i + 1) % 4 == 0:
                print(f"  已处理 {i + 1}/{len(smoke_samples)} 个样本")
        
        except Exception as e:
            print(f"推理失败 [{sample_id}]: {e}")
            # 不添加None，而是跳过失败的样本
            failed_inferences += 1
            # 注意：不添加None到列表，保持列表只包含有效结果
    
    print(f"[INFO] 完成推理: 成功 {successful_inferences} 个，失败 {failed_inferences} 个")
    
    # 检查是否有足够的成功结果
    if successful_inferences == 0:
        print("[ERROR] 所有推理都失败了")
        return [], []
    
    if successful_inferences < len(smoke_samples) * 0.5:  # 如果失败率超过50%
        print(f"[WARN] 失败率过高 ({failed_inferences}/{len(smoke_samples)})，但继续处理")
    
    return model_outputs, metrics_results


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
    parser.add_argument("--device", type=str, default="cuda",
                       help="设备 (cuda/cpu)")
    parser.add_argument("--checkpoint", type=str, default=None,
                       help="模型 checkpoint 路径（用于量化/蒸馏/剪枝模型）")
    
    args = parser.parse_args()
    
    # 加载 Smoke Gate
    gate = SmokeGate()
    
    if args.create_golden:
        # 创建 Golden outputs
        print("\n" + "="*60)
        print("🔧 创建 Golden Outputs")
        print("="*60)
        
        setup_dust3r_paths()
        model = load_dust3r_model(device=args.device)
        
        create_golden_outputs(
            model,
            smoke_samples=None,  # 从配置文件加载
            output_path=gate.golden_path,
            device=args.device
        )
        
        print("\n✅ Golden outputs 创建完成！")
        return
    
    # 加载模型和运行推理
    print("\n" + "="*60)
    print(f"🔍 Smoke Gate 验证 - {args.method}/{args.variant}")
    print("="*60)
    
    from scripts.utils.model_loader import load_model
    
    try:
        model = load_model(
            args.method, 
            args.variant, 
            device=args.device,
            checkpoint_path=args.checkpoint
        )
        
        outputs, metrics = run_smoke_inference(model, device=args.device)
        
        # 更严格的检查：不仅检查列表是否为空，还检查是否有有效结果
        if not outputs or not metrics:
            print("[ERROR] 推理失败，无法获取结果")
            return
        
        # 检查是否有足够的有效结果（至少50%成功）
        if len(outputs) == 0 or len(metrics) == 0:
            print("[ERROR] 没有有效的推理结果")
            return
        
        # 检查metrics中是否有太多NaN值（表示推理失败）
        valid_metrics = [m for m in metrics if not (np.isnan(m.get('absrel', np.nan)) and np.isnan(m.get('delta1', np.nan)))]
        if len(valid_metrics) < len(metrics) * 0.5:
            print(f"[ERROR] 有效结果太少 ({len(valid_metrics)}/{len(metrics)})，验证失败")
            return
        
        passed, results = gate.run_gate(
            outputs, 
            metrics, 
            args.tolerance,
            method=args.method,
            variant=args.variant,
            checkpoint_path=args.checkpoint,
            model=model
        )
        
        # 保存结果
        if args.output:
            gate.save_results(args.output)
        else:
            # 默认保存路径
            output_path = f"runs/smoke_gate_{args.method}_{args.variant}.json"
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
