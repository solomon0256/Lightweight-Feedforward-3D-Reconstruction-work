#!/usr/bin/env python3
"""
蒸馏训练脚本 - K-only

用途：
- 训练轻量 Student 模型逼近 Teacher
- 使用 Regr3D_Loss（归一化L2距离）+ 置信度对齐损失
- 支持课程式蒸馏（前期任务损失为主，后期增加蒸馏权重）

运行示例：
    python scripts/train_distill.py --exp-config distill.yaml
    python scripts/train_distill.py --dry-run --max-epochs 2
"""

import argparse
import sys
import os
import json
import random
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple, Any

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data.distributed import DistributedSampler

# 添加项目根目录到路径
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.config import (
    ExperimentConfig, add_common_args, config_from_args, get_project_root
)
from scripts.utils.logger import ExperimentLog, save_experiment_log
from scripts.utils.timer import Timer
from scripts.utils.model_stats import get_model_stats
from scripts.utils.metrics import MetricsCalculator, QualityMetrics
from scripts.models import create_student_model, DUSt3RStudent

# 导入DUSt3R的几何工具
import sys
DUST3R_PATH = PROJECT_ROOT / "third_party" / "dust3r"
sys.path.insert(0, str(DUST3R_PATH))
from dust3r.utils.geometry import normalize_pointcloud


# ============ 数据集 ============

class PairDataset(Dataset):
    """图像对数据集"""
    
    def __init__(
        self,
        pairs_list: str,
        img_size: Tuple[int, int] = (512, 384),
        transform=None,
        dummy: bool = False,
        num_dummy: int = 100,
    ):
        self.pairs = []
        self.img_size = img_size
        self.transform = transform
        self.dummy = dummy
        
        if dummy:
            self.pairs = [(f"dummy_{i}_a", f"dummy_{i}_b") for i in range(num_dummy)]
        elif Path(pairs_list).exists():
            with open(pairs_list, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and '|' in line:
                        img1, img2 = line.split('|')
                        self.pairs.append((img1.strip(), img2.strip()))
    
    def __len__(self):
        return len(self.pairs)
    
    def __getitem__(self, idx):
        if self.dummy:
            # 返回随机数据
            img1 = torch.randn(3, *self.img_size)
            img2 = torch.randn(3, *self.img_size)
            gt_pts = torch.randn(3, *self.img_size)
            gt_depth = torch.rand(1, *self.img_size)
            return {
                'img1': img1,
                'img2': img2,
                'gt_pts3d': gt_pts,
                'gt_depth': gt_depth,
            }
        
        # 实际数据加载
        img1_path, img2_path = self.pairs[idx]
        
        try:
            from PIL import Image
            from torchvision import transforms
            
            if self.transform is None:
                self.transform = transforms.Compose([
                    transforms.Resize(self.img_size),
                    transforms.ToTensor(),
                    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                       std=[0.229, 0.224, 0.225]),
                ])
            
            img1 = self.transform(Image.open(img1_path).convert('RGB'))
            img2 = self.transform(Image.open(img2_path).convert('RGB'))
            
            # GT 数据需要根据实际情况加载
            gt_pts = torch.zeros(3, *self.img_size)
            gt_depth = torch.zeros(1, *self.img_size)
            
            return {
                'img1': img1,
                'img2': img2,
                'gt_pts3d': gt_pts,
                'gt_depth': gt_depth,
            }
        except Exception as e:
            print(f"[WARN] Failed to load pair {idx}: {e}")
            return self.__getitem__((idx + 1) % len(self))


# ============ 蒸馏损失 ============

def Regr3D_Loss(pred_pts: torch.Tensor, target_pts: torch.Tensor, norm_mode: str = 'avg_dis') -> torch.Tensor:
    """
    3D点云回归损失（归一化L2距离）
    
    Args:
        pred_pts: (B, H, W, 3) 预测点云
        target_pts: (B, H, W, 3) 目标点云
        norm_mode: 归一化模式，'avg_dis'表示按平均距离归一化
    
    Returns:
        loss: 标量损失值
    """
    # 确保点云格式为 (B, H, W, 3)
    if pred_pts.ndim == 4 and pred_pts.shape[1] == 3:
        # 如果是 (B, 3, H, W)，转换为 (B, H, W, 3)
        pred_pts = pred_pts.permute(0, 2, 3, 1)
    if target_pts.ndim == 4 and target_pts.shape[1] == 3:
        target_pts = target_pts.permute(0, 2, 3, 1)
    
    # 归一化点云（单个点云时mask=None）
    pred_norm = normalize_pointcloud(pred_pts, None, norm_mode)
    target_norm = normalize_pointcloud(target_pts, None, norm_mode)
    # L2距离
    loss = torch.norm(pred_norm - target_norm, dim=-1).mean()
    return loss


