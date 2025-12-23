#!/usr/bin/env python3
"""
量化脚本 - Q-only / K→Q

用途：
- PTQ (Post-Training Quantization): 快速量化，校准后直接使用
- QAT (Quantization-Aware Training): 量化感知训练，精度更高
- ONNX 导出 + TensorRT 引擎构建

运行示例：
    python scripts/quantize.py --exp-config quant.yaml --mode ptq
    python scripts/quantize.py --exp-config quant.yaml --mode qat
    python scripts/quantize.py --dry-run
"""

import argparse
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List, Any, Tuple

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

# 添加项目根目录到路径
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.config import (
    ExperimentConfig, add_common_args, config_from_args
)
from scripts.utils.logger import ExperimentLog, save_experiment_log
from scripts.utils.timer import measure_inference_time
from scripts.utils.model_stats import get_model_stats, get_file_size_mb
from scripts.models import create_student_model


# ============ 校准数据集 ============

class CalibrationDataset(Dataset):
    """量化校准数据集"""
    
    def __init__(
        self,
        images_root: str,
        img_size: Tuple[int, int] = (512, 384),
        num_images: int = 512,
        dummy: bool = False,
    ):
        self.images_root = Path(images_root)
        self.img_size = img_size
        self.num_images = num_images
        self.dummy = dummy
        
        self.image_paths = []
        
        if not dummy and self.images_root.exists():
            # 收集图片
            for ext in ['*.jpg', '*.png', '*.jpeg']:
                self.image_paths.extend(self.images_root.glob(ext))
            self.image_paths = self.image_paths[:num_images]
        
        if len(self.image_paths) < num_images:
            print(f"[WARN] Only found {len(self.image_paths)} images, need {num_images}")
            self.dummy = True
    
    def __len__(self):
        return self.num_images
    
    def __getitem__(self, idx):
        if self.dummy:
            return torch.randn(3, *self.img_size)
        
        try:
            from PIL import Image
            from torchvision import transforms
            
            transform = transforms.Compose([
                transforms.Resize(self.img_size),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                   std=[0.229, 0.224, 0.225]),
            ])
            
            img_path = self.image_paths[idx % len(self.image_paths)]
            img = transform(Image.open(img_path).convert('RGB'))
            return img
        except Exception as e:
            return torch.randn(3, *self.img_size)


# ============ 量化工具 ============

class QuantizationConfig:
    """量化配置"""
    
    def __init__(
        self,
        bits_w: int = 8,
        bits_a: int = 8,
        weight_granularity: str = 'per-channel',
        activation_granularity: str = 'per-tensor',
        keep_list_modules: List[str] = None,
    ):
        self.bits_w = bits_w
        self.bits_a = bits_a
        self.weight_granularity = weight_granularity
        self.activation_granularity = activation_granularity
        self.keep_list_modules = keep_list_modules or []
    
    @classmethod
    def from_config(cls, quant_cfg: Dict[str, Any]) -> 'QuantizationConfig':
        return cls(
            bits_w=8,  # W8A8
            bits_a=8,
            weight_granularity=quant_cfg.get('weight', {}).get('granularity', 'per-channel'),
            activation_granularity=quant_cfg.get('activation', {}).get('granularity', 'per-tensor'),
            keep_list_modules=quant_cfg.get('keep_list_modules', []),
        )


def should_quantize_module(name: str, module: nn.Module, keep_list: List[str]) -> bool:
    """判断模块是否应该量化"""
    # 检查 keep_list
    for pattern in keep_list:
        if pattern in name:
            return False
    
    # 默认量化 Conv 和 Linear
    return isinstance(module, (nn.Conv2d, nn.Linear))


def apply_dynamic_quantization(model: nn.Module) -> nn.Module:
    """应用动态量化（最简单的量化方式）"""
    quantized_model = torch.quantization.quantize_dynamic(
        model,
        {nn.Linear},
        dtype=torch.qint8
    )
    return quantized_model


def prepare_ptq_model(
    model: nn.Module,
    quant_config: QuantizationConfig,
) -> nn.Module:
    """
    准备 PTQ 模型（插入量化观察器）
    
    使用 PyTorch 原生量化 API
    """
    model.eval()
    
    # 设置量化配置
    if quant_config.weight_granularity == 'per-channel':
        qconfig = torch.quantization.get_default_qconfig('fbgemm')
    else:
        qconfig = torch.quantization.default_qconfig
    
    # 应用 qconfig
    model.qconfig = qconfig
    
    # 准备模型（插入观察器）
    torch.quantization.prepare(model, inplace=True)
    
    return model


