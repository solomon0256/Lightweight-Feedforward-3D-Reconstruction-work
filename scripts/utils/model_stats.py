"""
模型统计工具 - 计算参数量、FLOPs、模型体积、显存占用
"""
import os
import torch
import torch.nn as nn
from pathlib import Path
from typing import Tuple, Optional, Union, Dict, Any
from dataclasses import dataclass


@dataclass
class ModelStats:
    """模型统计结果"""
    params_M: float      # 参数量（百万）
    params_trainable_M: float  # 可训练参数量（百万）
    flops_G: float       # FLOPs（GFLOPs）
    size_MB: float       # 模型体积（MB）
    vram_GB: float       # 显存占用（GB）
    
    def __str__(self) -> str:
        return (
            f"Params: {self.params_M:.2f}M (trainable: {self.params_trainable_M:.2f}M), "
            f"FLOPs: {self.flops_G:.2f}G, Size: {self.size_MB:.2f}MB, VRAM: {self.vram_GB:.2f}GB"
        )
    
    def to_dict(self) -> Dict[str, float]:
        return {
            'params_M': self.params_M,
            'params_trainable_M': self.params_trainable_M,
            'flops_G': self.flops_G,
            'size_MB': self.size_MB,
            'vram_GB': self.vram_GB,
        }


def count_parameters(model: nn.Module) -> Tuple[int, int]:
    """
    统计模型参数量
    
    Returns:
        (total_params, trainable_params)
    """
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return total, trainable


def estimate_model_size(model: nn.Module, include_buffers: bool = True) -> float:
    """
    估算模型体积（MB）
    
    Args:
        model: PyTorch 模型
        include_buffers: 是否包含 buffers
    
    Returns:
        体积（MB）
    """
    param_size = sum(p.numel() * p.element_size() for p in model.parameters())
    
    buffer_size = 0
    if include_buffers:
        buffer_size = sum(b.numel() * b.element_size() for b in model.buffers())
    
    return (param_size + buffer_size) / (1024 * 1024)


def get_file_size_mb(path: Union[str, Path]) -> float:
    """获取文件大小（MB）"""
    return os.path.getsize(path) / (1024 * 1024)


def measure_vram(model: nn.Module, input_shape: Tuple[int, ...], device: str = 'cuda') -> float:
    """
    测量模型推理时的显存占用
    
    Args:
        model: PyTorch 模型
        input_shape: 输入形状 (B, C, H, W)
        device: 设备
    
    Returns:
        显存占用（GB）
    """
    if device != 'cuda' or not torch.cuda.is_available():
        return 0.0
    
    model = model.to(device)
    model.eval()
    
    # 清空缓存
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    
    # 运行一次推理
    dummy_input = torch.randn(*input_shape, device=device)
    with torch.no_grad():
        _ = model(dummy_input)
    
    # 获取峰值显存
    peak_memory = torch.cuda.max_memory_allocated() / (1024 ** 3)  # GB
    
    # 清理
    del dummy_input
    torch.cuda.empty_cache()
    
    return peak_memory


def estimate_flops(
    model: nn.Module,
    input_shape: Tuple[int, ...],
    device: str = 'cpu'
) -> float:
    """
    估算模型 FLOPs
    
    使用 fvcore 或 thop 库（如果可用），否则返回粗略估计
    
    Args:
        model: PyTorch 模型
        input_shape: 输入形状 (B, C, H, W)
        device: 设备
    
    Returns:
        FLOPs（GFLOPs）
    """
    # 尝试使用 fvcore
    try:
        from fvcore.nn import FlopCountAnalysis
        model = model.to(device)
        model.eval()
        dummy_input = torch.randn(*input_shape, device=device)
        flops = FlopCountAnalysis(model, dummy_input).total()
        return flops / 1e9  # GFLOPs
    except ImportError:
        pass
    
    # 尝试使用 thop
    try:
        from thop import profile
        model = model.to(device)
        model.eval()
        dummy_input = torch.randn(*input_shape, device=device)
        flops, _ = profile(model, inputs=(dummy_input,), verbose=False)
        return flops / 1e9  # GFLOPs
    except ImportError:
        pass
    
    # 粗略估计：基于参数量
    # 假设每个参数在前向传播中参与 2 次运算
    total_params, _ = count_parameters(model)
    batch_size = input_shape[0]
    estimated_flops = total_params * 2 * batch_size
    
    print("Warning: Using rough FLOPs estimation. Install 'fvcore' or 'thop' for accurate results.")
    return estimated_flops / 1e9


