"""
DUSt3R FLOPs 基于 ViT-Large 已知数据推算 v4
"""
import sys
import os

print("=" * 60)
print("DUSt3R FLOPs 推算 (基于 ViT 已知数据)")
print("=" * 60)

# ============================================================
# 已知数据 (来自 timm 和 PyTorch 官方)
# ============================================================
print("""
📊 已知参考数据 (来自 timm/PyTorch):

| Model | Input | Params | GMACs | GFLOPs |
|-------|-------|--------|-------|--------|
| ViT-B/16 | 224×224 | 86M | 8.5G | 17.0G |
| ViT-L/16 | 224×224 | 304M | 30.9G | 61.8G |
| ViT-H/14 | 224×224 | 632M | 65.0G | 130.0G |

来源: https://github.com/huggingface/pytorch-image-models
""")

# ============================================================
# DUSt3R 架构分析
# ============================================================
print("""
🔍 DUSt3R 架构分析:

DUSt3R = CroCo encoder + DPT decoder

Encoder (ViT-Large):
- embed_dim: 1024
- num_heads: 16  
- depth: 24 layers
- 参数量: ~303M (已测)

Decoder (ViT-Base 级别):
- embed_dim: 768
- depth: 12 layers × 2 (两个 decoder)
- 参数量: ~227M (已测)

Heads (DPT):
- 参数量: ~40M (已测)
""")

# ============================================================
# FLOPs 推算
# ============================================================
print("""
📐 FLOPs 推算:

1. ViT-Large @ 224×224:
   - tokens = 14×14 = 196
   - GMACs = 30.9G
   - GFLOPs = 61.8G

2. DUSt3R @ 512×384:
   - tokens = 32×24 = 768
   - token 数比例 = 768/196 = 3.92x

3. Transformer FLOPs 与 token 数的关系:
   - Attention: O(N²) 
   - MLP: O(N)
   - 实际上约 O(N^1.5) 到 O(N^2)
   
   对于 ViT，主要是:
   - Linear projections (Q,K,V,O): O(N)
   - Attention matrix: O(N²)
   
   当 N 变 3.92x，FLOPs 大约变:
   - Linear 部分: 3.92x
   - Attention 部分: 3.92² = 15.4x
   - 加权估计: ~10x (取决于具体比例)
""")

# 计算
import math

# 参考值
vit_large_224_gflops = 61.8
tokens_224 = 14 * 14  # 196
tokens_512_384 = 32 * 24  # 768

token_ratio = tokens_512_384 / tokens_224
print(f"Token 比例: {token_ratio:.2f}x")

# 更精确的估算
# Attention FLOPs: 4*N*D² + 2*N²*D (占主要部分)
# MLP FLOPs: 8*N*D²
# 
# 对于 ViT-Large (D=1024):
# 单 layer:
#   attn: 4*N*1024² + 2*N²*1024 = 4.2M*N + 2048*N²
#   mlp: 8*N*1024² = 8.4M*N
#   total: 12.6M*N + 2048*N²
#
# N=196: 12.6M*196 + 2048*196² = 2.47G + 78.6M = 2.55G per layer
# N=768: 12.6M*768 + 2048*768² = 9.68G + 1.21G = 10.89G per layer
# 比例: 10.89/2.55 = 4.27x

flops_ratio = (12.6e6 * 768 + 2048 * 768**2) / (12.6e6 * 196 + 2048 * 196**2)
print(f"FLOPs 比例 (基于公式): {flops_ratio:.2f}x")

# 单 ViT-Large encoder @ 512×384
single_encoder_gflops = vit_large_224_gflops * flops_ratio
print(f"\n单 ViT-Large encoder @ 512×384: {single_encoder_gflops:.1f} GFLOPs")

# DUSt3R 完整估算
print("""
🧮 DUSt3R 完整 FLOPs 估算:
""")

encoder_gflops = single_encoder_gflops * 2  # 两个视图
print(f"  Encoder (2 views): {encoder_gflops:.1f}G")

# Cross-attention (后12层)
# 类似一个 encoder layer，但 K,V 来自另一个视图
cross_attn_gflops = single_encoder_gflops * 12 / 24  # 约一半 encoder
print(f"  Cross-attention (12 layers): {cross_attn_gflops:.1f}G")

# Decoder (ViT-Base 级别, 两个)
# ViT-Base @ 224: 17G FLOPs, 12 layers
# @ 512×384: 17 * 4.27 = 72.6G
# 两个 decoder: 72.6 * 2 = 145G
decoder_single_gflops = 17.0 * flops_ratio
decoder_total_gflops = decoder_single_gflops * 2
print(f"  Decoder (2 heads): {decoder_total_gflops:.1f}G")

# DPT head (相对较小)
head_gflops = 10.0  # 估计
print(f"  DPT Head: {head_gflops:.1f}G")

total_gflops = encoder_gflops + cross_attn_gflops + decoder_total_gflops + head_gflops
print(f"\n  {'=' * 30}")
print(f"  总计: {total_gflops:.0f}G FLOPs")
print(f"  MACs: {total_gflops / 2:.0f}G")

print("""
📋 结论:

基于 ViT-Large 已知 FLOPs 推算，DUSt3R-512 约:
""")
print(f"   {total_gflops:.0f}G FLOPs (或 {total_gflops/2:.0f}G MACs)")

print("""
⚠️ 之前文档中的 "~430G" 可能来源于:
1. 只计算了 encoder (不含 decoder/head)
2. 或者用了不同的计算口径
3. 或者是某篇论文的引用

建议: 
- 在文档中标注 FLOPs 为 "待精确测量"
- 或使用区间: 400-700G FLOPs
- 需要在更大显存机器上用 profiler 精确测量
""")

# 保存结果
results = {
    "datetime": "2025-12-25",
    "method": "基于 ViT-Large 已知数据推算",
    "reference": {
        "ViT-Large @ 224×224": {
            "tokens": 196,
            "GFLOPs": 61.8,
            "source": "timm/pytorch-image-models"
        }
    },
    "estimation": {
        "token_ratio": round(token_ratio, 2),
        "flops_ratio": round(flops_ratio, 2),
        "components": {
            "encoder_2views_GFLOPs": round(encoder_gflops, 1),
            "cross_attention_GFLOPs": round(cross_attn_gflops, 1),
            "decoder_2heads_GFLOPs": round(decoder_total_gflops, 1),
            "dpt_head_GFLOPs": round(head_gflops, 1)
        },
        "total_GFLOPs": round(total_gflops, 0),
        "total_GMACs": round(total_gflops / 2, 0)
    },
    "recommendation": "使用区间 400-700G FLOPs，待精确测量"
}

import json
output_path = os.path.join(os.path.dirname(__file__), '..', 'logs', 'flops_estimation_v4.json')
with open(output_path, 'w') as f:
    json.dump(results, f, indent=2)
print(f"\n✅ 结果已保存到: {output_path}")
