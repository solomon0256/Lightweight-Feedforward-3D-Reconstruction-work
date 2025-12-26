"""
DUSt3R FLOPs 准确测量 v2
使用多种工具交叉验证
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'third_party', 'dust3r'))

import torch
import json
from datetime import datetime

def load_model(device='cpu'):
    """加载模型到 CPU 以避免显存问题"""
    from dust3r.model import AsymmetricCroCo3DStereo
    
    print("加载模型...")
    model = AsymmetricCroCo3DStereo.from_pretrained(
        'naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt',
        local_files_only=True
    )
    model = model.to(device)
    model.eval()
    print(f"✅ 模型加载成功 (device={device})")
    return model

def measure_with_thop(model, device='cpu'):
    """使用 thop 测量"""
    print("\n" + "=" * 60)
    print("方法1: thop")
    print("=" * 60)
    
    try:
        from thop import profile, clever_format
        
        # DUSt3R 输入格式
        H, W = 384, 512
        view1 = {'img': torch.randn(1, 3, H, W).to(device), 'true_shape': torch.tensor([[H, W]])}
        view2 = {'img': torch.randn(1, 3, H, W).to(device), 'true_shape': torch.tensor([[H, W]])}
        
        # thop 需要 tuple 输入
        macs, params = profile(model, inputs=(view1, view2), verbose=False)
        
        flops = macs * 2  # MACs to FLOPs
        macs_str, params_str = clever_format([macs, params], "%.2f")
        flops_str = clever_format([flops], "%.2f")[0]
        
        print(f"MACs: {macs_str}")
        print(f"FLOPs: {flops_str}")
        print(f"Params: {params_str}")
        
        return {'macs': macs, 'flops': flops, 'params': params}
    except Exception as e:
        print(f"❌ thop 失败: {e}")
        return None

def measure_with_calflops(model, device='cpu'):
    """使用 calflops 测量"""
    print("\n" + "=" * 60)
    print("方法2: calflops")
    print("=" * 60)
    
    try:
        from calflops import calculate_flops
        
        H, W = 384, 512
        
        # calflops 需要特殊处理 dict 输入
        # 创建 wrapper
        class ModelWrapper(torch.nn.Module):
            def __init__(self, model):
                super().__init__()
                self.model = model
                self.H, self.W = 384, 512
            
            def forward(self, img1, img2):
                view1 = {'img': img1, 'true_shape': torch.tensor([[self.H, self.W]])}
                view2 = {'img': img2, 'true_shape': torch.tensor([[self.H, self.W]])}
                return self.model(view1, view2)
        
        wrapper = ModelWrapper(model).to(device)
        
        flops, macs, params = calculate_flops(
            model=wrapper,
            input_shape=(1, 3, H, W),
            args=[torch.randn(1, 3, H, W).to(device), torch.randn(1, 3, H, W).to(device)],
            output_as_string=False,
            print_results=False
        )
        
        print(f"FLOPs: {flops / 1e9:.2f}G")
        print(f"MACs: {macs / 1e9:.2f}G")
        print(f"Params: {params / 1e6:.2f}M")
        
        return {'flops': flops, 'macs': macs, 'params': params}
    except Exception as e:
        print(f"❌ calflops 失败: {e}")
        return None

def measure_encoder_only(model, device='cpu'):
    """单独测量 encoder 的 FLOPs"""
    print("\n" + "=" * 60)
    print("方法3: 分模块测量 (encoder)")
    print("=" * 60)
    
    try:
        from thop import profile
        
        H, W = 384, 512
        x = torch.randn(1, 3, H, W).to(device)
        
        # 只测 patch_embed
        patch_embed = model.patch_embed
        macs_patch, _ = profile(patch_embed, inputs=(x,), verbose=False)
        print(f"patch_embed MACs: {macs_patch / 1e9:.4f}G")
        
        # 测单个 encoder block
        # 先获取 patch_embed 输出
        with torch.no_grad():
            tokens = patch_embed(x)  # [1, num_patches, embed_dim]
        
        enc_block = model.enc_blocks[0]
        
        # 创建 position encoding
        pos = model.rope.get_cos_sin(W // 16, H // 16, x.device, x.dtype)
        
        # 测量单个 block
        class BlockWrapper(torch.nn.Module):
            def __init__(self, block, pos):
                super().__init__()
                self.block = block
                self.pos = pos
            def forward(self, x):
                return self.block(x, self.pos)
        
        wrapper = BlockWrapper(enc_block, pos).to(device)
        macs_block, _ = profile(wrapper, inputs=(tokens,), verbose=False)
        print(f"单个 enc_block MACs: {macs_block / 1e9:.4f}G")
        
        # 估算总 encoder FLOPs
        num_enc_blocks = len(model.enc_blocks)
        encoder_macs = macs_patch * 2 + macs_block * num_enc_blocks * 2  # 两个视图
        print(f"\nEncoder 估算:")
        print(f"  num_enc_blocks: {num_enc_blocks}")
        print(f"  Encoder MACs (2 views): {encoder_macs / 1e9:.2f}G")
        print(f"  Encoder FLOPs (2 views): {encoder_macs * 2 / 1e9:.2f}G")
        
        return {'encoder_macs': encoder_macs, 'encoder_flops': encoder_macs * 2}
    except Exception as e:
        print(f"❌ 分模块测量失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def manual_calculation():
    """手动计算 FLOPs（基于 Transformer 公式）"""
    print("\n" + "=" * 60)
    print("方法4: 手动公式计算")
    print("=" * 60)
    
    # DUSt3R-512 参数
    H, W = 384, 512
    P = 16  # patch size
    N = (H // P) * (W // P)  # 768 patches per view
    D = 1024  # ViT-Large embed dim
    L_enc = 24  # encoder layers
    L_dec = 12  # decoder layers (每个 decoder)
    D_dec = 768  # decoder embed dim (估计)
    
    print(f"输入: {H}×{W}, Patch: {P}×{P}")
    print(f"Tokens per view: N = {N}")
    print(f"Encoder: D={D}, L={L_enc}")
    print(f"Decoder: D={D_dec}, L={L_dec}")
    
    # ===== Encoder =====
    # Patch Embed: Conv2D
    # FLOPs = 2 * Cin * Cout * Kh * Kw * Hout * Wout
    patch_embed_flops = 2 * 3 * D * P * P * (H // P) * (W // P)
    patch_embed_total = patch_embed_flops * 2  # 两个视图
    
    # Self-Attention per layer: 
    # Q,K,V projection: 3 * 2*N*D*D
    # Attention scores: 2*N*N*D
    # Attention @ V: 2*N*N*D
    # Output projection: 2*N*D*D
    attn_qkv = 3 * 2 * N * D * D
    attn_scores = 2 * N * N * D
    attn_context = 2 * N * N * D
    attn_out = 2 * N * D * D
    self_attn_flops = attn_qkv + attn_scores + attn_context + attn_out
    
    # MLP per layer: 2 * N * D * 4D + 2 * N * 4D * D = 16*N*D*D
    mlp_flops = 16 * N * D * D
    
    # LayerNorm: 忽略（相对较小）
    
    encoder_layer_flops = self_attn_flops + mlp_flops
    encoder_total = encoder_layer_flops * L_enc * 2  # 两个视图
    
    print(f"\n----- Encoder -----")
    print(f"Patch Embed: {patch_embed_total / 1e9:.3f}G FLOPs")
    print(f"Self-Attn per layer: {self_attn_flops / 1e9:.3f}G FLOPs")
    print(f"MLP per layer: {mlp_flops / 1e9:.3f}G FLOPs")
    print(f"Encoder Total (2 views): {(encoder_total + patch_embed_total) / 1e9:.2f}G FLOPs")
    
    # ===== Cross-Attention (后12层) =====
    # DUSt3R 在后12层加入 cross-attention
    cross_attn_layers = 12
    # Cross attention: Q from view1, K,V from view2
    cross_attn_flops = attn_qkv + attn_scores + attn_context + attn_out  # 类似 self-attn
    cross_total = cross_attn_flops * cross_attn_layers * 2  # 双向
    
    print(f"\n----- Cross-Attention -----")
    print(f"Cross-Attn layers: {cross_attn_layers}")
    print(f"Cross-Attn Total: {cross_total / 1e9:.2f}G FLOPs")
    
    # ===== Decoder =====
    # 两个 decoder，每个12层
    # Decoder 用 D_dec=768
    N_dec = N  # 同样的 token 数
    
    dec_self_attn = 4 * 2 * N_dec * D_dec * D_dec + 4 * N_dec * N_dec * D_dec
    dec_cross_attn = dec_self_attn  # cross-attn with encoder output
    dec_mlp = 16 * N_dec * D_dec * D_dec
    
    decoder_layer_flops = dec_self_attn + dec_cross_attn + dec_mlp
    decoder_total = decoder_layer_flops * L_dec * 2 * 2  # 2 decoders, 2 views
    
    print(f"\n----- Decoder -----")
    print(f"Decoder layer FLOPs: {decoder_layer_flops / 1e9:.3f}G")
    print(f"Decoder Total (2 decoders, 2 views): {decoder_total / 1e9:.2f}G FLOPs")
    
    # ===== DPT Head =====
    # 粗略估计
    head_flops = N * D_dec * 256 * 2 * 2  # 简化估计
    head_total = head_flops * 2  # 两个 head
    
    print(f"\n----- Head -----")
    print(f"Head Total: {head_total / 1e9:.2f}G FLOPs")
    
    # ===== 总计 =====
    total_flops = patch_embed_total + encoder_total + cross_total + decoder_total + head_total
    
    print(f"\n" + "=" * 40)
    print(f"总计: {total_flops / 1e9:.2f}G FLOPs")
    print(f"MACs: {total_flops / 2 / 1e9:.2f}G")
    print(f"=" * 40)
    print(f"\n论文值: ~430G FLOPs")
    print(f"差异: {total_flops / 1e9 / 430:.2f}x")
    
    return total_flops

def main():
    print("=" * 60)
    print("DUSt3R FLOPs 准确测量 v2")
    print(f"时间: {datetime.now().isoformat()}")
    print("=" * 60)
    
    results = {}
    
    # 用 CPU 避免显存问题
    device = 'cpu'
    print(f"Device: {device} (避免显存限制)")
    
    model = load_model(device)
    
    # 方法1: thop
    thop_result = measure_with_thop(model, device)
    if thop_result:
        results['thop'] = thop_result
    
    # 方法2: calflops
    calflops_result = measure_with_calflops(model, device)
    if calflops_result:
        results['calflops'] = calflops_result
    
    # 方法3: 分模块
    encoder_result = measure_encoder_only(model, device)
    if encoder_result:
        results['encoder_only'] = encoder_result
    
    # 方法4: 手动计算
    manual_flops = manual_calculation()
    results['manual'] = {'flops': manual_flops}
    
    # 汇总
    print("\n" + "=" * 60)
    print("📊 测量结果汇总")
    print("=" * 60)
    
    for method, res in results.items():
        if res and 'flops' in res:
            print(f"{method}: {res['flops'] / 1e9:.2f}G FLOPs")
    
    print(f"\n论文值: ~430G FLOPs")
    
    # 保存
    output_path = os.path.join(os.path.dirname(__file__), '..', 'logs', 'flops_measurement_v2.json')
    with open(output_path, 'w') as f:
        # 转换为可序列化格式
        serializable = {}
        for k, v in results.items():
            if v:
                serializable[k] = {kk: float(vv) if isinstance(vv, (int, float)) else vv for kk, vv in v.items()}
        json.dump(serializable, f, indent=2)
    print(f"\n✅ 结果已保存到: {output_path}")

if __name__ == '__main__':
    main()