class DistillationLoss(nn.Module):
    """
    蒸馏损失
    
    L = α * L_task + β * L_distill + γ * L_conf
    
    - L_task: 任务损失（归一化L2距离）
    - L_distill: 蒸馏损失（Student vs Teacher点云对齐）
    - L_conf: 置信度对齐损失
    """
    
    def __init__(
        self,
        alpha: float = 1.0,
        beta: float = 0.5,
        gamma: float = 0.0,
    ):
        super().__init__()
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
    
    def forward(
        self,
        student_output: Dict[str, torch.Tensor],
        teacher_output: Dict[str, torch.Tensor],
        gt: Optional[Dict[str, torch.Tensor]] = None,
    ) -> Dict[str, torch.Tensor]:
        """
        计算蒸馏损失
        
        Returns:
            {
                'total': 总损失,
                'task': 任务损失,
                'distill': 蒸馏损失,
                'conf': 置信度对齐损失,
            }
        """
        losses = {}
        
        # 提取点云和置信度
        s_pts = student_output['pts3d']
        t_pts = teacher_output['pts3d']
        
        # 任务损失（使用归一化的Regr3D_Loss）
        if gt is not None and 'gt_pts3d' in gt:
            # 使用 GT 计算任务损失
            losses['task'] = Regr3D_Loss(s_pts, gt['gt_pts3d'], norm_mode='avg_dis')
        else:
            # 使用 Teacher 输出作为目标
            losses['task'] = Regr3D_Loss(s_pts, t_pts.detach(), norm_mode='avg_dis')
        
        # 蒸馏损失（Student vs Teacher点云对齐）
        losses['distill'] = Regr3D_Loss(s_pts, t_pts.detach(), norm_mode='avg_dis')
        
        # 置信度对齐损失 L_conf（如果形状不匹配，暂时跳过）
        if 'conf' in student_output and 'conf' in teacher_output:
            s_conf = student_output['conf']
            t_conf = teacher_output['conf']
            # 确保形状一致
            try:
                if s_conf.shape != t_conf.shape:
                    # 如果形状不同，尝试reshape或squeeze最后一个维度
                    if s_conf.ndim == 4 and t_conf.ndim == 4:
                        # (B, H, W, 1) 格式
                        if s_conf.shape[-1] == 1 and t_conf.shape[-1] == 1:
                            s_conf_2d = s_conf.squeeze(-1)  # (B, H, W)
                            t_conf_2d = t_conf.squeeze(-1)  # (B, H, W)
                            # 如果H、W不同，使用插值
                            if s_conf_2d.shape[1:] != t_conf_2d.shape[1:]:
                                t_conf_2d = F.interpolate(
                                    t_conf_2d.unsqueeze(1), 
                                    size=s_conf_2d.shape[1:], 
                                    mode='bilinear', 
                                    align_corners=False
                                ).squeeze(1)
                            losses['conf'] = F.mse_loss(s_conf_2d, t_conf_2d.detach())
                        else:
                            losses['conf'] = torch.tensor(0.0, device=s_pts.device)
                    else:
                        losses['conf'] = torch.tensor(0.0, device=s_pts.device)
                else:
                    losses['conf'] = F.mse_loss(s_conf, t_conf.detach())
            except Exception as e:
                # 如果处理失败，暂时设为0
                print(f"[WARN] Conf loss calculation failed: {e}, setting to 0")
                losses['conf'] = torch.tensor(0.0, device=s_pts.device)
        else:
            losses['conf'] = torch.tensor(0.0, device=s_pts.device)
        
        # 总损失：L_task + L_distill + L_conf
        losses['total'] = (
            self.alpha * losses['task'] +
            self.beta * losses['distill'] +
            self.gamma * losses['conf']
        )
        
        return losses
    
    def update_weights(self, alpha: float = None, beta: float = None, gamma: float = None):
        """更新损失权重（用于课程式蒸馏）"""
        if alpha is not None:
            self.alpha = alpha
        if beta is not None:
            self.beta = beta
        if gamma is not None:
            self.gamma = gamma


