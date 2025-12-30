#!/usr/bin/env python3
"""
蒸馏训练脚本 - K-only

用途：
- 训练轻量 Student 模型逼近 Teacher
- 使用 KL 散度 + 可选特征蒸馏损失
- 支持课程式蒸馏（前期任务损失为主，后期增加 KD 权重）

运行示例：
    python scripts/train_distill.py --exp-config distill.yaml
    python scripts/train_distill.py --dry-run --max-epochs 2
"""

import argparse
import sys
import json
import random
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple, Any

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

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

class DistillationLoss(nn.Module):
    """
    蒸馏损失
    
    L = α * L_task + β * L_kd + γ * L_fd
    
    - L_task: 任务损失（MSE on pts3d）
    - L_kd: KL 散度（soft targets）
    - L_fd: 特征蒸馏（MSE on features）
    """
    
    def __init__(
        self,
        alpha: float = 1.0,
        beta: float = 0.5,
        gamma: float = 0.0,
        temperature: float = 3.0,
    ):
        super().__init__()
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.temperature = temperature
    
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
                'kd': KL 散度损失,
                'fd': 特征蒸馏损失,
            }
        """
        losses = {}
        
        # 任务损失
        s_pts = student_output['pts3d']
        t_pts = teacher_output['pts3d']
        
        if gt is not None and 'gt_pts3d' in gt:
            # 使用 GT 计算任务损失
            losses['task'] = F.mse_loss(s_pts, gt['gt_pts3d'])
        else:
            # 使用 Teacher 输出作为目标
            losses['task'] = F.mse_loss(s_pts, t_pts.detach())
        
        # KL 散度（soft targets）
        # 将 pts3d 展平后计算 softmax
        s_flat = s_pts.flatten(1)  # (B, -1)
        t_flat = t_pts.flatten(1)
        
        s_log_prob = F.log_softmax(s_flat / self.temperature, dim=-1)
        t_prob = F.softmax(t_flat / self.temperature, dim=-1)
        
        losses['kd'] = F.kl_div(s_log_prob, t_prob.detach(), reduction='batchmean') * (self.temperature ** 2)
        
        # 特征蒸馏
        if self.gamma > 0 and 'features' in student_output and 'features' in teacher_output:
            s_feat = student_output['features']
            t_feat = teacher_output['features']
            
            # 如果维度不匹配，需要投影
            if s_feat.shape != t_feat.shape:
                # 简单方案：取平均
                s_feat = s_feat.mean(dim=1)
                t_feat = t_feat.mean(dim=1)
            
            losses['fd'] = F.mse_loss(s_feat, t_feat.detach())
        else:
            losses['fd'] = torch.tensor(0.0, device=s_pts.device)
        
        # 总损失
        losses['total'] = (
            self.alpha * losses['task'] +
            self.beta * losses['kd'] +
            self.gamma * losses['fd']
        )
        
        return losses
    
    def update_beta(self, new_beta: float):
        """更新 KD 权重（用于课程式蒸馏）"""
        self.beta = new_beta


# ============ 训练器 ============

class DistillationTrainer:
    """蒸馏训练器"""
    
    def __init__(
        self,
        student: nn.Module,
        teacher: nn.Module,
        train_loader: DataLoader,
        val_loader: DataLoader,
        config: ExperimentConfig,
        device: str = 'cuda',
    ):
        self.student = student.to(device)
        self.teacher = teacher.to(device)
        self.teacher.eval()  # Teacher 不更新
        
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.config = config
        self.device = device
        
        # 从配置获取蒸馏参数
        distill_cfg = config.experiment.get('distill', {})
        
        # 获取第一个温度值（如果是列表）
        temp_list = distill_cfg.get('kd_temperature', [3.0])
        temperature = temp_list[0] if isinstance(temp_list, list) else temp_list
        
        beta_list = distill_cfg.get('beta_kd', [0.5])
        beta = beta_list[0] if isinstance(beta_list, list) else beta_list
        
        gamma_list = distill_cfg.get('gamma_fd', [0.0])
        gamma = gamma_list[0] if isinstance(gamma_list, list) else gamma_list
        
        self.criterion = DistillationLoss(
            alpha=1.0,
            beta=beta,
            gamma=gamma,
            temperature=temperature,
        )
        
        # 优化器
        optim_cfg = config.experiment.get('optim', {})
        self.optimizer = torch.optim.AdamW(
            self.student.parameters(),
            lr=optim_cfg.get('lr', 2e-4),
            weight_decay=optim_cfg.get('weight_decay', 0.01),
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
        self.curriculum_pct = distill_cfg.get('curriculum_pct_task_first', 0.7)
        self.beta_init = beta
        self.beta_final = beta_list[-1] if isinstance(beta_list, list) and len(beta_list) > 1 else beta * 1.4
        
        # 梯度裁剪
        self.grad_clip = optim_cfg.get('grad_clip', 1.0)
        
        # 检查点目录
        self.ckpt_dir = config.paths.checkpoints
        self.ckpt_dir.mkdir(parents=True, exist_ok=True)
    
    def train_epoch(self, epoch: int) -> Dict[str, float]:
        """训练一个 epoch"""
        self.student.train()
        
        total_loss = 0.0
        loss_components = {'task': 0.0, 'kd': 0.0, 'fd': 0.0}
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
        """更新课程式蒸馏参数"""
        progress = epoch / self.max_epochs
        
        if progress > self.curriculum_pct:
            # 后段：增加 KD 权重
            beta_progress = (progress - self.curriculum_pct) / (1 - self.curriculum_pct)
            new_beta = self.beta_init + (self.beta_final - self.beta_init) * beta_progress
            self.criterion.update_beta(new_beta)
    
    def save_checkpoint(self, epoch: int, is_best: bool = False):
        """保存检查点"""
        state = {
            'epoch': epoch,
            'student_state_dict': self.student.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'best_val_loss': self.best_val_loss,
        }
        
        # 保存最新
        torch.save(state, self.ckpt_dir / 'student_latest.pth')
        
        # 保存最佳
        if is_best:
            torch.save(state, self.ckpt_dir / 'student_best.pth')
            # 单独保存模型（方便加载）
            torch.save(self.student.state_dict(), self.ckpt_dir / 'student_fp32_best.pth')
    
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
        
        print(f"\n{'='*60}")
        print("Starting Distillation Training")
        print(f"{'='*60}")
        print(f"  Max epochs: {self.max_epochs}")
        print(f"  Early stop patience: {self.early_stop_patience}")
        print(f"  Initial beta: {self.criterion.beta}")
        print(f"  Temperature: {self.criterion.temperature}")
        print(f"{'='*60}\n")
        
        for epoch in range(self.max_epochs):
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
            
            # 打印进度
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
            
            # 保存检查点
            self.save_checkpoint(epoch, is_best)
            
            # 早停检查
            if self.no_improve_count >= self.early_stop_patience:
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
        
        params = sum(p.numel() for p in model.parameters())
        print(f"[INFO] Teacher model loaded: {params/1e6:.2f}M parameters")
        
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
    
    args = parser.parse_args()
    
    # 加载配置
    config = config_from_args(args)
    config.paths.ensure_dirs()
    
    print("=" * 60)
    print("DUSt3R Knowledge Distillation")
    print("=" * 60)
    print(f"  Exp ID: {config.exp_id}")
    print(f"  Device: {config.device}")
    print(f"  Dry run: {args.dry_run}")
    print("=" * 60)
    
    # 设备
    device = config.device
    if device == 'cuda' and not torch.cuda.is_available():
        print("[WARN] CUDA not available, using CPU")
        device = 'cpu'
    
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
    
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=0 if args.dry_run else data_cfg.get('num_workers', 4),
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=0 if args.dry_run else data_cfg.get('num_workers', 4),
    )
    
    print(f"[INFO] Train samples: {len(train_dataset)}, Val samples: {len(val_dataset)}")
    
    # 加载 Teacher（使用真实的DUSt3R模型）
    teacher_cfg = config.experiment.get('teacher', {})
    teacher_weights = args.teacher_weights or teacher_cfg.get('weights')
    
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
    
    # 打印模型统计（跳过FLOPs计算以避免trace错误）
    print("\n[INFO] Model Statistics:")
    try:
        teacher_stats = get_model_stats(teacher, config.input_shape, device, measure_vram_flag=False)
        student_stats = get_model_stats(student, config.input_shape, device, measure_vram_flag=False)
        print(f"  Teacher: {teacher_stats}")
        print(f"  Student: {student_stats}")
        print(f"  Compression: {student_stats.params_M / teacher_stats.params_M * 100:.1f}% params")
    except Exception as e:
        # 如果FLOPs计算失败，只计算参数量
        from scripts.utils.model_stats import count_parameters
        teacher_params, _ = count_parameters(teacher)
        student_params, _ = count_parameters(student)
        print(f"  Teacher: {teacher_params/1e6:.2f}M parameters")
        print(f"  Student: {student_params/1e6:.2f}M parameters")
        print(f"  Compression: {student_params / teacher_params * 100:.1f}% params")
        print(f"  [WARN] FLOPs calculation skipped due to: {type(e).__name__}")
    
    # 创建训练器
    trainer = DistillationTrainer(
        student=student,
        teacher=teacher,
        train_loader=train_loader,
        val_loader=val_loader,
        config=config,
        device=device,
    )
    
    # 训练
    max_epochs = args.max_epochs or config.get_max_epochs('distill')
    if args.dry_run:
        max_epochs = min(max_epochs, 2)
    
    # 发送实验开始通知
    try:
        from scripts.experiment_notifier import notify_completion
        notify_completion(
            "K-only_real_data",
            "running",
            {
                "message": "实验开始训练",
                "train_samples": len(train_dataset),
                "val_samples": len(val_dataset),
                "teacher_params": f"{sum(p.numel() for p in teacher.parameters())/1e6:.2f}M",
                "student_params": f"{sum(p.numel() for p in student.parameters())/1e6:.2f}M",
                "max_epochs": max_epochs,
            }
        )
    except Exception as e:
        print(f"[WARN] 通知发送失败: {e}")
    
    start_time = datetime.now()
    history = trainer.train(max_epochs=max_epochs)
    elapsed_hours = (datetime.now() - start_time).total_seconds() / 3600
    
    # 加载最佳模型进行最终评测
    best_path = config.paths.checkpoints / 'student_fp32_best.pth'
    if best_path.exists():
        student.load_state_dict(torch.load(best_path, map_location=device))
    
    final_stats = get_model_stats(student, config.input_shape, device)
    
    # 创建日志
    distill_cfg = config.experiment.get('distill', {})
    log = ExperimentLog(
        exp_id=f"K_only_{config.seed}",
        combo="K-only",
        seed=config.seed,
        dataset_id=data_cfg.get('dataset_id', 'unknown'),
        split=data_cfg.get('split', 'train'),
        
        # 超参数
        T=distill_cfg.get('kd_temperature', [3.0])[0] if isinstance(distill_cfg.get('kd_temperature'), list) else distill_cfg.get('kd_temperature', 3.0),
        beta=distill_cfg.get('beta_kd', [0.5])[0] if isinstance(distill_cfg.get('beta_kd'), list) else distill_cfg.get('beta_kd', 0.5),
        gamma=distill_cfg.get('gamma_fd', [0.0])[0] if isinstance(distill_cfg.get('gamma_fd'), list) else distill_cfg.get('gamma_fd', 0.0),
        
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
        best_loss = min([h.get('val_loss', float('inf')) for h in history])
        notify_completion(
            "K-only_real_data",
            "success",
            {
                "message": "实验训练完成",
                "best_val_loss": f"{best_loss:.6f}",
                "total_epochs": len(history),
                "elapsed_hours": f"{elapsed_hours:.2f}",
                "checkpoint": str(config.paths.checkpoints / 'student_fp32_best.pth'),
                "log_file": str(output_paths['json']),
            }
        )
    except Exception as e:
        print(f"[WARN] 完成通知发送失败: {e}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
