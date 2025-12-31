#!/usr/bin/env python3
"""测试所有Student scale配置"""

import torch
import sys
from pathlib import Path

# 添加路径
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.models import DUSt3RStudent, StudentConfig

def test_scale(scale: str):
    """测试指定scale的配置"""
    print(f"\n=== Testing {scale.upper()} scale ===")
    
    # 创建配置
    config = StudentConfig.from_scale(scale)
    
    # 检查head_dim
    enc_head_dim = config.encoder_dim // config.encoder_heads
    dec_head_dim = config.decoder_dim // config.decoder_heads
    
    print(f"Encoder: {config.encoder_dim}/{config.encoder_heads} = {enc_head_dim} per head")
    print(f"Decoder: {config.decoder_dim}/{config.decoder_heads} = {dec_head_dim} per head")
    print(f"  RoPE constraint: head_dim/2 >= 32")
    print(f"  Encoder: {enc_head_dim}/2 = {enc_head_dim//2} {'✓' if enc_head_dim//2 >= 32 else '✗'}")
    print(f"  Decoder: {dec_head_dim}/2 = {dec_head_dim//2} {'✓' if dec_head_dim//2 >= 32 else '✗'}")
    
    # 创建模型
    model = DUSt3RStudent(config=config)
    
    # 测试前向传播
    view1 = {'img': torch.randn(1, 3, 512, 384)}
    view2 = {'img': torch.randn(1, 3, 512, 384)}
    
    with torch.no_grad():
        out1, out2 = model(view1, view2)
    
    # 统计参数
    params = sum(p.numel() for p in model.parameters()) / 1e6
    
    print(f"\n✓ Forward pass successful!")
    print(f"  Output shapes: pts3d={out1['pts3d'].shape}, conf={out1['conf'].shape}")
    print(f"  Total params: {params:.2f}M")
    
    return True

if __name__ == '__main__':
    print("=" * 60)
    print("Testing all Student scale configurations")
    print("=" * 60)
    
    for scale in ['s', 'm', 'l']:
        try:
            test_scale(scale)
        except Exception as e:
            print(f"\n✗ {scale.upper()} scale failed: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)