def get_model_stats(
    model: nn.Module,
    input_shape: Tuple[int, ...] = (1, 3, 512, 384),
    device: str = 'cuda',
    measure_vram_flag: bool = True,
) -> ModelStats:
    """
    获取完整的模型统计信息
    
    Args:
        model: PyTorch 模型
        input_shape: 输入形状
        device: 设备
        measure_vram_flag: 是否测量显存（需要 CUDA）
    
    Returns:
        ModelStats
    """
    total_params, trainable_params = count_parameters(model)
    size_mb = estimate_model_size(model)
    flops_g = estimate_flops(model, input_shape, device='cpu')  # FLOPs 在 CPU 上计算
    
    vram_gb = 0.0
    if measure_vram_flag and device == 'cuda' and torch.cuda.is_available():
        vram_gb = measure_vram(model, input_shape, device)
    
    return ModelStats(
        params_M=total_params / 1e6,
        params_trainable_M=trainable_params / 1e6,
        flops_G=flops_g,
        size_MB=size_mb,
        vram_GB=vram_gb,
    )


def compare_models(
    model_a: nn.Module,
    model_b: nn.Module,
    input_shape: Tuple[int, ...] = (1, 3, 512, 384),
    names: Tuple[str, str] = ('Model A', 'Model B'),
) -> Dict[str, Any]:
    """
    比较两个模型的统计信息
    
    Returns:
        比较结果字典
    """
    stats_a = get_model_stats(model_a, input_shape, measure_vram_flag=False)
    stats_b = get_model_stats(model_b, input_shape, measure_vram_flag=False)
    
    def pct_change(a, b):
        if a == 0:
            return 0
        return (b - a) / a * 100
    
    return {
        names[0]: stats_a.to_dict(),
        names[1]: stats_b.to_dict(),
        'comparison': {
            'params_change_pct': pct_change(stats_a.params_M, stats_b.params_M),
            'flops_change_pct': pct_change(stats_a.flops_G, stats_b.flops_G),
            'size_change_pct': pct_change(stats_a.size_MB, stats_b.size_MB),
        }
    }


def print_model_summary(model: nn.Module, input_shape: Tuple[int, ...] = (1, 3, 512, 384)):
    """打印模型摘要"""
    stats = get_model_stats(model, input_shape, measure_vram_flag=False)
    
    print("=" * 50)
    print("Model Summary")
    print("=" * 50)
    print(f"  Parameters:     {stats.params_M:.2f}M")
    print(f"  Trainable:      {stats.params_trainable_M:.2f}M")
    print(f"  FLOPs:          {stats.flops_G:.2f}G")
    print(f"  Size:           {stats.size_MB:.2f}MB")
    print("=" * 50)


# ============ 测试 ============

if __name__ == '__main__':
    # 创建一个简单模型测试
    class SimpleModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = nn.Conv2d(3, 64, 3, padding=1)
            self.conv2 = nn.Conv2d(64, 128, 3, padding=1)
            self.fc = nn.Linear(128 * 512 * 384, 1000)
        
        def forward(self, x):
            x = torch.relu(self.conv1(x))
            x = torch.relu(self.conv2(x))
            x = x.view(x.size(0), -1)
            x = self.fc(x)
            return x
    
    model = SimpleModel()
    print_model_summary(model, input_shape=(1, 3, 512, 384))