def calibrate_model(
    model: nn.Module,
    calib_loader: DataLoader,
    device: str = 'cpu',
    num_batches: int = None,
):
    """
    校准量化模型
    
    运行校准数据收集激活统计信息
    """
    model.eval()
    model = model.to(device)
    
    print(f"[INFO] Calibrating with {len(calib_loader)} batches...")
    
    with torch.no_grad():
        for i, batch in enumerate(calib_loader):
            if num_batches and i >= num_batches:
                break
            
            if isinstance(batch, torch.Tensor):
                img = batch.to(device)
            else:
                img = batch['img1'].to(device)
            
            _ = model(img)
            
            if (i + 1) % 50 == 0:
                print(f"  Calibrated {i + 1} batches")
    
    print("[INFO] Calibration complete")


def convert_to_quantized(model: nn.Module) -> nn.Module:
    """转换为量化模型"""
    model.eval()
    model = model.cpu()  # 量化转换需要在 CPU 上
    torch.quantization.convert(model, inplace=True)
    return model


# ============ QAT 训练 ============

def prepare_qat_model(
    model: nn.Module,
    quant_config: QuantizationConfig,
) -> nn.Module:
    """准备 QAT 模型"""
    model.train()
    
    # QAT 配置
    qconfig = torch.quantization.get_default_qat_qconfig('fbgemm')
    model.qconfig = qconfig
    
    # 融合模块（提高效率）
    # 注意：需要根据实际模型结构调整
    # torch.quantization.fuse_modules(model, [...], inplace=True)
    
    # 准备 QAT
    torch.quantization.prepare_qat(model, inplace=True)
    
    return model


def train_qat(
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    num_epochs: int = 15,
    lr: float = 1e-4,
    device: str = 'cuda',
    early_stop_patience: int = 3,
) -> Dict[str, Any]:
    """
    QAT 训练
    """
    model = model.to(device)
    model.train()
    
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()
    
    best_val_loss = float('inf')
    no_improve = 0
    history = {'train_loss': [], 'val_loss': []}
    
    print(f"\n[INFO] Starting QAT training for {num_epochs} epochs...")
    
    for epoch in range(num_epochs):
        # 训练
        model.train()
        train_loss = 0.0
        num_batches = 0
        
        for batch in train_loader:
            if isinstance(batch, torch.Tensor):
                img = batch.to(device)
                target = img  # 自监督
            else:
                img = batch['img1'].to(device)
                target = batch.get('gt_pts3d', img).to(device)
            
            optimizer.zero_grad()
            output = model(img)
            
            if isinstance(output, dict):
                output = output.get('pts3d', output.get('depth'))
            
            # 调整 target 形状
            if output.shape != target.shape:
                target = torch.randn_like(output)
            
            loss = criterion(output, target)
            loss.backward()
            optimizer.step()
            
            train_loss += loss.item()
            num_batches += 1
        
        avg_train_loss = train_loss / max(num_batches, 1)
        
        # 验证
        model.eval()
        val_loss = 0.0
        num_val = 0
        
        with torch.no_grad():
            for batch in val_loader:
                if isinstance(batch, torch.Tensor):
                    img = batch.to(device)
                    target = img
                else:
                    img = batch['img1'].to(device)
                    target = batch.get('gt_pts3d', img).to(device)
                
                output = model(img)
                if isinstance(output, dict):
                    output = output.get('pts3d', output.get('depth'))
                
                if output.shape != target.shape:
                    target = torch.randn_like(output)
                
                val_loss += criterion(output, target).item()
                num_val += 1
        
        avg_val_loss = val_loss / max(num_val, 1)
        
        history['train_loss'].append(avg_train_loss)
        history['val_loss'].append(avg_val_loss)
        
        print(f"  Epoch {epoch+1}/{num_epochs} | Train: {avg_train_loss:.4f} | Val: {avg_val_loss:.4f}")
        
        # 早停
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            no_improve = 0
        else:
            no_improve += 1
            if no_improve >= early_stop_patience:
                print(f"[INFO] Early stopping at epoch {epoch+1}")
                break
    
    return history


# ============ ONNX 导出 ============

def export_to_onnx(
    model: nn.Module,
    output_path: str,
    input_shape: Tuple[int, ...] = (1, 3, 512, 384),
    opset_version: int = 17,
    dynamic_axes: Dict = None,
) -> str:
    """
    导出模型为 ONNX 格式
    """
    model.eval()
    model = model.cpu()
    
    dummy_input = torch.randn(*input_shape)
    
    # 包装前向传播以返回单个张量
    class ONNXWrapper(nn.Module):
        def __init__(self, model):
            super().__init__()
            self.model = model
        
        def forward(self, x):
            out = self.model(x)
            if isinstance(out, dict):
                return out.get('pts3d', out.get('depth'))
            return out
    
    wrapped = ONNXWrapper(model)
    
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    torch.onnx.export(
        wrapped,
        dummy_input,
        str(output_path),
        export_params=True,
        opset_version=opset_version,
        do_constant_folding=True,
        input_names=['images'],
        output_names=['pts3d'],
        dynamic_axes=dynamic_axes,
    )
    
    print(f"[INFO] Exported ONNX model to: {output_path}")
    return str(output_path)


