"""
指标计算器 - 计算 3D 重建质量指标（Chamfer/AbsRel/RMSE/δ1/重投影误差）
"""
import torch
import numpy as np
from typing import Dict, Optional, Tuple, Union
from dataclasses import dataclass


@dataclass
class QualityMetrics:
    """质量指标结果"""
    chamfer: float      # Chamfer Distance
    absrel: float       # Absolute Relative Error
    rmse: float         # Root Mean Square Error
    delta1: float       # δ < 1.25 的比例
    reproj_px: float    # 重投影误差（像素）
    
    def __str__(self) -> str:
        return (
            f"Chamfer: {self.chamfer:.4f}, AbsRel: {self.absrel:.4f}, "
            f"RMSE: {self.rmse:.4f}, δ1: {self.delta1:.4f}, Reproj: {self.reproj_px:.2f}px"
        )
    
    def to_dict(self) -> Dict[str, float]:
        return {
            'chamfer': self.chamfer,
            'absrel': self.absrel,
            'rmse': self.rmse,
            'delta1': self.delta1,
            'reproj_px': self.reproj_px,
        }


def chamfer_distance(
    pred_points: torch.Tensor,
    gt_points: torch.Tensor,
    reduce: str = 'mean'
) -> torch.Tensor:
    """
    计算 Chamfer Distance
    
    Args:
        pred_points: 预测点云 (N, 3) 或 (B, N, 3) 或 (B, 3, H, W)
        gt_points: GT 点云 (M, 3) 或 (B, M, 3) 或 (B, 3, H, W)
        reduce: 'mean' / 'sum' / 'none'
    
    Returns:
        Chamfer distance
    """
    # 处理图像格式 (B, C, H, W) -> (B, N, 3)
    if pred_points.dim() == 4:
        B, C, H, W = pred_points.shape
        pred_points = pred_points.permute(0, 2, 3, 1).reshape(B, H * W, C)
        if C != 3:
            pred_points = pred_points[:, :, :3]  # 只取前3个通道
    if gt_points.dim() == 4:
        B, C, H, W = gt_points.shape
        gt_points = gt_points.permute(0, 2, 3, 1).reshape(B, H * W, C)
        if C != 3:
            gt_points = gt_points[:, :, :3]
    
    # 确保 batch 维度
    if pred_points.dim() == 2:
        pred_points = pred_points.unsqueeze(0)
        gt_points = gt_points.unsqueeze(0)
    
    B, N, _ = pred_points.shape
    _, M, _ = gt_points.shape
    
    # 采样以节省显存（如果点数太多）
    max_points = 4096
    if N > max_points:
        idx = torch.randperm(N, device=pred_points.device)[:max_points]
        pred_points = pred_points[:, idx, :]
        N = max_points
    if M > max_points:
        idx = torch.randperm(M, device=gt_points.device)[:max_points]
        gt_points = gt_points[:, idx, :]
        M = max_points
    
    # 计算两两距离
    # pred: (B, N, 1, 3), gt: (B, 1, M, 3)
    pred_expand = pred_points.unsqueeze(2)  # (B, N, 1, 3)
    gt_expand = gt_points.unsqueeze(1)      # (B, 1, M, 3)
    
    # (B, N, M)
    dist = torch.sum((pred_expand - gt_expand) ** 2, dim=-1)
    
    # pred -> gt 的最近距离
    dist_pred_to_gt = dist.min(dim=2)[0]  # (B, N)
    
    # gt -> pred 的最近距离
    dist_gt_to_pred = dist.min(dim=1)[0]  # (B, M)
    
    # Chamfer distance = 双向平均
    chamfer = dist_pred_to_gt.mean(dim=1) + dist_gt_to_pred.mean(dim=1)  # (B,)
    
    if reduce == 'mean':
        return chamfer.mean()
    elif reduce == 'sum':
        return chamfer.sum()
    else:
        return chamfer