# ============ 训练器 ============

class DistillationTrainer:
    """蒸馏训练器（支持DDP分布式训练）"""
    
    def __init__(
        self,
        student: nn.Module,
        teacher: nn.Module,
        train_loader: DataLoader,
        val_loader: DataLoader,
        config: ExperimentConfig,
        device: str = 'cuda',
        is_distributed: bool = False,
        is_main: bool = True,
        train_sampler: DistributedSampler = None,
    ):
        # DDP相关
        self.is_distributed = is_distributed
        self.is_main = is_main
        self.train_sampler = train_sampler
        
        # 模型已经在正确的设备上（DDP包装时已指定device_ids）
        self.student = student
        self.teacher = teacher
        self.teacher.eval()  # Teacher 不更新
        
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.config = config
        self.device = device
        
        # 从配置获取蒸馏参数
        distill_cfg = config.experiment.get('distill', {})
        
        # 蒸馏损失配置（已删除temperature，使用Regr3D_Loss）
        alpha = distill_cfg.get('alpha_task_init', 1.0)
        beta_init = distill_cfg.get('beta_distill_init', 0.5)
        beta = beta_init if isinstance(beta_init, (int, float)) else (beta_init[0] if isinstance(beta_init, list) else 0.5)
        gamma_init = distill_cfg.get('gamma_conf_init', 0.0)
        gamma = gamma_init if isinstance(gamma_init, (int, float)) else (gamma_init[0] if isinstance(gamma_init, list) else 0.0)
        
        self.criterion = DistillationLoss(
            alpha=alpha,
            beta=beta,
            gamma=gamma,
        )
        
        # 优化器
        optim_cfg = config.experiment.get('optim', {})
        lr = optim_cfg.get('lr', 2e-4)
        if isinstance(lr, str):
            lr = float(lr)
        
        self.optimizer = torch.optim.AdamW(
            self.student.parameters(),
            lr=lr,
            weight_decay=float(optim_cfg.get('weight_decay', 0.01)),
        )
        
        # 学习率调度器
        run_cfg = config.experiment.get('run', {})
        self.max_epochs = run_cfg.get('max_epochs', 30)
        
        if optim_cfg.get('sched') == 'cosine':
            self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                self.optimizer, T_max=self.max_epochs
            )
        else:
            self.scheduler = None
        
        # 早停
        self.early_stop_patience = run_cfg.get('early_stop_patience', 3)
        self.best_val_loss = float('inf')
        self.no_improve_count = 0
        
        # 课程式蒸馏
        self.curriculum_pct = distill_cfg.get('curriculum_pct', 0.7)
        self.alpha_init = alpha
        self.alpha_final = distill_cfg.get('alpha_task_final', 0.8)
        self.beta_init = distill_cfg.get('beta_distill_init', 0.5)
        self.beta_final = distill_cfg.get('beta_distill_final', 1.0)
        self.gamma_init = distill_cfg.get('gamma_conf_init', 0.0)
        self.gamma_final = distill_cfg.get('gamma_conf_final', 0.1)
        
        # 梯度裁剪
        self.grad_clip = optim_cfg.get('grad_clip', 1.0)
        
        # 检查点目录
        self.ckpt_dir = config.paths.checkpoints
        self.ckpt_dir.mkdir(parents=True, exist_ok=True)
    
    def train_epoch(self, epoch: int) -> Dict[str, float]:
        """训练一个 epoch"""
        self.student.train()
        
        total_loss = 0.0
        loss_components = {'task': 0.0, 'distill': 0.0, 'conf': 0.0}
        num_batches = 0
        
        for batch in self.train_loader:
            img1 = batch['img1'].to(self.device)
            img2 = batch['img2'].to(self.device)
            gt = {k: v.to(self.device) for k, v in batch.items() if k.startswith('gt_')}
            
            # 构造DUSt3R需要的view格式
            view1 = {
                'img': img1,
                'instance': [f'0_{i}' for i in range(img1.shape[0])],
                'idx': list(range(img1.shape[0]))
            }
            view2 = {
                'img': img2,
                'instance': [f'1_{i}' for i in range(img2.shape[0])],
                'idx': list(range(img2.shape[0]))
            }
            
            # Teacher 前向（不计算梯度）
            with torch.no_grad():
                teacher_res1, teacher_res2 = self.teacher(view1, view2)
                # 提取输出（DUSt3R返回字典）
                teacher_out = {
                    'pts3d': teacher_res1.get('pts3d', teacher_res1.get('pts3d_in_other_view')),
                    'depth': teacher_res1.get('depth'),
                    'conf': teacher_res1.get('conf')
                }
            
            # Student 前向（Student模型可能有不同的接口）
            if hasattr(self.student, 'forward') and 'return_features' in self.student.forward.__code__.co_varnames:
                student_out = self.student(img1, img2, return_features=True)
            else:
                # 如果Student也使用view格式
                student_res1, student_res2 = self.student(view1, view2)
                student_out = {
                    'pts3d': student_res1.get('pts3d', student_res1.get('pts3d_in_other_view')),
                    'depth': student_res1.get('depth'),
                    'conf': student_res1.get('conf')
                }
            
            # 计算损失
            losses = self.criterion(student_out, teacher_out, gt)
            
            # 反向传播
            self.optimizer.zero_grad()
            losses['total'].backward()
            
            if self.grad_clip > 0:
                torch.nn.utils.clip_grad_norm_(self.student.parameters(), self.grad_clip)
            
            self.optimizer.step()
            
            # 累计损失
            total_loss += losses['total'].item()
            for k in loss_components:
                loss_components[k] += losses[k].item()
            num_batches += 1
        
        # 平均
        avg_loss = total_loss / max(num_batches, 1)
        avg_components = {k: v / max(num_batches, 1) for k, v in loss_components.items()}
        
        return {'loss': avg_loss, **avg_components}
    
    @torch.no_grad()
    def validate(self) -> Dict[str, float]:
        """验证"""
        self.student.eval()
        
        total_loss = 0.0
        num_batches = 0
        
        for batch in self.val_loader:
            img1 = batch['img1'].to(self.device)
            img2 = batch['img2'].to(self.device)
            gt = {k: v.to(self.device) for k, v in batch.items() if k.startswith('gt_')}
            
            # 构造DUSt3R需要的view格式
            view1 = {
                'img': img1,
                'instance': [f'0_{i}' for i in range(img1.shape[0])],
                'idx': list(range(img1.shape[0]))
            }
            view2 = {
                'img': img2,
                'instance': [f'1_{i}' for i in range(img2.shape[0])],
                'idx': list(range(img2.shape[0]))
            }
            
            # Teacher 前向
            teacher_res1, teacher_res2 = self.teacher(view1, view2)
            teacher_out = {
                'pts3d': teacher_res1.get('pts3d', teacher_res1.get('pts3d_in_other_view')),
                'depth': teacher_res1.get('depth'),
                'conf': teacher_res1.get('conf')
            }
            
            # Student 前向
            if hasattr(self.student, 'forward') and 'return_features' in self.student.forward.__code__.co_varnames:
                student_out = self.student(img1, img2, return_features=True)
            else:
                student_res1, student_res2 = self.student(view1, view2)
                student_out = {
                    'pts3d': student_res1.get('pts3d', student_res1.get('pts3d_in_other_view')),
                    'depth': student_res1.get('depth'),
                    'conf': student_res1.get('conf')
                }
            
            losses = self.criterion(student_out, teacher_out, gt)
            total_loss += losses['total'].item()
            num_batches += 1
        
        return {'val_loss': total_loss / max(num_batches, 1)}
    
    def update_curriculum(self, epoch: int):
        """更新课程式蒸馏权重"""
        progress = epoch / self.max_epochs
        if progress > self.curriculum_pct:
            # 后期：调整权重
            weight_progress = (progress - self.curriculum_pct) / (1 - self.curriculum_pct)
            alpha = self.alpha_init + (self.alpha_final - self.alpha_init) * weight_progress
            beta = self.beta_init + (self.beta_final - self.beta_init) * weight_progress
            gamma = self.gamma_init + (self.gamma_final - self.gamma_init) * weight_progress
            self.criterion.update_weights(alpha=alpha, beta=beta, gamma=gamma)
    
    def save_checkpoint(self, epoch: int, is_best: bool = False):
        """保存检查点（DDP模型需要用.module获取原始模型）"""
        # 获取原始模型state_dict（DDP包装后需要访问.module）
        raw_student = self.student.module if self.is_distributed else self.student
        
        state = {
            'epoch': epoch,
            'student_state_dict': raw_student.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'best_val_loss': self.best_val_loss,
        }
        
        # 保存最新
        torch.save(state, self.ckpt_dir / 'student_latest.pth')
        
        # 保存最佳
        if is_best:
            torch.save(state, self.ckpt_dir / 'student_best.pth')
            # 单独保存模型（方便加载）
            torch.save(raw_student.state_dict(), self.ckpt_dir / 'student_fp32_best.pth')
    
    def train(self, max_epochs: Optional[int] = None) -> Dict[str, Any]:
        """
        完整训练流程
        
        Returns:
            训练历史
        """
        if max_epochs is not None:
            self.max_epochs = max_epochs
        
        history = {
            'train_loss': [],
            'val_loss': [],
            'lr': [],
        }
        
        if self.is_main:
            print(f"\n{'='*60}")
            print("Starting Distillation Training")
            print(f"{'='*60}")
            print(f"  Max epochs: {self.max_epochs}")
            print(f"  Early stop patience: {self.early_stop_patience}")
            print(f"  Initial beta: {self.criterion.beta}")
            print(f"  Distributed: {self.is_distributed}")
            print(f"{'='*60}\n")
        
        for epoch in range(self.max_epochs):
            # DDP: 设置sampler的epoch以确保每个epoch数据打乱不同
            if self.is_distributed and self.train_sampler is not None:
                self.train_sampler.set_epoch(epoch)
            
            # 更新课程参数
            self.update_curriculum(epoch)
            
            # 训练
            train_metrics = self.train_epoch(epoch)
            
            # 验证
            val_metrics = self.validate()
            
            # 学习率调度
            if self.scheduler:
                self.scheduler.step()
            
            current_lr = self.optimizer.param_groups[0]['lr']
            
            # 记录历史
            history['train_loss'].append(train_metrics['loss'])
            history['val_loss'].append(val_metrics['val_loss'])
            history['lr'].append(current_lr)
            
            # 打印进度（仅主进程）
            if self.is_main:
                print(f"Epoch {epoch+1}/{self.max_epochs} | "
                      f"Train: {train_metrics['loss']:.4f} | "
                      f"Val: {val_metrics['val_loss']:.4f} | "
                      f"LR: {current_lr:.2e} | "
                      f"β: {self.criterion.beta:.2f}")
            
            # 检查是否最佳
            is_best = val_metrics['val_loss'] < self.best_val_loss
            if is_best:
                self.best_val_loss = val_metrics['val_loss']
                self.no_improve_count = 0
            else:
                self.no_improve_count += 1
            
            # 保存检查点（仅主进程）
            if self.is_main:
                self.save_checkpoint(epoch, is_best)
            
            # 早停检查
            if self.no_improve_count >= self.early_stop_patience:
                if self.is_main:
                    print(f"\n[INFO] Early stopping at epoch {epoch+1}")
                break
        
        return history


