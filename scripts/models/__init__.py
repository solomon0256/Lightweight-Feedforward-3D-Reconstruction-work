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


@dataclass
class StudentConfig:
    """Student 架构配置"""
    # 编码器配置
    encoder_layers: int = 10           # 原版 12
    encoder_heads: int = 10            # 原版 12
    encoder_dim: int = 640             # 原版 768
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
                encoder_layers=9, encoder_heads=9, encoder_dim=540,
                decoder_layers=6, decoder_heads=8, decoder_dim=432,
            ),
            'm': cls(
                encoder_layers=10, encoder_heads=10, encoder_dim=640,
                decoder_layers=7, decoder_heads=10, decoder_dim=512,
            ),
            'l': cls(
                encoder_layers=11, encoder_heads=11, encoder_dim=704,
                decoder_layers=7, decoder_heads=11, decoder_dim=576,
            ),
        }
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
        self.pos_embed = nn.Parameter(torch.zeros(1, num_patches + 1, config.encoder_dim))
        self.cls_token = nn.Parameter(torch.zeros(1, 1, config.encoder_dim))
        
        self.blocks = nn.ModuleList([
            TransformerBlock(
                dim=config.encoder_dim,
                num_heads=config.encoder_heads,
                ffn_ratio=config.encoder_ffn_ratio,
            )
            for _ in range(config.encoder_layers)
        ])
        
        self.norm = nn.LayerNorm(config.encoder_dim)
        
        self._init_weights()
    
    def _init_weights(self):
        nn.init.trunc_normal_(self.pos_embed, std=0.02)
        nn.init.trunc_normal_(self.cls_token, std=0.02)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B = x.shape[0]
        
        x = self.patch_embed(x)  # (B, N, D)
        
        cls_token = self.cls_token.expand(B, -1, -1)
        x = torch.cat([cls_token, x], dim=1)  # (B, N+1, D)
        x = x + self.pos_embed
        
        for block in self.blocks:
            x = block(x)
        
        x = self.norm(x)
        return x


class DUSt3RStudentDecoder(nn.Module):
    """DUSt3R Student 解码器（输出 3D 点云）"""
    
    def __init__(self, config: StudentConfig):
        super().__init__()
        self.config = config
        
        # 投影层：编码器维度 -> 解码器维度
        self.proj = nn.Linear(config.encoder_dim, config.decoder_dim)
        
        self.blocks = nn.ModuleList([
            TransformerBlock(
                dim=config.decoder_dim,
                num_heads=config.decoder_heads,
                ffn_ratio=config.decoder_ffn_ratio,
            )
            for _ in range(config.decoder_layers)
        ])
        
        self.norm = nn.LayerNorm(config.decoder_dim)
        
        # 输出头：预测每个 patch 的 3D 点
        self.head = nn.Linear(config.decoder_dim, config.patch_size ** 2 * 3)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: 编码器输出 (B, N+1, encoder_dim)
        
        Returns:
            pts3d: (B, 3, H, W) 3D 点云
        """
        # 跳过 CLS token
        x = x[:, 1:, :]  # (B, N, encoder_dim)
        
        x = self.proj(x)  # (B, N, decoder_dim)
        
        for block in self.blocks:
            x = block(x)
        
        x = self.norm(x)
        x = self.head(x)  # (B, N, P*P*3)
        
        # 重塑为图像形状
        B, N, _ = x.shape
        P = self.config.patch_size
        H = self.config.img_size[0] // P
        W = self.config.img_size[1] // P
        
        x = x.reshape(B, H, W, P, P, 3)
        x = x.permute(0, 5, 1, 3, 2, 4).reshape(B, 3, H * P, W * P)
        
        return x


class DUSt3RStudent(nn.Module):
    """
    DUSt3R Student 完整模型
    
    简化版架构，用于知识蒸馏
    """
    
    def __init__(self, config: Optional[StudentConfig] = None, scale: str = 's'):
        super().__init__()
        
        if config is None:
            config = StudentConfig.from_scale(scale)
        
        self.config = config
        self.encoder = DUSt3RStudentEncoder(config)
        self.decoder = DUSt3RStudentDecoder(config)
        
        # 深度头（可选）
        self.depth_head = nn.Sequential(
            nn.Conv2d(3, 64, 3, padding=1),
            nn.ReLU(),
            nn.Conv2d(64, 1, 1),
        )
    
    def forward(
        self,
        img1: torch.Tensor,
        img2: Optional[torch.Tensor] = None,
        return_features: bool = False,
    ) -> Dict[str, torch.Tensor]:
        """
        前向传播
        
        Args:
            img1: 第一张图像 (B, 3, H, W)
            img2: 第二张图像（可选）
            return_features: 是否返回中间特征（用于蒸馏）
        
        Returns:
            {
                'pts3d': (B, 3, H, W),
                'depth': (B, 1, H, W),
                'features': (B, N, D) - 如果 return_features=True
            }
        """
        if img2 is None:
            img2 = img1
        
        # 编码两张图
        feat1 = self.encoder(img1)  # (B, N+1, D)
        feat2 = self.encoder(img2)
        
        # 融合特征（简单相加）
        feat = feat1 + feat2
        
        # 解码
        pts3d = self.decoder(feat)  # (B, 3, H, W)
        
        # 深度
        depth = self.depth_head(pts3d)  # (B, 1, H, W)
        
        output = {
            'pts3d': pts3d,
            'depth': depth,
        }
        
        if return_features:
            output['features'] = feat
        
        return output
    
    @classmethod
    def from_config_dict(cls, config_dict: Dict[str, Any]) -> 'DUSt3RStudent':
        """从配置字典创建模型"""
        config = StudentConfig(
            encoder_layers=config_dict.get('encoder_layers', 10),
            encoder_heads=int(12 * config_dict.get('mha_heads_ratio', 0.8)),
            encoder_dim=int(768 * config_dict.get('ffn_ratio', 0.8)),
            decoder_layers=config_dict.get('decoder_layers', 6),
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