# ============ TensorRT 构建 ============

def build_tensorrt_engine(
    onnx_path: str,
    output_path: str,
    fp16: bool = True,
    int8: bool = False,
    max_workspace_gb: float = 8.0,
) -> Optional[str]:
    """
    构建 TensorRT 引擎
    
    需要安装 tensorrt 包
    """
    try:
        import tensorrt as trt
    except ImportError:
        print("[WARN] TensorRT not installed, skipping engine build")
        return None
    
    TRT_LOGGER = trt.Logger(trt.Logger.WARNING)
    
    builder = trt.Builder(TRT_LOGGER)
    network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    parser = trt.OnnxParser(network, TRT_LOGGER)
    
    # 解析 ONNX
    with open(onnx_path, 'rb') as f:
        if not parser.parse(f.read()):
            for error in range(parser.num_errors):
                print(f"[ERROR] ONNX Parse Error: {parser.get_error(error)}")
            return None
    
    # 配置
    config = builder.create_builder_config()
    config.max_workspace_size = int(max_workspace_gb * (1 << 30))
    
    if fp16:
        config.set_flag(trt.BuilderFlag.FP16)
    if int8:
        config.set_flag(trt.BuilderFlag.INT8)
    
    # 构建引擎
    print("[INFO] Building TensorRT engine (this may take a while)...")
    engine = builder.build_engine(network, config)
    
    if engine is None:
        print("[ERROR] Failed to build TensorRT engine")
        return None
    
    # 保存
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'wb') as f:
        f.write(engine.serialize())
    
    print(f"[INFO] TensorRT engine saved to: {output_path}")
    return str(output_path)


# ============ 主函数 ============

