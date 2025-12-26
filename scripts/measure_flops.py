#!/usr/bin/env python3
"""
DUSt3R FLOPs 测量脚本

用途: 测量 DUSt3R 模型的 FLOPs、MACs、参数量分布
论文值: DUSt3R-512 ~430G FLOPs, 571M params

使用方法:
    python scripts/measure_flops.py
"""

import sys
import os

# 添加 dust3r 路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
dust3r_path = os.path.join(project_root, 'third_party', 'dust3r')
sys.path.insert(0, dust3r_path)
sys.path.insert(0, project_root)

import torch
import json
from datetime import datetime

def check_fvcore():
    """检查并安装 fvcore"""
    try:
        from fvcore.nn import FlopCountAnalysis, parameter_count_table
        return True
    except ImportError:
        print("❌ fvcore 未安装，正在安装...")
        os.system("pip install fvcore")
        return False

def load_model(device='cuda'):
    """加载 DUSt3R 模型"""
    print("=" * 60)
    print("Step 1: 加载模型")
    print("=" * 60)
    
    from dust3r.model import AsymmetricCroCo3DStereo
    
    model = AsymmetricCroCo3DStereo.from_pretrained(
        'naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt',
        local_files_only=True  # 从本地缓存加载，避免网络问题
    )
    model = model.to(device)
    model.eval()
    
    print(f"✅ 模型加载成功")
    return model

def count_parameters(model):
    """统计参数量分布"""
    print("\n" + "=" * 60)
    print("Step 2: 统计参数量")
    print("=" * 60)
    
    # 总参数量
    params_total = sum(p.numel() for p in model.parameters())
    params_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    
    print(f"params_total: {params_total:,} ({params_total / 1e6:.2f}M)")
    print(f"params_trainable: {params_trainable:,} ({params_trainable / 1e6:.2f}M)")
    
    # 分模块统计
    module_params = {}
    for name, module in model.named_children():
        params = sum(p.numel() for p in module.parameters())
        module_params[name] = params
        print(f"  {name}: {params:,} ({params / 1e6:.2f}M)")
    
    # 尝试分拆 encoder / decoder
    encoder_keys = ['patch_embed', 'enc_blocks', 'enc_norm']
    decoder_keys = ['dec_blocks', 'dec_blocks2', 'dec_norm', 'head']
    
    params_encoder = sum(module_params.get(k, 0) for k in encoder_keys)
    params_decoder = sum(module_params.get(k, 0) for k in decoder_keys)
    params_other = params_total - params_encoder - params_decoder
    
    print(f"\n分拆统计:")
    print(f"  params_encoder: {params_encoder:,} ({params_encoder / 1e6:.2f}M)")
    print(f"  params_decoder: {params_decoder:,} ({params_decoder / 1e6:.2f}M)")
    print(f"  params_other: {params_other:,} ({params_other / 1e6:.2f}M)")
    
    return {
        'params_total': params_total,
        'params_trainable': params_trainable,
        'params_encoder': params_encoder,
        'params_decoder': params_decoder,
        'params_other': params_other,
        'module_params': module_params
    }

def measure_flops_fvcore(model, device='cuda'):
    """使用 fvcore 测量 FLOPs"""
    print("\n" + "=" * 60)
    print("Step 3: 测量 FLOPs (fvcore)")
    print("=" * 60)
    
    from fvcore.nn import FlopCountAnalysis, flop_count_table
    
    # DUSt3R 输入格式: [B, 3, H, W] 其中 H=384, W=512
    # 模型需要两个视图作为输入
    H, W = 384, 512
    
    # 创建 dummy 输入 - DUSt3R forward 需要特定格式
    # 查看 DUSt3R 的 forward 签名
    print(f"输入尺寸: [1, 3, {H}, {W}] × 2 views")
    
    # 方法1: 直接用 forward 的输入格式
    # DUSt3R forward(self, view1, view2) 其中 view 是 dict
    view1 = {
        'img': torch.randn(1, 3, H, W, device=device),
        'true_shape': torch.tensor([[H, W]], device=device),
        'idx': 0,
        'instance': '0'
    }
    view2 = {
        'img': torch.randn(1, 3, H, W, device=device),
        'true_shape': torch.tensor([[H, W]], device=device),
        'idx': 1,
        'instance': '1'
    }
    
    try:
        # 尝试直接计算
        print("尝试方法1: FlopCountAnalysis(model, (view1, view2))...")
        flop_counter = FlopCountAnalysis(model, (view1, view2))
        flops = flop_counter.total()
        print(f"✅ FLOPs: {flops:,} ({flops / 1e9:.2f}G)")
        return flops
    except Exception as e:
        print(f"方法1失败: {e}")
    
    # 方法2: 只计算 encoder 部分
    try:
        print("\n尝试方法2: 分别计算 encoder...")
        img = torch.randn(1, 3, H, W, device=device)
        
        # 获取 patch_embed 的 FLOPs
        if hasattr(model, 'patch_embed'):
            flop_counter = FlopCountAnalysis(model.patch_embed, (img,))
            flops_patch = flop_counter.total()
            print(f"  patch_embed FLOPs: {flops_patch / 1e9:.2f}G")
        
        return None
    except Exception as e:
        print(f"方法2失败: {e}")
    
    return None

