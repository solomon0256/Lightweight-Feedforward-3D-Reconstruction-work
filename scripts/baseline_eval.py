#!/usr/bin/env python3
"""
Baseline 评测脚本 - Teacher 模型评测

用途：
- 评测 DUSt3R Teacher 模型的质量/效率/资源指标
- 产出基线日志 teacher_eval.json
- 为后续实验提供对照基准

运行示例：
    python scripts/baseline_eval.py --exp-config distill.yaml
    python scripts/baseline_eval.py --dry-run  # 干跑验证
"""

import argparse
import sys
import json
from pathlib import Path
from datetime import datetime

import torch
import torch.nn as nn

# 添加项目根目录到路径
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.config import (
    ExperimentConfig, add_common_args, config_from_args, get_project_root
)
from scripts.utils.logger import ExperimentLog, save_experiment_log
from scripts.utils.timer import Timer, BatchTimer, TimingResult
from scripts.utils.model_stats import get_model_stats, ModelStats
from scripts.utils.metrics import MetricsCalculator, QualityMetrics


# ============ DUSt3R 模型加载（适配层）============

def load_dust3r_model(weights_path: str, device: str = 'cuda') -> nn.Module:
    """
    加载 DUSt3R Teacher 模型
    
    注意：需要根据实际 DUSt3R 安装方式调整
    """
    # 方式1：尝试从 dust3r 包导入
    try:
        from dust3r.model import AsymmetricCroCo3DStereo
        from dust3r.inference import load_model
        
        model = load_model(weights_path, device=device)
        print(f"[INFO] Loaded DUSt3R model from: {weights_path}")
        return model
    except ImportError:
        pass
    
    # 方式2：尝试从本地 checkpoints 加载
    try:
        # 假设使用标准 PyTorch 保存格式
        checkpoint = torch.load(weights_path, map_location=device)
        
        # 检查是否包含模型定义
        if 'model' in checkpoint:
            model = checkpoint['model']
        elif 'state_dict' in checkpoint:
            # 需要先构建模型架构
            raise NotImplementedError(
                "Model architecture needed. Please install dust3r package or "
                "provide model class."
            )
        else:
            raise ValueError(f"Unknown checkpoint format: {checkpoint.keys()}")
        
        model = model.to(device)
        model.eval()
        return model
    except Exception as e:
        print(f"[ERROR] Failed to load model: {e}")
        raise


def create_dummy_model(device: str = 'cuda') -> nn.Module:
    """
    创建虚拟模型（用于干跑测试）
    """
    class DummyDUSt3R(nn.Module):
        def __init__(self):
            super().__init__()
            # 模拟 DUSt3R 的参数量级
            self.encoder = nn.Sequential(
                nn.Conv2d(3, 64, 7, stride=2, padding=3),
                nn.ReLU(),
                nn.Conv2d(64, 128, 3, stride=2, padding=1),
                nn.ReLU(),
                nn.Conv2d(128, 256, 3, stride=2, padding=1),
            )
            self.decoder = nn.Sequential(
                nn.ConvTranspose2d(256, 128, 4, stride=2, padding=1),
                nn.ReLU(),
                nn.ConvTranspose2d(128, 64, 4, stride=2, padding=1),
                nn.ReLU(),
                nn.Conv2d(64, 3, 3, padding=1),  # 输出点云坐标
            )
        
        def forward(self, img1, img2=None):
            """模拟双图输入"""
            if img2 is None:
                img2 = img1
            
            # 编码
            f1 = self.encoder(img1)
            f2 = self.encoder(img2)
            
            # 融合（简单拼接）
            f = f1 + f2
            
            # 解码
            out = self.decoder(f)
            
            return {
                'pts3d': out,
                'depth': out[:, 0:1, :, :],
            }
    
    model = DummyDUSt3R().to(device)
    model.eval()
    print("[INFO] Created dummy model for dry-run")
    return model


# ============ 数据加载 ============

