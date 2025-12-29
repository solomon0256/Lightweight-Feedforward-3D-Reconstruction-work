#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
轻量化结果正确性验证脚本

用途：
- 在工作电脑上快速验证轻量化脚本能否成功运行
- 用少量数据快速跑轻量化流程的一部分
- 验证代码不崩溃、流程正确

运行示例：
    python scripts/verify_lightweight_feasibility.py --method all
    python scripts/verify_lightweight_feasibility.py --method distill
"""

import argparse
import sys
import io
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# 修复Windows编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

# 添加项目根目录到路径
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.baseline_eval import load_dust3r_model, setup_dust3r_paths
from scripts.models import create_student_model
from scripts.utils.model_stats import count_parameters


# ============ 数据集 ============

class DummyPairDataset(Dataset):
    """虚拟图像对数据集（用于快速验证）"""
    
    def __init__(self, num_samples: int = 2, img_size: tuple = (512, 384)):
        self.num_samples = num_samples
        self.img_size = img_size
    
    def __len__(self):
        return self.num_samples
    
    def __getitem__(self, idx):
        return {
            'img1': torch.randn(3, *self.img_size),
            'img2': torch.randn(3, *self.img_size),
            'gt_pts3d': torch.randn(3, *self.img_size),
            'gt_depth': torch.rand(1, *self.img_size),
        }


# ============ 验证函数 ============

def verify_distillation(device: str = 'cuda') -> Dict[str, Any]:
    """
    验证蒸馏：用1-2个图像对，跑2-3个训练step
    
    Returns:
        {
            'passed': bool,
            'losses': [loss1, loss2, loss3],
            'message': str
        }
    """
    print("\n[1/3] 蒸馏验证 (Distillation)")
    print("=" * 60)
    
    try:
        # 1. 设置路径
        setup_dust3r_paths()
        
        # 2. 加载 Teacher 模型
        print("  加载 Teacher 模型...")
        teacher = load_dust3r_model(device=device)
        teacher.eval()
        
        # 3. 创建 Student 模型
        print("  创建 Student 模型...")
        student = create_student_model(arch='dust3r_student_s', device=device)
        student.train()
        
        # 4. 创建虚拟数据集（2个样本）
        dataset = DummyPairDataset(num_samples=2)
        dataloader = DataLoader(dataset, batch_size=1, shuffle=False)
        
        # 5. 设置优化器和损失函数
        optimizer = torch.optim.AdamW(student.parameters(), lr=2e-4)
        criterion = nn.MSELoss()
        
        # 6. 跑3个step，记录loss
        losses = []
        print("  运行3个训练step...")
        
        step_count = 0
        for batch in dataloader:
            if step_count >= 3:
                break
            
            img1 = batch['img1'].to(device)
            img2 = batch['img2'].to(device)
            gt_pts3d = batch['gt_pts3d'].to(device)
            
            # Teacher 前向传播（不更新）
            # DUSt3R需要view格式，包含'img', 'instance', 'idx'
            view1 = {
                'img': img1,
                'instance': ['0'],
                'idx': [0]
            }
            view2 = {
                'img': img2,
                'instance': ['1'],
                'idx': [1]
            }
            with torch.no_grad():
                teacher_output1, teacher_output2 = teacher(view1, view2)
                teacher_output = teacher_output1  # 取第一个view的输出
                if isinstance(teacher_output, dict):
                    teacher_pts = teacher_output.get('pts3d')
                    if teacher_pts is None:
                        teacher_pts = teacher_output.get('depth') or list(teacher_output.values())[0]
                else:
                    teacher_pts = teacher_output
            
            # Student 前向传播（Student模型直接接受tensor）
            student_output = student(img1, img2)
            if isinstance(student_output, dict):
                student_pts = student_output.get('pts3d', student_output.get('depth'))
            else:
                student_pts = student_output
            
            # 处理shape不匹配问题
            # Teacher输出可能是 (B, H, W, 3) 或 (B, 3, H, W)
            # Student输出是 (B, 3, H, W)
            if teacher_pts.dim() == 4:
                # 如果是 (B, H, W, 3)，转换为 (B, 3, H, W)
                if teacher_pts.shape[-1] == 3 and teacher_pts.shape[1] != 3:
                    teacher_pts = teacher_pts.permute(0, 3, 1, 2)  # (B, H, W, 3) -> (B, 3, H, W)
                # 如果channel维度不对，尝试其他方式
                elif teacher_pts.shape[1] != 3:
                    # 可能是其他格式，尝试reshape
                    if teacher_pts.numel() == student_pts.numel():
                        teacher_pts = teacher_pts.reshape(student_pts.shape)
                    else:
                        # 如果大小不匹配，进行插值
                        h, w = student_pts.shape[2], student_pts.shape[3]
                        if teacher_pts.shape[1] == 3:
                            teacher_pts = F.interpolate(teacher_pts, size=(h, w), mode='bilinear', align_corners=False)
                        else:
                            # 尝试找到正确的维度
                            teacher_pts = teacher_pts.view(-1, 3, teacher_pts.shape[1]//3, teacher_pts.shape[2])
                            teacher_pts = F.interpolate(teacher_pts, size=(h, w), mode='bilinear', align_corners=False)
            
            # 确保shape匹配
            if teacher_pts.shape != student_pts.shape:
                # 最后尝试：直接插值到Student的尺寸
                h, w = student_pts.shape[2], student_pts.shape[3]
                if teacher_pts.dim() == 4 and teacher_pts.shape[1] == 3:
                    teacher_pts = F.interpolate(teacher_pts, size=(h, w), mode='bilinear', align_corners=False)
                else:
                    # 如果还是不对，跳过这个step
                    print(f"    Warning: Shape mismatch - Teacher: {teacher_pts.shape}, Student: {student_pts.shape}, skipping...")
                    continue
            
            loss = criterion(student_pts, teacher_pts.detach())
            
            # 反向传播
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            
            loss_val = loss.item()
            losses.append(loss_val)
            print(f"    Step {step_count + 1} Loss: {loss_val:.4f}")
            step_count += 1
        
        # 7. 检查loss是否下降
        if len(losses) >= 2:
            loss_decreased = losses[-1] < losses[0]
            passed = loss_decreased
            
            print(f"\n  Step 1 Loss: {losses[0]:.4f}")
            print(f"  Step {len(losses)} Loss: {losses[-1]:.4f}")
            print(f"  Loss 下降: {'[PASS]' if passed else '[FAIL]'}")
            
            return {
                'passed': passed,
                'losses': losses,
                'message': 'Loss 下降' if passed else 'Loss 未下降'
            }
        else:
            return {
                'passed': False,
                'losses': losses,
                'message': '训练step不足'
            }
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'passed': False,
            'losses': [],
            'message': f'验证失败: {str(e)}'
        }


def verify_quantization(device: str = 'cuda') -> Dict[str, Any]:
    """
    验证量化：用1个图像对，跑一次量化流程
    
    Returns:
        {
            'passed': bool,
            'output_shape': tuple,
            'has_nan': bool,
            'has_inf': bool,
            'message': str
        }
    """
    print("\n[2/3] 量化验证 (Quantization)")
    print("=" * 60)
    
    try:
        # 1. 设置路径
        setup_dust3r_paths()
        
        # 2. 加载模型
        print("  加载模型...")
        model = load_dust3r_model(device=device)
        model.eval()
        
        # 3. 创建虚拟数据集（1个样本）
        dataset = DummyPairDataset(num_samples=1)
        dataloader = DataLoader(dataset, batch_size=1)
        
        # 4. 获取一个样本
        batch = next(iter(dataloader))
        img1 = batch['img1'].to(device)
        img2 = batch['img2'].to(device)
        
        # 5. 应用动态量化（INT8，更兼容）
        print("  应用动态量化（INT8）...")
        # 量化模型只能在CPU上运行（PyTorch限制）
        original_device = next(model.parameters()).device
        model_cpu = model.cpu()
        # 只量化Linear层，避免Conv层的问题
        quantized_model = torch.quantization.quantize_dynamic(
            model_cpu,
            {torch.nn.Linear},
            dtype=torch.qint8
        )
        # 量化后的模型必须保持在CPU上（PyTorch量化只支持CPU）
        
        # 6. 构造DUSt3R需要的输入格式（view1和view2字典）
        # DUSt3R需要'img', 'instance', 'idx'等键
        # 输入数据也要移到CPU（量化模型在CPU上）
        img1_cpu = img1.cpu()
        img2_cpu = img2.cpu()
        view1 = {
            'img': img1_cpu,
            'instance': ['0'],
            'idx': [0]
        }
        view2 = {
            'img': img2_cpu,
            'instance': ['1'],
            'idx': [1]
        }
        
        # 7. 运行推理（量化模型必须在CPU上）
        print("  运行量化后模型推理（CPU）...")
        with torch.no_grad():
            output1, output2 = quantized_model(view1, view2)
            # DUSt3R返回两个view的输出，取第一个
            output = output1
        
        # 8. 检查输出（DUSt3R返回字典，包含'pts3d'等）
        if isinstance(output, dict):
            output_tensor = output.get('pts3d')
            if output_tensor is None:
                # 尝试其他键
                output_tensor = output.get('depth') or list(output.values())[0]
        else:
            output_tensor = output
        
        output_shape = tuple(output_tensor.shape)
        has_nan = torch.isnan(output_tensor).any().item()
        has_inf = torch.isinf(output_tensor).any().item()
        
        passed = not has_nan and not has_inf
        
        print(f"  输出 Shape: {output_shape}")
        print(f"  数值有效: {'[无 NaN/Inf]' if passed else '[有 NaN/Inf]'}")
        print(f"  结果: {'[PASS]' if passed else '[FAIL]'}")
        
        return {
            'passed': passed,
            'output_shape': output_shape,
            'has_nan': has_nan,
            'has_inf': has_inf,
            'message': '量化后推理正常' if passed else '量化后推理异常'
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'passed': False,
            'output_shape': None,
            'has_nan': True,
            'has_inf': True,
            'message': f'验证失败: {str(e)}'
        }


def verify_pruning(device: str = 'cuda', target_sparsity: float = 0.4) -> Dict[str, Any]:
    """
    验证剪枝：用1个图像对，跑一次剪枝流程
    
    Returns:
        {
            'passed': bool,
            'target_sparsity': float,
            'actual_sparsity': float,
            'message': str
        }
    """
    print("\n[3/3] 剪枝验证 (Pruning)")
    print("=" * 60)
    
    try:
        # 1. 设置路径
        setup_dust3r_paths()
        
        # 2. 加载模型
        print("  加载模型...")
        model = load_dust3r_model(device=device)
        model.eval()
        
        # 3. 创建虚拟数据集（1个样本）
        dataset = DummyPairDataset(num_samples=1)
        dataloader = DataLoader(dataset, batch_size=1)
        
        # 4. 获取一个样本
        batch = next(iter(dataloader))
        img1 = batch['img1'].to(device)
        img2 = batch['img2'].to(device)
        
        # 5. 应用剪枝（L1非结构化剪枝）
        print(f"  应用剪枝（目标稀疏度: {target_sparsity*100:.0f}%）...")
        import torch.nn.utils.prune as prune
        
        # 找到第一个Linear层进行剪枝
        pruned_module = None
        for name, module in model.named_modules():
            if isinstance(module, nn.Linear) and module.weight.numel() > 10000:
                pruned_module = (name, module)
                break
        
        if pruned_module is None:
            return {
                'passed': False,
                'target_sparsity': target_sparsity,
                'actual_sparsity': 0.0,
                'message': '未找到合适的剪枝层'
            }
        
        name, module = pruned_module
        prune.l1_unstructured(module, name='weight', amount=target_sparsity)
        
        # 6. 计算实际稀疏度
        total_params = module.weight.numel()
        zero_params = (module.weight == 0).sum().item()
        actual_sparsity = zero_params / total_params
        
        # 7. 构造DUSt3R需要的输入格式
        view1 = {
            'img': img1,
            'instance': ['0'],
            'idx': [0]
        }
        view2 = {
            'img': img2,
            'instance': ['1'],
            'idx': [1]
        }
        
        # 8. 运行推理测试
        print("  运行剪枝后模型推理...")
        with torch.no_grad():
            output1, output2 = model(view1, view2)
            output = output1  # 取第一个view的输出
        
        # 8. 检查稀疏度是否达标
        passed = actual_sparsity >= target_sparsity * 0.9  # 允许10%误差
        
        print(f"  目标稀疏度: {target_sparsity*100:.1f}%")
        print(f"  实际稀疏度: {actual_sparsity*100:.1f}%")
        print(f"  结果: {'[PASS]' if passed else '[FAIL]'}")
        
        # 清理剪枝（恢复原状）
        prune.remove(module, 'weight')
        
        return {
            'passed': passed,
            'target_sparsity': target_sparsity,
            'actual_sparsity': actual_sparsity,
            'message': '剪枝稀疏度达标' if passed else '剪枝稀疏度未达标'
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'passed': False,
            'target_sparsity': target_sparsity,
            'actual_sparsity': 0.0,
            'message': f'验证失败: {str(e)}'
        }


# ============ 主函数 ============

def main():
    parser = argparse.ArgumentParser(description='验证轻量化脚本能否成功运行')
    parser.add_argument('--method', type=str, default='all',
                       choices=['all', 'distill', 'quantize', 'prune'],
                       help='验证方法: all, distill, quantize, prune')
    parser.add_argument('--device', type=str, default='cuda',
                       choices=['cuda', 'cpu'],
                       help='设备: cuda, cpu')
    parser.add_argument('--target-sparsity', type=float, default=0.4,
                       help='剪枝目标稀疏度 (默认: 0.4)')
    parser.add_argument('--output', type=str, default=None,
                       help='输出JSON报告路径')
    
    args = parser.parse_args()
    
    # 检查设备
    if args.device == 'cuda' and not torch.cuda.is_available():
        print("[WARN] CUDA不可用，使用CPU")
        args.device = 'cpu'
    
    print("=" * 60)
    print("轻量化结果正确性验证报告")
    print("=" * 60)
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'method': args.method,
        'device': args.device,
        'checks': {}
    }
    
    all_passed = True
    
    # 验证蒸馏
    if args.method in ['all', 'distill']:
        distill_result = verify_distillation(device=args.device)
        results['checks']['distillation'] = distill_result
        if not distill_result['passed']:
            all_passed = False
    
    # 验证量化
    if args.method in ['all', 'quantize']:
        quant_result = verify_quantization(device=args.device)
        results['checks']['quantization'] = quant_result
        if not quant_result['passed']:
            all_passed = False
    
    # 验证剪枝
    if args.method in ['all', 'prune']:
        prune_result = verify_pruning(device=args.device, target_sparsity=args.target_sparsity)
        results['checks']['pruning'] = prune_result
        if not prune_result['passed']:
            all_passed = False
    
    # 总结
    print("\n" + "=" * 60)
    results['passed'] = all_passed
    if all_passed:
        print("[SUCCESS] 总结: 所有验证通过 - 可以在服务器运行完整轻量化")
    else:
        print("[FAIL] 总结: 部分验证失败 - 需要修复问题后再运行")
    print("=" * 60)
    
    # 保存结果
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n结果已保存到: {output_path}")
    else:
        # 默认保存路径
        logs_dir = PROJECT_ROOT / 'logs'
        logs_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = logs_dir / f'verify_feasibility_{timestamp}.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n结果已保存到: {output_path}")
    
    # 退出码
    sys.exit(0 if all_passed else 1)


if __name__ == '__main__':
    main()

