"""
Student 模型架构定义

提供多种轻量化 Student 架构：
- DUSt3R Student S: 减少 30% 层数/头数/FFN
- DUSt3R Student M: 减少 20%
- 自定义缩放配置
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass
from copy import deepcopy


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
        presets = {
            's': cls(
                encoder_layers=9, encoder_heads=9, encoder_dim=540,  # 540 // 9 = 60 ✓
                decoder_layers=6, decoder_heads=8, decoder_dim=432,  # 432 // 8 = 54 ✓
            ),
            'm': cls(
                encoder_layers=10, encoder_heads=10, encoder_dim=640,  # 640 // 10 = 64 ✓
                decoder_layers=7, decoder_heads=10, decoder_dim=512,  # 512 // 10 = 51.2 ✗ → 510
            ),
            'l': cls(
                encoder_layers=11, encoder_heads=11, encoder_dim=704,  # 704 // 11 = 64 ✓
                decoder_layers=7, decoder_heads=11, decoder_dim=572,  # 572 // 11 = 52 ✓ (原576不能整除)
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


class MultiHeadAttention(nn.Module):
    """多头注意力（支持可变头数）"""
    
    def __init__(self, dim: int, num_heads: int, dropout: float = 0.0):
        super().__init__()
        self.num_heads = num_heads
        self.head_dim = dim // num_heads
        self.scale = self.head_dim ** -0.5
        
        self.qkv = nn.Linear(dim, dim * 3)
        self.proj = nn.Linear(dim, dim)
        self.dropout = nn.Dropout(dropout)
    
    def forward(self, x: torch.Tensor, mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        B, N, C = x.shape
        qkv = self.qkv(x).reshape(B, N, 3, self.num_heads, self.head_dim).permute(2, 0, 3, 1, 4)
        q, k, v = qkv[0], qkv[1], qkv[2]
        
        attn = (q @ k.transpose(-2, -1)) * self.scale
        if mask is not None:
            attn = attn.masked_fill(mask == 0, float('-inf'))
        attn = attn.softmax(dim=-1)
        attn = self.dropout(attn)
        
        x = (attn @ v).transpose(1, 2).reshape(B, N, C)
        x = self.proj(x)
        return x


class CrossAttention(nn.Module):
    """交叉注意力（用于Decoder中两个view之间的信息交换）"""
    
    def __init__(self, dim: int, num_heads: int, dropout: float = 0.0):
        super().__init__()
        self.num_heads = num_heads
        self.head_dim = dim // num_heads
        self.scale = self.head_dim ** -0.5
        
        self.q = nn.Linear(dim, dim)
        self.kv = nn.Linear(dim, dim * 2)
        self.proj = nn.Linear(dim, dim)
        self.dropout = nn.Dropout(dropout)
    
    def forward(self, x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: query (B, N1, D)
            y: key/value (B, N2, D)
        Returns:
            out: (B, N1, D)
        """
        B, N1, C = x.shape
        N2 = y.shape[1]
        
        q = self.q(x).reshape(B, N1, self.num_heads, self.head_dim).permute(0, 2, 1, 3)
        kv = self.kv(y).reshape(B, N2, 2, self.num_heads, self.head_dim).permute(2, 0, 3, 1, 4)
        k, v = kv[0], kv[1]
        
        attn = (q @ k.transpose(-2, -1)) * self.scale
        attn = attn.softmax(dim=-1)
        attn = self.dropout(attn)
        
        x = (attn @ v).permute(0, 2, 1, 3).reshape(B, N1, C)
        x = self.proj(x)
        return x


