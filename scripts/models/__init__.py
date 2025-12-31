"""
Student 模型架构定义

提供多种轻量化 Student 架构：
- DUSt3R Student S: 减少 30% 层数/头数/FFN
- DUSt3R Student M: 减少 20%
- 自定义缩放配置
"""

import sys
from pathlib import Path
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass
from copy import deepcopy
from functools import partial

# 设置路径以导入Teacher的类
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
_dust3r_path = _PROJECT_ROOT / 'third_party' / 'dust3r'
_croco_path = _dust3r_path / 'croco'

# 确保 croco/models/__init__.py 存在
_croco_models_init = _croco_path / 'models' / '__init__.py'
if not _croco_models_init.exists():
    _croco_models_init.parent.mkdir(parents=True, exist_ok=True)
    _croco_models_init.touch()

# 添加到 sys.path（顺序很重要：croco必须在dust3r之前，因为models在croco下）
for p in [str(_croco_path), str(_dust3r_path)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# 导入Teacher的类（与Teacher完全一致）
# 注意：使用绝对导入路径避免与scripts.models冲突
import importlib.util
_blocks_path = _croco_path / 'models' / 'blocks.py'
_pos_embed_path = _croco_path / 'models' / 'pos_embed.py'

# 动态加载blocks模块
_spec_blocks = importlib.util.spec_from_file_location("croco_blocks", _blocks_path)
_croco_blocks = importlib.util.module_from_spec(_spec_blocks)
_spec_blocks.loader.exec_module(_croco_blocks)
Block = _croco_blocks.Block
DecoderBlock = _croco_blocks.DecoderBlock
PatchEmbed = _croco_blocks.PatchEmbed

# 动态加载pos_embed模块
_spec_pos = importlib.util.spec_from_file_location("croco_pos_embed", _pos_embed_path)
_croco_pos = importlib.util.module_from_spec(_spec_pos)
_spec_pos.loader.exec_module(_croco_pos)
RoPE2D = _croco_pos.RoPE2D


@dataclass
class StudentConfig:
    """Student 架构配置"""
    # 编码器配置
    encoder_layers: int = 17           # Teacher: 24层
    encoder_heads: int = 12            # Teacher: 16头
    encoder_dim: int = 720             # Teacher: 1024维
    encoder_ffn_ratio: float = 4.0     # FFN 膨胀比
    
    # 解码器配置
    decoder_layers: int = 6            # 原版 8
    decoder_heads: int = 10
    decoder_dim: int = 512
    decoder_ffn_ratio: float = 4.0
    
    # 其他
    patch_size: int = 16
    img_size: Tuple[int, int] = (512, 384)
    
    @classmethod
    def from_scale(cls, scale: str = 's') -> 'StudentConfig':
        """
        根据缩放等级创建配置
        
        Args:
            scale: 's' (small, -30%), 'm' (medium, -20%), 'l' (large, -10%)
        """
        # 注意：RoPE要求 head_dim 必须是偶数，且 head_dim/2 >= max_position(32)
        # Teacher: enc_dim=1024, enc_heads=16 → head_dim=64; dec_dim=768, dec_heads=12 → head_dim=64
        presets = {
            's': cls(
                encoder_layers=9, encoder_heads=8, encoder_dim=512,   # 512 // 8 = 64 ✓
                decoder_layers=6, decoder_heads=8, decoder_dim=512,   # 512 // 8 = 64 ✓
            ),
            'm': cls(
                encoder_layers=12, encoder_heads=8, encoder_dim=512,  # 512 // 8 = 64 ✓
                decoder_layers=8, decoder_heads=8, decoder_dim=512,   # 512 // 8 = 64 ✓
            ),
            'l': cls(
                encoder_layers=16, encoder_heads=12, encoder_dim=768, # 768 // 12 = 64 ✓
                decoder_layers=8, decoder_heads=12, decoder_dim=768,  # 768 // 12 = 64 ✓
            ),
        }
        # 确保所有配置的dim都能被heads整除
        for scale_name, config in presets.items():
            # 调整encoder_dim
            if config.encoder_dim % config.encoder_heads != 0:
                head_dim = config.encoder_dim // config.encoder_heads
                config.encoder_dim = head_dim * config.encoder_heads
            
            # 调整decoder_dim
            if config.decoder_dim % config.decoder_heads != 0:
                head_dim = config.decoder_dim // config.decoder_heads
                config.decoder_dim = head_dim * config.decoder_heads
        
        return presets.get(scale, cls())


# 注意：不再需要自定义的MultiHeadAttention、CrossAttention、DecoderBlock、TransformerBlock、FFN、PatchEmbed
# 因为我们现在直接使用Teacher的类（Block, DecoderBlock, PatchEmbed），它们已包含RoPE支持


class DUSt3RStudentEncoder(nn.Module):
    """DUSt3R Student 编码器（使用Teacher的Block和RoPE）"""
    
    def __init__(self, config: StudentConfig):
        super().__init__()
        self.config = config
        
        # 使用Teacher的PatchEmbed（返回x, pos）
        self.patch_embed = PatchEmbed(
            img_size=config.img_size,
            patch_size=config.patch_size,
            in_chans=3,
            embed_dim=config.encoder_dim,
            norm_layer=None,
            flatten=True
        )
        
        # 初始化RoPE（与Teacher一致，使用RoPE100）
        self.rope = RoPE2D(freq=100.0)
        
        # 使用Teacher的Block类（包含RoPE支持）
        norm_layer = partial(nn.LayerNorm, eps=1e-6)
        self.blocks = nn.ModuleList([
            Block(
                dim=config.encoder_dim,
                num_heads=config.encoder_heads,
                mlp_ratio=config.encoder_ffn_ratio,
                qkv_bias=True,
                drop=0.0,
                attn_drop=0.0,
                drop_path=0.0,
                act_layer=nn.GELU,
                norm_layer=norm_layer,
                rope=self.rope
            )
            for _ in range(config.encoder_layers)
        ])
        
        self.norm = norm_layer(config.encoder_dim)
    
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            x: (B, C, H, W)
        Returns:
            x: (B, N, D) - 编码特征
            pos: (B, N, 2) - 位置信息
        """
        # PatchEmbed返回 (x, pos)
        x, pos = self.patch_embed(x)  # x: (B, N, D), pos: (B, N, 2)
        
        # 使用Teacher的Block（需要传递pos）
        for block in self.blocks:
            x = block(x, pos)
        
        x = self.norm(x)
        return x, pos


class DUSt3RStudent(nn.Module):
    """
    DUSt3R Student 完整模型（与Teacher架构对齐）
    
    - 两个独立Decoder（使用deepcopy）
    - Cross-Attention机制
    - 无CLS token
    - RoPE位置编码（在attention中应用）
    """
    
    def __init__(self, config: Optional[StudentConfig] = None, scale: str = 's'):
        super().__init__()
        
        if config is None:
            config = StudentConfig.from_scale(scale)
        
        self.config = config
        self.encoder = DUSt3RStudentEncoder(config)
        
        # Decoder投影层
        self.decoder_embed = nn.Linear(config.encoder_dim, config.decoder_dim)
        
        # 初始化RoPE（Decoder也使用相同的RoPE）
        self.rope = RoPE2D(freq=100.0)
        
        # 使用Teacher的DecoderBlock类（包含RoPE和CrossAttention支持）
        norm_layer = partial(nn.LayerNorm, eps=1e-6)
        self.dec_blocks = nn.ModuleList([
            DecoderBlock(
                dim=config.decoder_dim,
                num_heads=config.decoder_heads,
                mlp_ratio=config.decoder_ffn_ratio,
                qkv_bias=True,
                drop=0.0,
                attn_drop=0.0,
                drop_path=0.0,
                act_layer=nn.GELU,
                norm_layer=norm_layer,
                norm_mem=True,
                rope=self.rope
            )
            for _ in range(config.decoder_layers)
        ])
        self.dec_blocks2 = deepcopy(self.dec_blocks)  # 第二个独立Decoder
        self.dec_norm = norm_layer(config.decoder_dim)
        
        # 输出头：预测每个patch的3D点（两个独立头）
        self.head1 = nn.Linear(config.decoder_dim, config.patch_size ** 2 * 3)
        self.head2 = nn.Linear(config.decoder_dim, config.patch_size ** 2 * 3)
        
        # 置信度头（可选）
        self.conf_head1 = nn.Linear(config.decoder_dim, config.patch_size ** 2 * 1)
        self.conf_head2 = nn.Linear(config.decoder_dim, config.patch_size ** 2 * 1)
    
    def forward(
        self,
        view1: Dict[str, torch.Tensor],
        view2: Dict[str, torch.Tensor],
    ) -> Tuple[Dict[str, torch.Tensor], Dict[str, torch.Tensor]]:
        """
        前向传播（与Teacher对齐）
        
        Args:
            view1: 第一个view，包含'img'键 (B, 3, H, W)
            view2: 第二个view，包含'img'键 (B, 3, H, W)
        
        Returns:
            output1: 第一个view的输出 {'pts3d': (B, H, W, 3), 'conf': (B, H, W, 1)}
            output2: 第二个view的输出
        """
        img1 = view1['img']
        img2 = view2['img']
        
        # 1. 编码两张图像（共享Encoder，返回特征和位置）
        enc_feat1, pos1 = self.encoder(img1)  # (B, N, D), (B, N, 2)
        enc_feat2, pos2 = self.encoder(img2)   # (B, N, D), (B, N, 2)
        
        # 2. Decoder投影
        dec_feat1 = self.decoder_embed(enc_feat1)  # (B, N, decoder_dim)
        dec_feat2 = self.decoder_embed(enc_feat2)  # (B, N, decoder_dim)
        
        # 3. Decoder处理（两个独立Decoder，通过cross-attention交换信息）
        # DecoderBlock需要传递位置信息: (x, y, xpos, ypos)
        # 关键：同一层内，两个block都使用上一层的输出（与Teacher对齐）
        prev_out1, prev_out2 = dec_feat1, dec_feat2
        
        for blk1, blk2 in zip(self.dec_blocks, self.dec_blocks2):
            # Decoder1: view1的特征，cross-attention到view2（使用上一层的输出）
            dec_out1, _ = blk1(prev_out1, prev_out2, pos1, pos2)
            # Decoder2: view2的特征，cross-attention到view1（使用上一层的输出）
            dec_out2, _ = blk2(prev_out2, prev_out1, pos2, pos1)
            # 更新为当前层输出，供下一层使用
            prev_out1, prev_out2 = dec_out1, dec_out2
        
        dec_out1 = self.dec_norm(dec_out1)  # (B, N, decoder_dim)
        dec_out2 = self.dec_norm(dec_out2)
        
        # 4. 输出头
        pts3d_flat1 = self.head1(dec_out1)  # (B, N, P*P*3)
        pts3d_flat2 = self.head2(dec_out2)
        conf_flat1 = self.conf_head1(dec_out1)  # (B, N, P*P*1)
        conf_flat2 = self.conf_head2(dec_out2)
        
        # 5. 重塑为图像形状
        B, N, _ = pts3d_flat1.shape
        P = self.config.patch_size
        H = self.config.img_size[0] // P
        W = self.config.img_size[1] // P
        
        pts3d1 = pts3d_flat1.reshape(B, H, W, P, P, 3).permute(0, 3, 1, 4, 2, 5).reshape(B, H*P, W*P, 3)
        pts3d2 = pts3d_flat2.reshape(B, H, W, P, P, 3).permute(0, 3, 1, 4, 2, 5).reshape(B, H*P, W*P, 3)
        conf1 = conf_flat1.reshape(B, H, W, P, P, 1).permute(0, 3, 1, 4, 2, 5).reshape(B, H*P, W*P, 1)
        conf2 = conf_flat2.reshape(B, H, W, P, P, 1).permute(0, 3, 1, 4, 2, 5).reshape(B, H*P, W*P, 1)
        
        output1 = {'pts3d': pts3d1, 'conf': conf1}
        output2 = {'pts3d': pts3d2, 'conf': conf2}
        
        return output1, output2
    
    @classmethod
    def from_config_dict(cls, config_dict: Dict[str, Any]) -> 'DUSt3RStudent':
        """从配置字典创建模型（直接使用配置参数）"""
        # 直接读取配置参数（优先使用显式配置）
        encoder_layers = config_dict.get('encoder_layers', 17)
        encoder_heads = config_dict.get('encoder_heads', 12)
        encoder_dim = config_dict.get('encoder_dim', 720)
        encoder_ffn_ratio = config_dict.get('encoder_ffn_ratio', 4.0)
        
        decoder_layers = config_dict.get('decoder_layers', 8)
        decoder_heads = config_dict.get('decoder_heads', 9)
        decoder_dim = config_dict.get('decoder_dim', 540)
        decoder_ffn_ratio = config_dict.get('decoder_ffn_ratio', 4.0)
        
        patch_size = config_dict.get('patch_size', 16)
        img_size = config_dict.get('img_size', [512, 384])
        if isinstance(img_size, list):
            img_size = tuple(img_size)
        
        # 确保dim能被heads整除
        if encoder_dim % encoder_heads != 0:
            head_dim = encoder_dim // encoder_heads
            encoder_dim = head_dim * encoder_heads
            print(f"[WARN] encoder_dim adjusted to {encoder_dim} for divisibility")
        
        if decoder_dim % decoder_heads != 0:
            head_dim = decoder_dim // decoder_heads
            decoder_dim = head_dim * decoder_heads
            print(f"[WARN] decoder_dim adjusted to {decoder_dim} for divisibility")
        
        config = StudentConfig(
            encoder_layers=encoder_layers,
            encoder_heads=encoder_heads,
            encoder_dim=encoder_dim,
            encoder_ffn_ratio=encoder_ffn_ratio,
            decoder_layers=decoder_layers,
            decoder_heads=decoder_heads,
            decoder_dim=decoder_dim,
            decoder_ffn_ratio=decoder_ffn_ratio,
            patch_size=patch_size,
            img_size=img_size,
        )
        return cls(config=config)


def create_student_model(
    arch: str = 'dust3r_student_s',
    config_dict: Optional[Dict[str, Any]] = None,
    device: str = 'cuda',
) -> DUSt3RStudent:
    """
    创建 Student 模型
    
    Args:
        arch: 架构名称 ('dust3r_student_s', 'dust3r_student_m', 'dust3r_student_l')
        config_dict: 自定义配置（覆盖 arch）
        device: 设备
    """
    if config_dict:
        model = DUSt3RStudent.from_config_dict(config_dict)
    else:
        scale = arch.split('_')[-1] if '_' in arch else 's'
        model = DUSt3RStudent(scale=scale)
    
    return model.to(device)


# ============ 测试 ============

if __name__ == '__main__':
    # 测试 Student 模型
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    
    for scale in ['s', 'm', 'l']:
        config = StudentConfig.from_scale(scale)
        model = DUSt3RStudent(config=config).to(device)
        
        # 测试前向传播
        img = torch.randn(1, 3, 512, 384, device=device)
        output = model(img, return_features=True)
        
        # 统计参数
        params = sum(p.numel() for p in model.parameters()) / 1e6
        
        print(f"\nStudent-{scale.upper()}:")
        print(f"  Params: {params:.2f}M")
        print(f"  pts3d shape: {output['pts3d'].shape}")
        print(f"  depth shape: {output['depth'].shape}")
        print(f"  features shape: {output['features'].shape}")