def measure_flops_thop(model, device='cuda'):
    """使用 thop 测量 FLOPs (备用方法)"""
    print("\n" + "=" * 60)
    print("Step 3b: 测量 FLOPs (thop - 备用)")
    print("=" * 60)
    
    try:
        from thop import profile, clever_format
    except ImportError:
        print("thop 未安装，跳过")
        return None
    
    H, W = 384, 512
    
    view1 = {
        'img': torch.randn(1, 3, H, W, device=device),
        'true_shape': torch.tensor([[H, W]], device=device),
        'idx': 0,
        'instance': '0'
    }
    view2 = {
        'img': torch.randn(1, 3, H, W, device=device),
        'true_shape': torch.tensor([[H, W]], device=device),
        'idx': 1,
        'instance': '1'
    }
    
    try:
        macs, params = profile(model, inputs=(view1, view2), verbose=False)
        flops = macs * 2  # MACs to FLOPs
        macs_str, params_str = clever_format([macs, params], "%.2f")
        print(f"✅ MACs: {macs_str}, Params: {params_str}")
        print(f"✅ FLOPs: {flops / 1e9:.2f}G")
        return flops
    except Exception as e:
        print(f"thop 测量失败: {e}")
        return None

def measure_flops_manual(model, device='cuda'):
    """手动估算 FLOPs"""
    print("\n" + "=" * 60)
    print("Step 3c: 手动估算 FLOPs")
    print("=" * 60)
    
    H, W = 384, 512
    patch_size = 16  # ViT patch size
    num_patches = (H // patch_size) * (W // patch_size)  # 24 * 32 = 768
    
    print(f"输入尺寸: H={H}, W={W}")
    print(f"Patch size: {patch_size}")
    print(f"Num patches per view: {num_patches}")
    
    # ViT-Large 参数
    embed_dim = 1024  # ViT-Large
    num_heads = 16
    mlp_ratio = 4
    num_encoder_layers = 24  # ViT-Large
    num_decoder_layers = 12  # DUSt3R decoder
    
    # DUSt3R 架构说明：
    # - Encoder: 分别处理两个视图，然后 cross-attention
    # - Decoder: 两个 decoder head
    
    # 单视图 encoder FLOPs (per layer)
    seq_len = num_patches  # 768 tokens per view
    
    # Self-Attention: 4*seq*d^2 + 2*seq^2*d
    attn_flops = 4 * seq_len * embed_dim**2 + 2 * seq_len**2 * embed_dim
    # MLP: 8*seq*d^2 (两层: d->4d->d)
    mlp_flops = 8 * seq_len * embed_dim**2
    encoder_layer_flops = attn_flops + mlp_flops
    
    # 两个视图的 encoder = 2 * single_view
    encoder_total_flops = encoder_layer_flops * num_encoder_layers * 2
    
    # Cross-attention in encoder (后几层)
    cross_attn_layers = 12  # 估计后12层有 cross-attention
    cross_seq_len = num_patches * 2  # cross-attention 看两个视图
    cross_attn_flops = 4 * cross_seq_len * embed_dim**2 + 2 * cross_seq_len**2 * embed_dim
    cross_total_flops = cross_attn_flops * cross_attn_layers
    
    # Decoder FLOPs (两个 decoder)
    decoder_embed_dim = 768  # decoder 可能用更小的维度
    decoder_layer_flops = (4 * seq_len * decoder_embed_dim**2 + 
                           2 * seq_len**2 * decoder_embed_dim + 
                           8 * seq_len * decoder_embed_dim**2)
    decoder_total_flops = decoder_layer_flops * num_decoder_layers * 2 * 2  # 2 decoders, 2 views
    
    # Patch embed FLOPs: Conv2D
    patch_embed_flops = 2 * (3 * patch_size**2 * embed_dim * num_patches * 2)
    
    # DPT Head FLOPs (粗略估计)
    head_flops = num_patches * 4 * embed_dim * 3 * 2  # 两个 head
    
    total_flops = encoder_total_flops + cross_total_flops + decoder_total_flops + patch_embed_flops + head_flops
    
    print(f"\n估算结果 (修正版):")
    print(f"  Encoder (2 views): {encoder_total_flops / 1e9:.2f}G FLOPs")
    print(f"  Cross-Attention: {cross_total_flops / 1e9:.2f}G FLOPs")
    print(f"  Decoder (2 decoders): {decoder_total_flops / 1e9:.2f}G FLOPs")
    print(f"  Patch Embed: {patch_embed_flops / 1e9:.2f}G FLOPs")
    print(f"  Head: {head_flops / 1e9:.2f}G FLOPs")
    print(f"  ----------------------------------------")
    print(f"  Total (估算): {total_flops / 1e9:.2f}G FLOPs")
    print(f"\n论文值: ~430G FLOPs")
    
    # 根据参数量比例校正
    # 论文 571M params -> 430G FLOPs
    # 比例: 430 / 571 ≈ 0.75 GFLOPs/M
    flops_by_ratio = 571.17 * 0.75
    print(f"\n按参数量比例估算: {flops_by_ratio:.0f}G FLOPs")
    
    return total_flops

def save_results(results, output_path):
    """保存结果到 JSON"""
    print("\n" + "=" * 60)
    print("Step 4: 保存结果")
    print("=" * 60)
    
    # 转换 module_params 中的值为 Python int
    if 'params' in results and 'module_params' in results['params']:
        results['params']['module_params'] = {
            k: int(v) for k, v in results['params']['module_params'].items()
        }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"✅ 结果已保存到: {output_path}")