def absolute_relative_error(
    pred_depth: torch.Tensor,
    gt_depth: torch.Tensor,
    mask: Optional[torch.Tensor] = None
) -> torch.Tensor:
    """
    计算绝对相对误差 (AbsRel)
    
    AbsRel = |pred - gt| / gt
    
    Args:
        pred_depth: 预测深度 (H, W) 或 (B, H, W)
        gt_depth: GT 深度
        mask: 有效区域掩码
    """
    if mask is None:
        mask = gt_depth > 0
    
    diff = torch.abs(pred_depth - gt_depth)
    absrel = (diff / (gt_depth + 1e-8))[mask]
    
    return absrel.mean()


def rmse(
    pred_depth: torch.Tensor,
    gt_depth: torch.Tensor,
    mask: Optional[torch.Tensor] = None
) -> torch.Tensor:
    """
    计算 Root Mean Square Error
    
    RMSE = sqrt(mean((pred - gt)^2))
    """
    if mask is None:
        mask = gt_depth > 0
    
    diff = (pred_depth - gt_depth) ** 2
    return torch.sqrt(diff[mask].mean())


def delta_accuracy(
    pred_depth: torch.Tensor,
    gt_depth: torch.Tensor,
    threshold: float = 1.25,
    mask: Optional[torch.Tensor] = None
) -> torch.Tensor:
    """
    计算 δ < threshold 的比例
    
    δ = max(pred/gt, gt/pred)
    
    常用 threshold: 1.25, 1.25^2, 1.25^3
    """
    if mask is None:
        mask = gt_depth > 0
    
    pred_valid = pred_depth[mask]
    gt_valid = gt_depth[mask]
    
    ratio = torch.maximum(pred_valid / (gt_valid + 1e-8), 
                          gt_valid / (pred_valid + 1e-8))
    
    return (ratio < threshold).float().mean()


def reprojection_error(
    pred_points: torch.Tensor,
    gt_points: torch.Tensor,
    K: torch.Tensor,
    R: Optional[torch.Tensor] = None,
    t: Optional[torch.Tensor] = None,
) -> torch.Tensor:
    """
    计算重投影误差（像素）
    
    Args:
        pred_points: 预测 3D 点 (N, 3)
        gt_points: GT 3D 点（用于对应关系）
        K: 相机内参 (3, 3)
        R: 旋转矩阵 (3, 3)，默认单位阵
        t: 平移向量 (3,)，默认零向量
    
    Returns:
        平均重投影误差（像素）
    """
    if R is None:
        R = torch.eye(3, device=pred_points.device)
    if t is None:
        t = torch.zeros(3, device=pred_points.device)
    
    # 投影预测点
    # P' = K @ (R @ P + t)
    pred_cam = (R @ pred_points.T + t.unsqueeze(1)).T  # (N, 3)
    pred_proj = (K @ pred_cam.T).T  # (N, 3)
    pred_2d = pred_proj[:, :2] / (pred_proj[:, 2:3] + 1e-8)  # (N, 2)
    
    # 投影 GT 点
    gt_cam = (R @ gt_points.T + t.unsqueeze(1)).T
    gt_proj = (K @ gt_cam.T).T
    gt_2d = gt_proj[:, :2] / (gt_proj[:, 2:3] + 1e-8)
    
    # 计算像素误差
    error = torch.norm(pred_2d - gt_2d, dim=1)
    
    return error.mean()


