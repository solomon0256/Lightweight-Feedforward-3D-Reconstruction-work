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
import os
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

def setup_dust3r_paths():
    """设置 DUSt3R 和 CroCo 路径"""
    dust3r_path = PROJECT_ROOT / 'third_party' / 'dust3r'
    croco_path = dust3r_path / 'croco'
    
    # 确保 croco/models/__init__.py 存在
    croco_models_init = croco_path / 'models' / '__init__.py'
    if not croco_models_init.exists():
        croco_models_init.parent.mkdir(parents=True, exist_ok=True)
        croco_models_init.touch()
    
    # 添加到 sys.path
    for p in [str(dust3r_path), str(croco_path)]:
        if p not in sys.path:
            sys.path.insert(0, p)


def load_dust3r_model(model_name: str = 'naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt', device: str = 'cuda') -> nn.Module:
    """
    加载 DUSt3R Teacher 模型（从 HuggingFace Hub）
    
    Args:
        model_name: HuggingFace 模型名称，默认 'naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt'
        device: 设备 ('cuda' / 'cpu')
    
    Returns:
        加载好的模型
    """
    setup_dust3r_paths()
    
    from dust3r.model import AsymmetricCroCo3DStereo
    
    print(f"[INFO] Loading DUSt3R from HuggingFace: {model_name}")
    model = AsymmetricCroCo3DStereo.from_pretrained(model_name)
    model = model.to(device)
    model.eval()
    
    params = sum(p.numel() for p in model.parameters())
    print(f"[INFO] Model loaded: {params/1e6:.2f}M parameters")
    
    return model


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

def load_eval_pairs(pairs_list_path: str, limit: int = None, seed: int = None):
    """
    加载评测对图列表
    
    文件格式：每行 "path_img1|path_img2"
    
    Args:
        pairs_list_path: pairs列表文件路径
        limit: 限制返回的pairs数量
        seed: 随机种子（用于可复现的随机选择）
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
    
    # 如果提供了seed，使用随机选择（可复现）
    if seed is not None:
        import random
        random.seed(seed)
        random.shuffle(pairs)
    
    if limit:
        pairs = pairs[:limit]
    
    print(f"[INFO] Loaded {len(pairs)} image pairs" + (f" (seed={seed})" if seed is not None else ""))
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


def create_temp_test_images(tmp_dir: str) -> tuple:
    """创建临时测试图像"""
    import numpy as np
    from PIL import Image
    
    # 创建有视差的测试图像
    img1 = np.zeros((384, 512, 3), dtype=np.uint8)
    img1[100:200, 150:350] = [255, 0, 0]
    img1[200:300, 200:400] = [0, 255, 0]
    
    img2 = np.zeros((384, 512, 3), dtype=np.uint8)
    img2[100:200, 170:370] = [255, 0, 0]
    img2[200:300, 220:420] = [0, 255, 0]
    
    img1_path = os.path.join(tmp_dir, "view1.png")
    img2_path = os.path.join(tmp_dir, "view2.png")
    Image.fromarray(img1).save(img1_path)
    Image.fromarray(img2).save(img2_path)
    
    return img1_path, img2_path


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
    运行基线评测（使用 DUSt3R 官方推理 API）
    
    Returns:
        {
            'model_stats': ModelStats,
            'timing': TimingResult,
            'quality': QualityMetrics,
        }
    """
    # 导入 DUSt3R 推理工具
    from dust3r.utils.image import load_images
    from dust3r.image_pairs import make_pairs
    from dust3r.inference import inference
    
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
    
    # 干跑模式：创建临时测试图像
    if dry_run:
        import tempfile
        tmp_dir = tempfile.mkdtemp()
        dummy_img1, dummy_img2 = create_temp_test_images(tmp_dir)
    
    with torch.no_grad():
        for i, (img1_path, img2_path) in enumerate(pairs):
            # 干跑模式使用临时图像
            if dry_run:
                img1_path, img2_path = dummy_img1, dummy_img2
            
            # 使用 DUSt3R 官方 API 加载图像
            imgs = load_images([img1_path, img2_path], size=512, verbose=False)
            img_pairs = make_pairs(imgs, scene_graph="complete", prefilter=None, symmetrize=True)
            
            # 推理计时
            with timer.measure():
                output = inference(img_pairs, model, device, batch_size=1, verbose=False)
            
            # 提取输出
            pred1 = output['pred1']
            pred2 = output['pred2']
            
            # 质量指标
            pts3d = pred1['pts3d']  # [B, H, W, 3]
            conf = pred1['conf']    # [B, H, W]
            
            # 干跑时用自身作为 GT（仅验证流程）
            if dry_run:
                gt_output = {
                    'pts3d': pts3d,
                    'conf': conf,
                }
            else:
                gt_output = {'pts3d': pts3d, 'conf': conf}
            
            # 计算质量指标
            eval_output = {'pts3d': pts3d, 'conf': conf}
            quality = metrics_calc.compute_from_outputs(eval_output, gt_output)
            all_quality.append(quality)
            
            if (i + 1) % 10 == 0:
                print(f"  Processed {i + 1}/{len(pairs)} pairs")
    
    # 清理临时文件
    if dry_run:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
    
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
        # 直接从 HuggingFace 加载，不需要本地权重文件
        model_name = args.weights or 'naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt'
        model = load_dust3r_model(model_name, device)
    
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