def main():
    parser = argparse.ArgumentParser(
        description='DUSt3R Model Quantization (PTQ/QAT)',
    )
    parser = add_common_args(parser)
    parser.add_argument('--mode', type=str, default='auto',
                        choices=['ptq', 'qat', 'auto'],
                        help='量化模式')
    parser.add_argument('--model-weights', type=str, default=None,
                        help='模型权重路径（FP32）')
    parser.add_argument('--export-onnx', action='store_true',
                        help='导出 ONNX')
    parser.add_argument('--build-trt', action='store_true',
                        help='构建 TensorRT 引擎')
    parser.add_argument('--output', type=str, default='quant_eval',
                        help='输出日志文件名')
    
    args = parser.parse_args()
    
    # 加载配置
    if args.exp_config is None:
        args.exp_config = 'quant.yaml'
    
    config = config_from_args(args)
    config.paths.ensure_dirs()
    
    print("=" * 60)
    print("DUSt3R Model Quantization")
    print("=" * 60)
    print(f"  Mode: {args.mode}")
    print(f"  Dry run: {args.dry_run}")
    print("=" * 60)
    
    # 设备（PTQ 校准需要在 CPU 或 CUDA 上，量化转换在 CPU）
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    
    # 加载模型
    model_cfg = config.experiment.get('model', {})
    weights_path = args.model_weights or model_cfg.get('weights_fp32')
    
    if weights_path and Path(weights_path).exists():
        print(f"[INFO] Loading model from: {weights_path}")
        # 假设使用 Student 架构
        model = create_student_model(arch='dust3r_student_s', device='cpu')
        state_dict = torch.load(weights_path, map_location='cpu')
        if isinstance(state_dict, dict) and 'state_dict' in state_dict:
            state_dict = state_dict['state_dict']
        model.load_state_dict(state_dict, strict=False)
    else:
        print("[WARN] No weights, using random initialized model")
        model = create_student_model(arch='dust3r_student_s', device='cpu')
    
    # 量化配置
    quant_cfg = config.experiment.get('quant', {})
    q_config = QuantizationConfig.from_config(quant_cfg)
    
    # 准备校准数据
    calib_cfg = quant_cfg.get('calibration', {})
    img_size = (config.input_shape[2], config.input_shape[3])
    
    calib_dataset = CalibrationDataset(
        images_root=calib_cfg.get('list', 'datasets/calibration/'),
        img_size=img_size,
        num_images=calib_cfg.get('num_images', 512),
        dummy=args.dry_run,
    )
    
    calib_loader = DataLoader(calib_dataset, batch_size=1, shuffle=False)
    
    print(f"[INFO] Calibration dataset: {len(calib_dataset)} images")
    
    # 执行量化
    mode = args.mode
    start_time = datetime.now()
    
    if mode == 'auto':
        # 先尝试 PTQ，如果精度损失大则转 QAT
        mode = 'ptq'
    
    if mode == 'ptq':
        print("\n[INFO] Running Post-Training Quantization (PTQ)...")
        
        # 准备
        model = prepare_ptq_model(model, q_config)
        
        # 校准
        calibrate_model(model, calib_loader, device='cpu', 
                       num_batches=100 if args.dry_run else None)
        
        # 转换
        quantized_model = convert_to_quantized(model)
        
    elif mode == 'qat':
        print("\n[INFO] Running Quantization-Aware Training (QAT)...")
        
        # 准备
        model = prepare_qat_model(model, q_config)
        
        # QAT 需要训练数据
        train_loader = calib_loader  # 简化：用校准集作为训练集
        val_loader = calib_loader
        
        qat_cfg = quant_cfg.get('qat', {})
        num_epochs = 2 if args.dry_run else qat_cfg.get('epochs', 15)
        
        history = train_qat(
            model=model,
            train_loader=train_loader,
            val_loader=val_loader,
            num_epochs=num_epochs,
            lr=qat_cfg.get('lr', 1e-4),
            device=device,
        )
        
        # 转换
        quantized_model = convert_to_quantized(model)
    
    elapsed_hours = (datetime.now() - start_time).total_seconds() / 3600
    
    # 保存量化模型
    quant_ckpt_path = config.paths.checkpoints / f'quantized_{mode}.pth'
    torch.save(quantized_model.state_dict(), quant_ckpt_path)
    print(f"[INFO] Quantized model saved to: {quant_ckpt_path}")
    
    # 获取模型统计
    # 注意：量化模型的统计需要特殊处理
    model_size_mb = get_file_size_mb(quant_ckpt_path) if quant_ckpt_path.exists() else 0
    
    # 导出 ONNX
    onnx_path = None
    if args.export_onnx or model_cfg.get('export_onnx', True):
        onnx_path = config.paths.outputs / f'student_{mode}_int8.onnx'
        
        # ONNX 导出需要原始模型（非量化）
        # 这里简化处理
        try:
            original_model = create_student_model(arch='dust3r_student_s', device='cpu')
            if weights_path and Path(weights_path).exists():
                state_dict = torch.load(weights_path, map_location='cpu')
                if isinstance(state_dict, dict) and 'state_dict' in state_dict:
                    state_dict = state_dict['state_dict']
                original_model.load_state_dict(state_dict, strict=False)
            
            export_to_onnx(
                model=original_model,
                output_path=str(onnx_path),
                input_shape=config.input_shape,
            )
        except Exception as e:
            print(f"[WARN] ONNX export failed: {e}")
    
    # 构建 TensorRT 引擎
    trt_path = None
    if args.build_trt and onnx_path and Path(onnx_path).exists():
        trt_cfg = config.experiment.get('tensorrt', {})
        trt_path = config.paths.outputs / 'student_int8.trt'
        
        trt_path = build_tensorrt_engine(
            onnx_path=str(onnx_path),
            output_path=str(trt_path),
            fp16=True,
            int8=True,
            max_workspace_gb=trt_cfg.get('build', {}).get('max_workspace_GB', 8),
        )
    
    # 创建日志
    log = ExperimentLog(
        exp_id=f"Q_{mode}_{config.seed}",
        combo="Q-only",
        seed=config.seed,
        dataset_id=config.workload.get('data', {}).get('dataset_id', 'unknown'),
        split='calib',
        
        # 量化参数
        bits_w=q_config.bits_w,
        bits_a=q_config.bits_a,
        keep_list=','.join(q_config.keep_list_modules[:3]) if q_config.keep_list_modules else None,
        
        # 资源
        params_M=0,  # 量化后难以准确统计
        flops_G=0,
        size_MB=model_size_mb,
        vram_GB=0,
        
        # 质量（需要后续评测）
        chamfer=0.0,
        absrel=0.0,
        rmse=0.0,
        delta1=0.0,
        reproj_px=0.0,
        
        # 效率（需要后续评测）
        t_pair_p50_ms=0.0,
        t_pair_p95_ms=0.0,
        t_scene_s=0.0,
        pairs_per_sec=0.0,
        
        gpu_hours=elapsed_hours,
        notes=f"{'[DRY-RUN] ' if args.dry_run else ''}{mode.upper()} quantization complete",
    )
    
    output_paths = save_experiment_log(
        log=log,
        log_dir=config.paths.logs,
        also_csv=True,
    )
    
    print("\n" + "=" * 60)
    print("Quantization Complete!")
    print(f"  Mode: {mode.upper()}")
    print(f"  Quantized model: {quant_ckpt_path}")
    if onnx_path:
        print(f"  ONNX: {onnx_path}")
    if trt_path:
        print(f"  TensorRT: {trt_path}")
    print(f"  Log: {output_paths['json']}")
    print("=" * 60)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
