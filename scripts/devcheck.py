#!/usr/bin/env python3
"""
干跑校验脚本 - 验证配置和代码正确性

用途：
- 验证配置文件语法和字段
- 验证日志 schema
- 验证脚本可导入
- 不实际运行模型

运行示例：
    python scripts/devcheck.py
    python scripts/devcheck.py --verbose
"""

import argparse
import sys
import json
from pathlib import Path
from typing import List, Tuple

# 添加项目根目录到路径
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))


def check_config_files(root: Path, verbose: bool = False) -> Tuple[bool, List[str]]:
    """检查配置文件"""
    errors = []
    
    config_files = [
        root / 'config' / 'workload.yaml',
        root / 'config' / 'eval.yaml',
        root / 'expconfigs' / 'distill.yaml',
        root / 'expconfigs' / 'quant.yaml',
    ]
    
    for cfg_path in config_files:
        if not cfg_path.exists():
            errors.append(f"Missing config: {cfg_path}")
            continue
        
        try:
            import yaml
            with open(cfg_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if data is None:
                errors.append(f"Empty config: {cfg_path}")
            elif verbose:
                print(f"  ✅ {cfg_path.name}: {len(data)} top-level keys")
        except Exception as e:
            errors.append(f"Invalid YAML in {cfg_path}: {e}")
    
    return len(errors) == 0, errors


def check_log_schema(root: Path, verbose: bool = False) -> Tuple[bool, List[str]]:
    """检查日志 schema"""
    errors = []
    
    schema_path = root / 'logs' / 'unified_log_schema.json'
    
    if not schema_path.exists():
        errors.append(f"Missing schema: {schema_path}")
        return False, errors
    
    try:
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = json.load(f)
        
        required = schema.get('required', [])
        properties = schema.get('properties', {})
        
        if verbose:
            print(f"  ✅ Schema: {len(required)} required fields, {len(properties)} properties")
        
        # 验证必填字段都有定义
        for field in required:
            if field not in properties:
                errors.append(f"Required field '{field}' not in properties")
    
    except Exception as e:
        errors.append(f"Invalid JSON in schema: {e}")
    
    return len(errors) == 0, errors


def check_imports(verbose: bool = False) -> Tuple[bool, List[str]]:
    """检查模块可导入"""
    errors = []
    
    modules = [
        ('scripts.utils.config', ['ExperimentConfig', 'load_yaml']),
        ('scripts.utils.logger', ['ExperimentLog', 'UnifiedLogger']),
        ('scripts.utils.timer', ['Timer', 'BatchTimer']),
        ('scripts.utils.metrics', ['MetricsCalculator', 'QualityMetrics']),
        ('scripts.utils.model_stats', ['get_model_stats', 'ModelStats']),
        ('scripts.models', ['DUSt3RStudent', 'create_student_model']),
    ]
    
    for module_name, attrs in modules:
        try:
            module = __import__(module_name, fromlist=attrs)
            for attr in attrs:
                if not hasattr(module, attr):
                    errors.append(f"Missing attribute '{attr}' in {module_name}")
            
            if verbose:
                print(f"  ✅ {module_name}: {len(attrs)} attributes OK")
        
        except ImportError as e:
            errors.append(f"Cannot import {module_name}: {e}")
    
    return len(errors) == 0, errors


def check_workload_values(root: Path, verbose: bool = False) -> Tuple[bool, List[str]]:
    """检查工作负载口径值"""
    errors = []
    warnings = []
    
    try:
        import yaml
        
        workload_path = root / 'config' / 'workload.yaml'
        with open(workload_path, 'r', encoding='utf-8') as f:
            workload = yaml.safe_load(f)
        
        # 检查输入形状
        input_cfg = workload.get('input', {})
        shape = input_cfg.get('shape', [])
        
        if len(shape) != 4:
            errors.append(f"Input shape should be [B, C, H, W], got {shape}")
        else:
            B, C, H, W = shape
            if B != 1:
                warnings.append(f"Batch size is {B}, expected 1 for pair inference")
            if C != 3:
                errors.append(f"Channels should be 3, got {C}")
            if H not in [384, 512, 640]:
                warnings.append(f"Height {H} is non-standard (expected 384/512/640)")
            if W not in [384, 512, 640]:
                warnings.append(f"Width {W} is non-standard (expected 384/512/640)")
        
        # 检查 pair_graph
        pair_cfg = workload.get('pair_graph', {})
        k = pair_cfg.get('k', 0)
        if k < 1:
            errors.append(f"pair_graph.k should be >= 1, got {k}")
        
        # 检查 seed
        seed = workload.get('seed', None)
        if seed is None:
            warnings.append("No seed specified, results may not be reproducible")
        
        if verbose:
            print(f"  ✅ workload.yaml values checked")
            for w in warnings:
                print(f"    ⚠️  {w}")
    
    except Exception as e:
        errors.append(f"Error checking workload: {e}")
    
    return len(errors) == 0, errors


def check_eval_thresholds(root: Path, verbose: bool = False) -> Tuple[bool, List[str]]:
    """检查评测阈值"""
    errors = []
    
    try:
        import yaml
        
        eval_path = root / 'config' / 'eval.yaml'
        with open(eval_path, 'r', encoding='utf-8') as f:
            eval_cfg = yaml.safe_load(f)
        
        thresholds = eval_cfg.get('thresholds', {})
        
        # 检查阈值范围
        quality_drop = thresholds.get('quality_drop_main_pct', 0)
        if quality_drop < 0 or quality_drop > 10:
            errors.append(f"quality_drop_main_pct={quality_drop}% seems unreasonable")
        
        speedup = thresholds.get('speedup_pair_p50_pct', 0)
        if speedup < 0 or speedup > 90:
            errors.append(f"speedup_pair_p50_pct={speedup}% seems unreasonable")
        
        if verbose:
            print(f"  ✅ eval.yaml thresholds checked")
    
    except Exception as e:
        errors.append(f"Error checking eval: {e}")
    
    return len(errors) == 0, errors


def generate_dummy_log(root: Path, verbose: bool = False) -> Tuple[bool, List[str]]:
    """生成并验证虚拟日志"""
    errors = []
    
    try:
        from scripts.utils.logger import ExperimentLog
        
        # 创建测试日志
        log = ExperimentLog(
            exp_id="devcheck_test",
            combo="test",
            seed=42,
            dataset_id="test_dataset",
            split="val",
            params_M=100.0,
            flops_G=50.0,
            size_MB=200.0,
            vram_GB=4.0,
            chamfer=0.05,
            absrel=0.1,
            rmse=0.15,
            delta1=0.95,
            reproj_px=2.0,
            t_pair_p50_ms=50.0,
            t_pair_p95_ms=80.0,
            t_scene_s=10.0,
            pairs_per_sec=20.0,
            gpu_hours=0.1,
        )
        
        # 验证
        missing = log.validate()
        if missing:
            errors.append(f"Dummy log missing fields: {missing}")
        
        # 转换为字典
        data = log.to_dict()
        
        if verbose:
            print(f"  ✅ Dummy log created with {len(data)} fields")
    
    except Exception as e:
        errors.append(f"Error creating dummy log: {e}")
    
    return len(errors) == 0, errors


def check_directory_structure(root: Path, verbose: bool = False) -> Tuple[bool, List[str]]:
    """检查目录结构"""
    errors = []
    
    required_dirs = [
        'config',
        'expconfigs',
        'scripts',
        'scripts/utils',
        'scripts/models',
        'logs',
        'outputs',
        'datasets',
        'reports',
    ]
    
    for dir_name in required_dirs:
        dir_path = root / dir_name
        if not dir_path.exists():
            # 创建目录
            dir_path.mkdir(parents=True, exist_ok=True)
            if verbose:
                print(f"  📁 Created: {dir_name}/")
        elif verbose:
            print(f"  ✅ {dir_name}/")
    
    return True, errors


def main():
    parser = argparse.ArgumentParser(
        description='Development Check - Validate configs and code',
    )
    parser.add_argument('--project-root', type=str, default=None)
    parser.add_argument('--verbose', '-v', action='store_true')
    
    args = parser.parse_args()
    
    if args.project_root:
        root = Path(args.project_root)
    else:
        root = PROJECT_ROOT
    
    print("=" * 60)
    print("DUSt3R-PQK Development Check")
    print("=" * 60)
    print(f"Project root: {root}")
    print("=" * 60)
    
    all_passed = True
    all_errors = []
    
    checks = [
        ("Directory Structure", lambda: check_directory_structure(root, args.verbose)),
        ("Config Files", lambda: check_config_files(root, args.verbose)),
        ("Log Schema", lambda: check_log_schema(root, args.verbose)),
        ("Python Imports", lambda: check_imports(args.verbose)),
        ("Workload Values", lambda: check_workload_values(root, args.verbose)),
        ("Eval Thresholds", lambda: check_eval_thresholds(root, args.verbose)),
        ("Dummy Log Generation", lambda: generate_dummy_log(root, args.verbose)),
    ]
    
    for name, check_fn in checks:
        print(f"\n📋 Checking: {name}")
        try:
            passed, errors = check_fn()
            
            if passed:
                print(f"   ✅ PASSED")
            else:
                print(f"   ❌ FAILED")
                for err in errors:
                    print(f"      - {err}")
                all_errors.extend(errors)
                all_passed = False
        
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            all_passed = False
    
    # 总结
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ ALL CHECKS PASSED")
        print("=" * 60)
        print("\nYou can now run experiments:")
        print("  python scripts/baseline_eval.py --dry-run")
        print("  python scripts/train_distill.py --dry-run")
        print("  python scripts/quantize.py --dry-run")
        print("  python scripts/run_kq_pipeline.py --dry-run")
    else:
        print(f"❌ {len(all_errors)} ERRORS FOUND")
        print("=" * 60)
        for err in all_errors:
            print(f"  - {err}")
    
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