class DecoderBlock(nn.Module):
    """Decoder块（包含self-attention和cross-attention）"""
    
    def __init__(self, dim: int, num_heads: int, ffn_ratio: float = 4.0, dropout: float = 0.0):
        super().__init__()
        self.norm1 = nn.LayerNorm(dim)
        self.self_attn = MultiHeadAttention(dim, num_heads, dropout)
        self.norm2 = nn.LayerNorm(dim)
        self.cross_attn = CrossAttention(dim, num_heads, dropout)
        self.norm3 = nn.LayerNorm(dim)
        self.ffn = FFN(dim, ffn_ratio, dropout)
    
    def forward(self, x: torch.Tensor, y: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            x: 当前view的特征 (B, N1, D)
            y: 另一个view的特征 (B, N2, D)
        Returns:
            x: 更新后的当前view特征
            y: 另一个view特征（不变）
        """
        # Self-attention
        x = x + self.self_attn(self.norm1(x))
        # Cross-attention
        x = x + self.cross_attn(self.norm2(x), y)
        # FFN
        x = x + self.ffn(self.norm3(x))
        return x, y


class FFN(nn.Module):
    """前馈网络"""
    
    def __init__(self, dim: int, ffn_ratio: float = 4.0, dropout: float = 0.0):
        super().__init__()
        hidden_dim = int(dim * ffn_ratio)
        self.fc1 = nn.Linear(dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, dim)
        self.dropout = nn.Dropout(dropout)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = F.gelu(self.fc1(x))
        x = self.dropout(x)
        x = self.fc2(x)
        x = self.dropout(x)
        return x


class TransformerBlock(nn.Module):
    """Transformer 块"""
    
    def __init__(
        self,
        dim: int,
        num_heads: int,
        ffn_ratio: float = 4.0,
        dropout: float = 0.0,
    ):
        super().__init__()
        self.norm1 = nn.LayerNorm(dim)
        self.attn = MultiHeadAttention(dim, num_heads, dropout)
        self.norm2 = nn.LayerNorm(dim)
        self.ffn = FFN(dim, ffn_ratio, dropout)
    
    def forward(self, x: torch.Tensor, mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        x = x + self.attn(self.norm1(x), mask)
        x = x + self.ffn(self.norm2(x))
        return x


class PatchEmbed(nn.Module):
    """图像分块嵌入"""
    
    def __init__(
        self,
        img_size: Tuple[int, int] = (512, 384),
        patch_size: int = 16,
        in_channels: int = 3,
        embed_dim: int = 768,
    ):
        super().__init__()
        self.img_size = img_size
        self.patch_size = patch_size
        self.num_patches = (img_size[0] // patch_size) * (img_size[1] // patch_size)
        
        self.proj = nn.Conv2d(
            in_channels, embed_dim,
            kernel_size=patch_size, stride=patch_size
        )
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, C, H, W) -> (B, N, D)
        x = self.proj(x)  # (B, D, H/P, W/P)
        x = x.flatten(2).transpose(1, 2)  # (B, N, D)
        return x


class DUSt3RStudentEncoder(nn.Module):
    """DUSt3R Student 编码器"""
    
    def __init__(self, config: StudentConfig):
        super().__init__()
        self.config = config
        
        self.patch_embed = PatchEmbed(
            img_size=config.img_size,
            patch_size=config.patch_size,
            embed_dim=config.encoder_dim,
        )
        
        num_patches = self.patch_embed.num_patches
        
        # 删除CLS token和可学习位置编码（与Teacher对齐，使用RoPE）
        # 注意：RoPE在attention中应用，这里不需要显式位置编码
        
        self.blocks = nn.ModuleList([
            TransformerBlock(
                dim=config.encoder_dim,
                num_heads=config.encoder_heads,
                ffn_ratio=config.encoder_ffn_ratio,
            )
            for _ in range(config.encoder_layers)
        ])
        
        self.norm = nn.LayerNorm(config.encoder_dim)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B = x.shape[0]
        
        x = self.patch_embed(x)  # (B, N, D)
        # 不使用CLS token和位置编码（RoPE在attention中应用）
        
        for block in self.blocks:
            x = block(x)
        
        x = self.norm(x)
        return x


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
        
        # 两个独立Decoder（使用deepcopy，与Teacher对齐）
        self.dec_blocks = nn.ModuleList([
            DecoderBlock(
                dim=config.decoder_dim,
                num_heads=config.decoder_heads,
                ffn_ratio=config.decoder_ffn_ratio,
            )
            for _ in range(config.decoder_layers)
        ])
        self.dec_blocks2 = deepcopy(self.dec_blocks)  # 第二个独立Decoder
        self.dec_norm = nn.LayerNorm(config.decoder_dim)
        
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
        
        # 1. 编码两张图像（共享Encoder）
        enc_feat1 = self.encoder(img1)  # (B, N, D)
        enc_feat2 = self.encoder(img2)   # (B, N, D)
        
        # 2. Decoder投影
        dec_feat1 = self.decoder_embed(enc_feat1)  # (B, N, decoder_dim)
        dec_feat2 = self.decoder_embed(enc_feat2)  # (B, N, decoder_dim)
        
        # 3. Decoder处理（两个独立Decoder，通过cross-attention交换信息）
        dec_out1 = dec_feat1
        dec_out2 = dec_feat2
        
        for blk1, blk2 in zip(self.dec_blocks, self.dec_blocks2):
            # Decoder1: view1的特征，cross-attention到view2
            dec_out1, _ = blk1(dec_out1, dec_out2)
            # Decoder2: view2的特征，cross-attention到view1
            dec_out2, _ = blk2(dec_out2, dec_out1)
        
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