# ============ Teacher 加载 ============

def setup_dust3r_paths():
    """设置 DUSt3R 和 CroCo 路径"""
    dust3r_path = SCRIPT_DIR.parent / 'third_party' / 'dust3r'
    croco_path = dust3r_path / 'croco'
    
    # 确保 croco/models/__init__.py 存在
    croco_models_init = croco_path / 'models' / '__init__.py'
    if not croco_models_init.exists():
        croco_models_init.parent.mkdir(parents=True, exist_ok=True)
        croco_models_init.touch()
    
    # 添加到 sys.path
    for p in [str(dust3r_path), str(croco_path)]:
        if p not in sys.path:
            sys.path.insert(0, p)


def load_teacher_model(weights_path: str = None, device: str = 'cuda') -> nn.Module:
    """
    加载 Teacher 模型（真实的DUSt3R模型）
    
    Args:
        weights_path: 权重路径（可选，如果为None则从HuggingFace加载）
        device: 设备
    
    Returns:
        加载好的Teacher模型
    """
    setup_dust3r_paths()
    
    try:
        from dust3r.model import AsymmetricCroCo3DStereo
        
        # 如果提供了权重路径且文件存在，从本地加载
        if weights_path and Path(weights_path).exists():
            print(f"[INFO] Loading Teacher from local weights: {weights_path}")
            # 这里需要根据实际权重格式调整加载方式
            model = AsymmetricCroCo3DStereo.from_pretrained(weights_path)
        elif weights_path and weights_path.strip() and weights_path != "null":
            # 权重路径指定但文件不存在，尝试作为HuggingFace模型名
            print(f"[INFO] Local weights not found, trying as HuggingFace model: {weights_path}")
            model = AsymmetricCroCo3DStereo.from_pretrained(weights_path)
        else:
            # 从HuggingFace加载（默认方式）
            model_name = 'naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt'
            print(f"[INFO] Loading Teacher from HuggingFace: {model_name}")
            model = AsymmetricCroCo3DStereo.from_pretrained(model_name)
        
        model = model.to(device)
        model.eval()
        
        # 显式冻结Teacher参数
        for param in model.parameters():
            param.requires_grad = False
        
        params = sum(p.numel() for p in model.parameters())
        print(f"[INFO] Teacher model loaded: {params/1e6:.2f}M parameters (frozen)")
        
        return model
    except Exception as e:
        import traceback
        print(f"[WARN] Failed to load real DUSt3R Teacher: {e}")
        traceback.print_exc()
        print("[WARN] Using Student-L as dummy Teacher for testing")
        model = create_student_model(arch='dust3r_student_l', device=device)
        return model