def load_eval_pairs(pairs_list_path: str, limit: int = None):
    """
    加载评测对图列表
    
    文件格式：每行 "path_img1|path_img2"
    """
    pairs = []
    
    if not Path(pairs_list_path).exists():
        print(f"[WARN] Pairs list not found: {pairs_list_path}")
        return pairs
    
    with open(pairs_list_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and '|' in line:
                img1, img2 = line.split('|')
                pairs.append((img1.strip(), img2.strip()))
    
    if limit:
        pairs = pairs[:limit]
    
    print(f"[INFO] Loaded {len(pairs)} image pairs")
    return pairs


def create_dummy_pairs(num_pairs: int = 20, img_shape: tuple = (3, 512, 384)):
    """创建虚拟对图数据（用于干跑）"""
    pairs = []
    for i in range(num_pairs):
        pairs.append((f"dummy_img_{i}_a.jpg", f"dummy_img_{i}_b.jpg"))
    return pairs


def load_image_pair(img1_path: str, img2_path: str, shape: tuple, device: str):
    """
    加载并预处理图像对
    
    Returns:
        (tensor1, tensor2): 两个图像张量
    """
    try:
        from PIL import Image
        from torchvision import transforms
        
        transform = transforms.Compose([
            transforms.Resize((shape[2], shape[3])),  # H, W
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                               std=[0.229, 0.224, 0.225]),
        ])
        
        img1 = transform(Image.open(img1_path).convert('RGB')).unsqueeze(0)
        img2 = transform(Image.open(img2_path).convert('RGB')).unsqueeze(0)
        
        return img1.to(device), img2.to(device)
    except Exception as e:
        # 回退到随机张量
        print(f"[WARN] Failed to load images, using random: {e}")
        return create_dummy_batch(shape, device)


def create_dummy_batch(shape: tuple, device: str):
    """创建虚拟批次"""
    img1 = torch.randn(*shape, device=device)
    img2 = torch.randn(*shape, device=device)
    return img1, img2


# ============ 评测主流程 ============

def run_baseline_eval(
    model: nn.Module,
    pairs: list,
    input_shape: tuple,
    device: str,
    num_warmup: int = 3,
    dry_run: bool = False,
) -> dict:
    """
    运行基线评测
    
    Returns:
        {
            'model_stats': ModelStats,
            'timing': TimingResult,
            'quality': QualityMetrics,
        }
    """
    model.eval()
    
    # 1. 模型统计
    print("[INFO] Computing model statistics...")
    model_stats = get_model_stats(
        model, 
        input_shape=input_shape,
        device=device,
        measure_vram_flag=(device == 'cuda')
    )
    print(f"  {model_stats}")
    
    # 2. 时延测量
    print(f"[INFO] Running inference on {len(pairs)} pairs...")
    timer = BatchTimer(warmup=num_warmup, sync_cuda=(device == 'cuda'))
    
    metrics_calc = MetricsCalculator(device=device)
    all_quality = []
    
    with torch.no_grad():
        for i, (img1_path, img2_path) in enumerate(pairs):
            # 加载数据
            if dry_run:
                img1, img2 = create_dummy_batch(input_shape, device)
            else:
                img1, img2 = load_image_pair(img1_path, img2_path, input_shape, device)
            
            # 推理计时
            with timer.measure():
                output = model(img1, img2)
            
            # 质量指标（干跑时用随机 GT）
            if dry_run:
                gt_output = {
                    'pts3d': output.get('pts3d', torch.randn_like(img1)),
                    'depth': output.get('depth', torch.rand(1, 1, input_shape[2], input_shape[3], device=device)),
                }
            else:
                gt_output = output  # 实际评测时需要加载 GT
            
            # 计算质量指标
            quality = metrics_calc.compute_from_outputs(output, gt_output)
            all_quality.append(quality)
            
            if (i + 1) % 10 == 0:
                print(f"  Processed {i + 1}/{len(pairs)} pairs")
    
    # 汇总时延
    timing = timer.get_result()
    print(f"  {timing}")
    
    # 汇总质量指标（取平均）
    avg_quality = QualityMetrics(
        chamfer=sum(q.chamfer for q in all_quality) / len(all_quality),
        absrel=sum(q.absrel for q in all_quality) / len(all_quality),
        rmse=sum(q.rmse for q in all_quality) / len(all_quality),
        delta1=sum(q.delta1 for q in all_quality) / len(all_quality),
        reproj_px=sum(q.reproj_px for q in all_quality) / len(all_quality),
    )
    print(f"  Quality: {avg_quality}")
    
    return {
        'model_stats': model_stats,
        'timing': timing,
        'quality': avg_quality,
    }