class MetricsCalculator:
    """
    指标计算器 - 封装所有质量指标计算
    """
    
    def __init__(self, device: str = 'cuda'):
        self.device = device
    
    def compute_all(
        self,
        pred_points: Optional[torch.Tensor] = None,
        gt_points: Optional[torch.Tensor] = None,
        pred_depth: Optional[torch.Tensor] = None,
        gt_depth: Optional[torch.Tensor] = None,
        K: Optional[torch.Tensor] = None,
        depth_mask: Optional[torch.Tensor] = None,
    ) -> QualityMetrics:
        """
        计算所有质量指标
        
        至少需要提供以下之一：
        - 点云对 (pred_points, gt_points)
        - 深度图对 (pred_depth, gt_depth)
        """
        metrics = {
            'chamfer': 0.0,
            'absrel': 0.0,
            'rmse': 0.0,
            'delta1': 0.0,
            'reproj_px': 0.0,
        }
        
        # 点云指标
        if pred_points is not None and gt_points is not None:
            pred_points = pred_points.to(self.device)
            gt_points = gt_points.to(self.device)
            
            metrics['chamfer'] = chamfer_distance(pred_points, gt_points).item()
            
            if K is not None:
                metrics['reproj_px'] = reprojection_error(
                    pred_points, gt_points, K.to(self.device)
                ).item()
        
        # 深度指标
        if pred_depth is not None and gt_depth is not None:
            pred_depth = pred_depth.to(self.device)
            gt_depth = gt_depth.to(self.device)
            
            metrics['absrel'] = absolute_relative_error(
                pred_depth, gt_depth, depth_mask
            ).item()
            
            metrics['rmse'] = rmse(
                pred_depth, gt_depth, depth_mask
            ).item()
            
            metrics['delta1'] = delta_accuracy(
                pred_depth, gt_depth, threshold=1.25, mask=depth_mask
            ).item()
        
        return QualityMetrics(**metrics)
    
    def compute_from_outputs(
        self,
        pred_output: Dict[str, torch.Tensor],
        gt_output: Dict[str, torch.Tensor],
    ) -> QualityMetrics:
        """
        从模型输出字典计算指标
        
        支持的键：
        - 'points' / 'pts3d': 3D 点云
        - 'depth': 深度图
        - 'K' / 'intrinsics': 相机内参
        """
        pred_points = pred_output.get('points') or pred_output.get('pts3d')
        gt_points = gt_output.get('points') or gt_output.get('pts3d')
        pred_depth = pred_output.get('depth')
        gt_depth = gt_output.get('depth')
        K = pred_output.get('K') or pred_output.get('intrinsics')
        
        return self.compute_all(
            pred_points=pred_points,
            gt_points=gt_points,
            pred_depth=pred_depth,
            gt_depth=gt_depth,
            K=K,
        )


def compare_metrics(
    baseline: QualityMetrics,
    experiment: QualityMetrics,
) -> Dict[str, float]:
    """
    比较两组指标，计算相对变化
    
    Returns:
        各指标的相对变化（%），正值表示下降（变差），负值表示提升
    """
    def pct_change(base, exp, higher_is_better=False):
        if base == 0:
            return 0
        change = (exp - base) / base * 100
        return -change if higher_is_better else change
    
    return {
        'chamfer_change_pct': pct_change(baseline.chamfer, experiment.chamfer),
        'absrel_change_pct': pct_change(baseline.absrel, experiment.absrel),
        'rmse_change_pct': pct_change(baseline.rmse, experiment.rmse),
        'delta1_change_pct': pct_change(baseline.delta1, experiment.delta1, higher_is_better=True),
        'reproj_change_pct': pct_change(baseline.reproj_px, experiment.reproj_px),
    }


# ============ 测试 ============

if __name__ == '__main__':
    # 创建测试数据
    pred_points = torch.randn(1000, 3)
    gt_points = pred_points + torch.randn(1000, 3) * 0.1
    
    pred_depth = torch.rand(480, 640) * 10 + 0.5
    gt_depth = pred_depth + torch.randn(480, 640) * 0.5
    
    # 计算指标
    calc = MetricsCalculator(device='cpu')
    metrics = calc.compute_all(
        pred_points=pred_points,
        gt_points=gt_points,
        pred_depth=pred_depth,
        gt_depth=gt_depth,
    )
    
    print(metrics)
    print(metrics.to_dict())