# ============ 主函数 ============

def main():
    parser = argparse.ArgumentParser(
        description='DUSt3R Knowledge Distillation Training',
    )
    parser = add_common_args(parser)
    parser.add_argument('--teacher-weights', type=str, default=None,
                        help='Teacher 模型权重路径')
    parser.add_argument('--student-arch', type=str, default='dust3r_student_s',
                        help='Student 架构')
    parser.add_argument('--max-epochs', type=int, default=None,
                        help='最大 epoch 数（覆盖配置）')
    parser.add_argument('--batch-size', type=int, default=1,
                        help='批大小')
    parser.add_argument('--output', type=str, default='distill_log',
                        help='输出日志文件名')
    # DDP参数（torchrun自动设置）
    parser.add_argument('--local_rank', type=int, default=-1,
                        help='Local rank for distributed training (set by torchrun)')
    
    args = parser.parse_args()
    
    # 加载配置
    config = config_from_args(args)
    config.paths.ensure_dirs()
    
    # ========== DDP初始化 ==========
    # 检测是否为分布式训练（torchrun会设置环境变量）
    is_distributed = int(os.environ.get('WORLD_SIZE', 1)) > 1
    local_rank = int(os.environ.get('LOCAL_RANK', args.local_rank))
    world_size = int(os.environ.get('WORLD_SIZE', 1))
    rank = int(os.environ.get('RANK', 0))
    
    if is_distributed:
        torch.cuda.set_device(local_rank)
        dist.init_process_group(backend='nccl')
        device = f'cuda:{local_rank}'
        if rank == 0:
            print(f"[DDP] Initialized: world_size={world_size}, using NCCL backend")
    else:
        device = config.device
        if device == 'cuda' and not torch.cuda.is_available():
            print("[WARN] CUDA not available, using CPU")
            device = 'cpu'
    
    # 只在主进程打印
    is_main = (rank == 0)
    
    if is_main:
        print("=" * 60)
        print("DUSt3R Knowledge Distillation")
        print("=" * 60)
        print(f"  Exp ID: {config.exp_id}")
        print(f"  Device: {device}")
        print(f"  Distributed: {is_distributed} (world_size={world_size})")
        print(f"  Dry run: {args.dry_run}")
        print("=" * 60)
    
    # 设置随机种子
    torch.manual_seed(config.seed)
    random.seed(config.seed)
    
    # 加载数据
    data_cfg = config.experiment.get('data', config.workload.get('data', {}))
    img_size = (config.input_shape[2], config.input_shape[3])
    
    if args.dry_run:
        train_dataset = PairDataset(
            pairs_list="", dummy=True, num_dummy=50, img_size=img_size
        )
        val_dataset = PairDataset(
            pairs_list="", dummy=True, num_dummy=20, img_size=img_size
        )
    else:
        train_dataset = PairDataset(
            pairs_list=data_cfg.get('train_set', 'datasets/train_pairs.lst'),
            img_size=img_size,
        )
        val_dataset = PairDataset(
            pairs_list=data_cfg.get('val_set', 'datasets/val_pairs.lst'),
            img_size=img_size,
        )
        
        # 如果数据集为空，使用虚拟数据
        if len(train_dataset) == 0:
            print("[WARN] No training data, using dummy data")
            train_dataset = PairDataset(
                pairs_list="", dummy=True, num_dummy=50, img_size=img_size
            )
            val_dataset = PairDataset(
                pairs_list="", dummy=True, num_dummy=20, img_size=img_size
            )
    
    # 创建DataLoader（分布式训练使用DistributedSampler）
    num_workers = 0 if args.dry_run else data_cfg.get('num_workers', 4)
    
    if is_distributed:
        train_sampler = DistributedSampler(train_dataset, shuffle=True)
        val_sampler = DistributedSampler(val_dataset, shuffle=False)
        train_loader = DataLoader(
            train_dataset,
            batch_size=args.batch_size,
            sampler=train_sampler,
            num_workers=num_workers,
            pin_memory=True,
        )
        val_loader = DataLoader(
            val_dataset,
            batch_size=args.batch_size,
            sampler=val_sampler,
            num_workers=num_workers,
            pin_memory=True,
        )
    else:
        train_sampler = None
        val_sampler = None
        train_loader = DataLoader(
            train_dataset,
            batch_size=args.batch_size,
            shuffle=True,
            num_workers=num_workers,
        )
        val_loader = DataLoader(
            val_dataset,
            batch_size=args.batch_size,
            shuffle=False,
            num_workers=num_workers,
        )
    
    if is_main:
        print(f"[INFO] Train samples: {len(train_dataset)}, Val samples: {len(val_dataset)}")
    
    # 加载 Teacher（使用真实的DUSt3R模型）
    teacher_cfg = config.experiment.get('teacher', {})
    teacher_weights = args.teacher_weights or teacher_cfg.get('weights')
    
    if is_main:
        print("[INFO] Loading Teacher model (real DUSt3R from HuggingFace)...")
    teacher = load_teacher_model(weights_path=teacher_weights, device=device)
    
    # 创建 Student
    student_cfg = config.experiment.get('student', {})
    student_arch = args.student_arch or student_cfg.get('arch', 'dust3r_student_s')
    student_config = student_cfg.get('student_config')
    
    student = create_student_model(
        arch=student_arch,
        config_dict=student_config,
        device=device,
    )
    
    # ========== DDP模型包装 ==========
    if is_distributed:
        # 关键：DDP可以处理字典输入，因为它包装的是module而不是数据
        # 每个进程独立处理自己的数据分片
        student = DDP(student, device_ids=[local_rank], output_device=local_rank)
        # Teacher不需要DDP（不参与训练，只做推理）
        if is_main:
            print(f"[DDP] Student wrapped with DistributedDataParallel")
    
    # 打印模型统计（跳过FLOPs计算以避免trace错误）
    if is_main:
        print("\n[INFO] Model Statistics:")
        try:
            # DDP包装后需要访问.module获取原始模型
            raw_student = student.module if is_distributed else student
            teacher_stats = get_model_stats(teacher, config.input_shape, device, measure_vram_flag=False)
            student_stats = get_model_stats(raw_student, config.input_shape, device, measure_vram_flag=False)
            print(f"  Teacher: {teacher_stats}")
            print(f"  Student: {student_stats}")
            print(f"  Compression: {student_stats.params_M / teacher_stats.params_M * 100:.1f}% params")
        except Exception as e:
            # 如果FLOPs计算失败，只计算参数量
            from scripts.utils.model_stats import count_parameters
            raw_student = student.module if is_distributed else student
            teacher_params, _ = count_parameters(teacher)
            student_params, _ = count_parameters(raw_student)
            print(f"  Teacher: {teacher_params/1e6:.2f}M parameters")
            print(f"  Student: {student_params/1e6:.2f}M parameters")
            print(f"  Compression: {student_params / teacher_params * 100:.1f}% params")
            print(f"  [WARN] FLOPs calculation skipped due to: {type(e).__name__}")
    
    # 创建训练器（传入DDP相关参数）
    trainer = DistillationTrainer(
        student=student,
        teacher=teacher,
        train_loader=train_loader,
        val_loader=val_loader,
        config=config,
        device=device,
        is_distributed=is_distributed,
        is_main=is_main,
        train_sampler=train_sampler,
    )
    
    # 训练
    max_epochs = args.max_epochs or config.get_max_epochs('distill')
    if args.dry_run:
        max_epochs = min(max_epochs, 2)
    
    # 发送实验开始通知（仅主进程）
    if is_main:
        try:
            from scripts.experiment_notifier import notify_completion
            raw_student = student.module if is_distributed else student
            notify_completion(
                "K-only_real_data",
                "running",
                {
                    "message": "实验开始训练",
                    "train_samples": len(train_dataset),
                    "val_samples": len(val_dataset),
                    "teacher_params": f"{sum(p.numel() for p in teacher.parameters())/1e6:.2f}M",
                    "student_params": f"{sum(p.numel() for p in raw_student.parameters())/1e6:.2f}M",
                    "max_epochs": max_epochs,
                    "distributed": is_distributed,
                    "world_size": world_size,
                }
            )
        except Exception as e:
            print(f"[WARN] 通知发送失败: {e}")
    
    start_time = datetime.now()
    history = trainer.train(max_epochs=max_epochs)
    elapsed_hours = (datetime.now() - start_time).total_seconds() / 3600
    
    # 以下仅在主进程执行
    if is_main:
        # 加载最佳模型进行最终评测
        raw_student = student.module if is_distributed else student
        best_path = config.paths.checkpoints / 'student_fp32_best.pth'
        if best_path.exists():
            raw_student.load_state_dict(torch.load(best_path, map_location=device))
        
        # 计算最终统计（跳过FLOPs避免trace错误）
        try:
            final_stats = get_model_stats(raw_student, config.input_shape, device, measure_vram_flag=False)
        except Exception as e:
            # Student模型的forward需要两个view，FLOPs计算会失败
            from scripts.utils.model_stats import count_parameters, ModelStats
            params, trainable = count_parameters(raw_student)
            final_stats = ModelStats(
                params_M=params / 1e6,
                params_trainable_M=trainable / 1e6,
                flops_G=0.0,  # 跳过FLOPs
                size_MB=params * 4 / 1024 / 1024,  # FP32估算
                vram_GB=0.0,
            )
            print(f"[WARN] Final stats FLOPs skipped: {type(e).__name__}")
        
        # 创建日志
        distill_cfg = config.experiment.get('distill', {})
        log = ExperimentLog(
            exp_id=f"K_only_{config.seed}",
            combo="K-only",
            seed=config.seed,
            dataset_id=data_cfg.get('dataset_id', 'unknown'),
            split=data_cfg.get('split', 'train'),
            
            # 超参数
            beta=distill_cfg.get('beta_distill_init', 0.5),
            gamma=distill_cfg.get('gamma_conf_init', 0.0),
            
            # 资源
            params_M=final_stats.params_M,
            flops_G=final_stats.flops_G,
            size_MB=final_stats.size_MB,
            vram_GB=final_stats.vram_GB,
            
            # 质量（需要实际评测填充）
            chamfer=0.0,
            absrel=0.0,
            rmse=0.0,
            delta1=0.0,
            reproj_px=0.0,
            
            # 效率（训练后评测填充）
            t_pair_p50_ms=0.0,
            t_pair_p95_ms=0.0,
            t_scene_s=0.0,
            pairs_per_sec=0.0,
            
            # 元信息
            gpu_hours=elapsed_hours,
            notes=f"{'[DRY-RUN] ' if args.dry_run else ''}K-only distillation, final val_loss={history['val_loss'][-1]:.4f}",
        )
        
        # 保存日志
        output_paths = save_experiment_log(
            log=log,
            log_dir=config.paths.logs,
            also_csv=True,
        )
        
        print("\n" + "=" * 60)
        print("Training Complete!")
        print(f"  Best checkpoint: {config.paths.checkpoints / 'student_fp32_best.pth'}")
        print(f"  JSON log: {output_paths['json']}")
        print(f"  GPU hours: {elapsed_hours:.2f}h")
        print("=" * 60)
        
        # 发送实验完成通知
        try:
            from scripts.experiment_notifier import notify_completion
            best_loss = min(history['val_loss']) if history['val_loss'] else float('inf')
            notify_completion(
                "K-only_real_data",
                "success",
                {
                    "message": "实验训练完成",
                    "best_val_loss": f"{best_loss:.6f}",
                    "total_epochs": len(history['val_loss']),
                    "elapsed_hours": f"{elapsed_hours:.2f}",
                    "checkpoint": str(config.paths.checkpoints / 'student_fp32_best.pth'),
                    "log_file": str(output_paths['json']),
                }
            )
        except Exception as e:
            print(f"[WARN] 完成通知发送失败: {e}")
    
    # DDP cleanup
    if is_distributed:
        dist.destroy_process_group()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