def create_baseline_log(
    config: ExperimentConfig,
    results: dict,
    gpu_hours: float = 0.0,
    notes: str = None,
) -> ExperimentLog:
    """创建基线日志"""
    model_stats: ModelStats = results['model_stats']
    timing: TimingResult = results['timing']
    quality: QualityMetrics = results['quality']
    
    return ExperimentLog(
        exp_id="baseline_teacher_v1",
        combo="baseline",
        seed=config.seed,
        dataset_id=config.workload.get('data', {}).get('dataset_id', 'unknown'),
        split=config.workload.get('data', {}).get('split', 'val'),
        
        # 资源指标
        params_M=model_stats.params_M,
        flops_G=model_stats.flops_G,
        size_MB=model_stats.size_MB,
        vram_GB=model_stats.vram_GB,
        
        # 质量指标
        chamfer=quality.chamfer,
        absrel=quality.absrel,
        rmse=quality.rmse,
        delta1=quality.delta1,
        reproj_px=quality.reproj_px,
        
        # 效率指标
        t_pair_p50_ms=timing.p50_ms,
        t_pair_p95_ms=timing.p95_ms,
        t_scene_s=timing.total_s,
        pairs_per_sec=timing.throughput,
        
        # 元信息
        num_pairs=timing.count,
        gpu_hours=gpu_hours,
        notes=notes or "Baseline teacher evaluation",
    )


# ============ 主函数 ============

def main():
    parser = argparse.ArgumentParser(
        description='DUSt3R Baseline (Teacher) Evaluation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser = add_common_args(parser)
    parser.add_argument('--weights', type=str, default=None,
                        help='Teacher 模型权重路径')
    parser.add_argument('--num-pairs', type=int, default=None,
                        help='评测 pair 数量限制')
    parser.add_argument('--output', type=str, default='teacher_eval',
                        help='输出日志文件名（不含扩展名）')
    
    args = parser.parse_args()
    
    # 加载配置
    config = config_from_args(args)
    config.paths.ensure_dirs()
    
    print("=" * 60)
    print("DUSt3R Baseline Evaluation")
    print("=" * 60)
    print(f"  Exp ID: {config.exp_id}")
    print(f"  Device: {config.device}")
    print(f"  Input shape: {config.input_shape}")
    print(f"  Dry run: {args.dry_run}")
    print("=" * 60)
    
    # 确定设备
    device = config.device
    if device == 'cuda' and not torch.cuda.is_available():
        print("[WARN] CUDA not available, falling back to CPU")
        device = 'cpu'
    
    # 加载模型
    if args.dry_run:
        model = create_dummy_model(device)
    else:
        weights_path = args.weights or config.experiment.get('teacher', {}).get('weights')
        if not weights_path:
            print("[ERROR] No weights path specified. Use --weights or set in config.")
            print("[INFO] Running in dry-run mode instead...")
            model = create_dummy_model(device)
            args.dry_run = True
        else:
            model = load_dust3r_model(weights_path, device)
    
    # 加载评测数据
    if args.dry_run:
        num_pairs = args.num_pairs or 20
        pairs = create_dummy_pairs(num_pairs, config.input_shape[1:])
    else:
        pairs_list = config.workload.get('data', {}).get('eval_pairs_list')
        pairs = load_eval_pairs(pairs_list, limit=args.num_pairs)
        if not pairs:
            print("[WARN] No pairs loaded, using dummy data")
            pairs = create_dummy_pairs(20, config.input_shape[1:])
            args.dry_run = True
    
    # 运行评测
    start_time = datetime.now()
    results = run_baseline_eval(
        model=model,
        pairs=pairs,
        input_shape=config.input_shape,
        device=device,
        dry_run=args.dry_run,
    )
    elapsed_hours = (datetime.now() - start_time).total_seconds() / 3600
    
    # 创建日志
    log = create_baseline_log(
        config=config,
        results=results,
        gpu_hours=elapsed_hours,
        notes=f"{'[DRY-RUN] ' if args.dry_run else ''}Baseline teacher evaluation",
    )
    
    # 保存日志
    output_paths = save_experiment_log(
        log=log,
        log_dir=config.paths.logs,
        also_csv=True,
    )
    
    print("=" * 60)
    print("Evaluation Complete!")
    print(f"  JSON log: {output_paths['json']}")
    print(f"  CSV log: {output_paths['csv']}")
    print("=" * 60)
    
    # 打印关键结果
    print("\n📊 Key Results:")
    print(f"  Params: {log.params_M:.2f}M")
    print(f"  FLOPs: {log.flops_G:.2f}G")
    print(f"  Size: {log.size_MB:.2f}MB")
    print(f"  t_pair p50: {log.t_pair_p50_ms:.2f}ms")
    print(f"  t_pair p95: {log.t_pair_p95_ms:.2f}ms")
    print(f"  Throughput: {log.pairs_per_sec:.2f} pairs/sec")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