def main():
    print("=" * 60)
    print("DUSt3R FLOPs 测量")
    print(f"时间: {datetime.now().isoformat()}")
    print("=" * 60)
    
    # 检查 fvcore
    check_fvcore()
    
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Device: {device}")
    
    # 加载模型
    model = load_model(device)
    
    results = {
        'datetime': datetime.now().isoformat(),
        'device': device,
        'input_resolution': '512x384',
        'paper_flops': '~430G'
    }
    
    # 统计参数
    params_info = count_parameters(model)
    results['params'] = {
        'params_total': int(params_info['params_total']),
        'params_total_M': round(params_info['params_total'] / 1e6, 2),
        'params_encoder': int(params_info['params_encoder']),
        'params_encoder_M': round(params_info['params_encoder'] / 1e6, 2),
        'params_decoder': int(params_info['params_decoder']),
        'params_decoder_M': round(params_info['params_decoder'] / 1e6, 2),
    }
    
    # 测量 FLOPs
    flops = measure_flops_fvcore(model, device)
    if flops is None:
        flops = measure_flops_thop(model, device)
    
    # 手动估算
    flops_manual = measure_flops_manual(model, device)
    
    results['flops'] = {
        'flops_measured': flops / 1e9 if flops else None,
        'flops_estimated': round(flops_manual / 1e9, 2),
        'macs_estimated': round(flops_manual / 2 / 1e9, 2),
        'paper_value': '~430G'
    }
    
    # 汇总
    print("\n" + "=" * 60)
    print("📊 测量结果汇总")
    print("=" * 60)
    print(f"params_total: {results['params']['params_total_M']}M (论文: 571M)")
    print(f"params_encoder: {results['params']['params_encoder_M']}M")
    print(f"params_decoder: {results['params']['params_decoder_M']}M")
    print(f"FLOPs (估算): {results['flops']['flops_estimated']}G (论文: ~430G)")
    print(f"MACs (估算): {results['flops']['macs_estimated']}G")
    
    # 保存结果
    output_path = os.path.join(
        os.path.dirname(__file__), '..', 'logs', 'flops_measurement.json'
    )
    save_results(results, output_path)
    
    return results

if __name__ == '__main__':
    main()
