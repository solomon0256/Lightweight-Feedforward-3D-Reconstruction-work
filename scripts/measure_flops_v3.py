"""
DUSt3R FLOPs 准确测量 v3
使用 ptflops 库（比较可靠）
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'third_party', 'dust3r'))

import torch
import json
from datetime import datetime

print("=" * 60)
print("DUSt3R FLOPs 准确测量 v3")
print(f"时间: {datetime.now().isoformat()}")
print("=" * 60)

# 安装 ptflops
os.system("pip install ptflops -q")

from ptflops import get_model_complexity_info
from dust3r.model import AsymmetricCroCo3DStereo

print("\n加载模型...")
model = AsymmetricCroCo3DStereo.from_pretrained(
    'naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt',
    local_files_only=True
)
model.eval()
print("✅ 模型加载成功")

# DUSt3R 输入格式特殊，需要 wrapper
class DUSt3RWrapper(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model
        self.H, self.W = 384, 512
    
    def forward(self, x):
        # x: [B, 6, H, W] -> 拆分成两个视图
        B = x.shape[0]
        img1 = x[:, :3]  # [B, 3, H, W]
        img2 = x[:, 3:]  # [B, 3, H, W]
        
        view1 = {'img': img1, 'true_shape': torch.tensor([[self.H, self.W]] * B)}
        view2 = {'img': img2, 'true_shape': torch.tensor([[self.H, self.W]] * B)}
        
        return self.model(view1, view2)

wrapper = DUSt3RWrapper(model)

print("\n" + "=" * 60)
print("方法1: ptflops (6通道输入)")
print("=" * 60)

try:
    # 用 6 通道输入模拟两个视图
    macs, params = get_model_complexity_info(
        wrapper, 
        (6, 384, 512),  # 两个视图合并
        as_strings=True,
        print_per_layer_stat=False,
        verbose=False
    )
    print(f"MACs: {macs}")
    print(f"Params: {params}")
except Exception as e:
    print(f"❌ ptflops 失败: {e}")

# 也尝试只计算单个 encoder
print("\n" + "=" * 60)
print("方法2: 只测 Encoder (单视图)")
print("=" * 60)

class EncoderWrapper(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.patch_embed = model.patch_embed
        self.enc_blocks = model.enc_blocks
        self.enc_norm = model.enc_norm
        self.rope = model.rope
    
    def forward(self, x):
        B, C, H, W = x.shape
        x = self.patch_embed(x)  # [B, N, D]
        pos = self.rope.get_cos_sin(W // 16, H // 16, x.device, x.dtype)
        for blk in self.enc_blocks:
            x = blk(x, pos)
        x = self.enc_norm(x)
        return x

try:
    enc_wrapper = EncoderWrapper(model)
    macs, params = get_model_complexity_info(
        enc_wrapper,
        (3, 384, 512),
        as_strings=True,
        print_per_layer_stat=False,
        verbose=False
    )
    print(f"Encoder MACs (单视图): {macs}")
    print(f"Encoder Params: {params}")
    
    # 手动 parse 数值
    if 'GMac' in macs:
        macs_value = float(macs.replace(' GMac', ''))
        print(f"\n推算全模型 (2视图 + decoder + head):")
        # 粗略估计: encoder × 2 + decoder (约 encoder 的 0.8) × 2
        estimated_total = macs_value * 2 * 2.0
        print(f"  估计 MACs: {estimated_total:.1f} GMac")
        print(f"  估计 FLOPs: {estimated_total * 2:.1f} GFLOPs")
except Exception as e:
    print(f"❌ Encoder 测量失败: {e}")
    import traceback
    traceback.print_exc()

# 参考: ViT-Large 的标准 FLOPs
print("\n" + "=" * 60)
print("参考: ViT-Large 标准 FLOPs")
print("=" * 60)
print("""
ViT-Large-14 (ImageNet):
- 输入: 224×224
- FLOPs: ~60G

DUSt3R 输入: 512×384 (约 224×224 的 3.9 倍面积)
ViT token 数: 768 vs 256 (约 3x)

单 ViT-Large encoder @ 512×384:
- 粗估: 60G × 3 = ~180G FLOPs

DUSt3R 完整模型:
- 2 × encoder (双视图): ~360G
- cross-attention layers: ~50-100G  
- 2 × decoder: ~100-200G
- head: ~10G
--------------------------
总估计: 500-700G FLOPs

这比我之前手动计算的 2100G 合理得多。
之前的公式有问题！
""")

print("\n" + "=" * 60)
print("结论")
print("=" * 60)
print("""
⚠️ 之前文档里的 "~430G FLOPs" 来源不明！

实际情况:
1. 参数量: 571M ✅ (已验证，与 HuggingFace 一致)
2. FLOPs: 需要用可靠工具测量

建议:
- 使用 ptflops 或 fvcore 在更大显存机器上测量
- 或者标记为 "待验证"，不要用未经验证的数值
""")
