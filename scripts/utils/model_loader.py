"""
模型加载器 - 统一加载不同变体的模型
"""
import sys
from pathlib import Path
from typing import Optional
import torch
import torch.nn as nn

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.baseline_eval import load_dust3r_model, setup_dust3r_paths


def load_model(method: str, variant: str, device: str = 'cuda', 
               checkpoint_path: Optional[str] = None) -> nn.Module:
    """
    根据 method 和 variant 加载对应模型
    
    Args:
        method: 'Q' (量化), 'K' (蒸馏), 'P' (剪枝), 'baseline' (基线)
        variant: 'fp16', 'int8', 'student', 'pruned_50', etc.
        device: 设备 ('cuda' / 'cpu')
        checkpoint_path: 可选的 checkpoint 路径（用于量化/蒸馏/剪枝模型）
    
    Returns:
        加载好的模型
    """
    setup_dust3r_paths()
    
    if method == 'Q' and variant == 'fp16':
        # FP16 量化：加载 baseline 并转换为 FP16
        print(f"[INFO] Loading baseline model and converting to FP16...")
        model = load_dust3r_model(device=device)
        model = model.half()  # 转换为 FP16
        print(f"[INFO] Model converted to FP16")
    
    elif method == 'Q' and variant == 'int8':
        # INT8 量化：需要从 checkpoint 加载
        if checkpoint_path and Path(checkpoint_path).exists():
            print(f"[INFO] Loading INT8 quantized model from {checkpoint_path}...")
            # TODO: 实现量化模型加载
            # 目前先加载 baseline 作为 fallback
            print(f"[WARN] INT8 model loading not implemented, using baseline")
            model = load_dust3r_model(device=device)
        else:
            print(f"[WARN] Checkpoint not found, loading baseline model")
            model = load_dust3r_model(device=device)
    
    elif method == 'K' and variant == 'student':
        # 蒸馏后的 student 模型
        if checkpoint_path and Path(checkpoint_path).exists():
            print(f"[INFO] Loading student model from {checkpoint_path}...")
            try:
                from scripts.models import create_student_model
                
                # 创建 student 模型架构
                student = create_student_model(arch='dust3r_student_s', device=device)
                
                # 加载权重
                state_dict = torch.load(checkpoint_path, map_location=device)
                if isinstance(state_dict, dict):
                    if 'state_dict' in state_dict:
                        state_dict = state_dict['state_dict']
                    elif 'model' in state_dict:
                        state_dict = state_dict['model']
                
                student.load_state_dict(state_dict, strict=False)
                student.eval()
                model = student
                print(f"[INFO] Student model loaded successfully")
            except Exception as e:
                print(f"[WARN] Failed to load student model: {e}")
                print(f"[WARN] Falling back to baseline model")
                model = load_dust3r_model(device=device)
        else:
            print(f"[WARN] Checkpoint not found, loading baseline model")
            model = load_dust3r_model(device=device)
    
    elif method == 'P':
        # 剪枝模型
        if checkpoint_path and Path(checkpoint_path).exists():
            print(f"[INFO] Loading pruned model from {checkpoint_path}...")
            try:
                # 剪枝后的模型通常与原始模型结构相同，但某些权重为0
                # 先加载 baseline 模型
                model = load_dust3r_model(device=device)
                
                # 加载剪枝后的权重
                state_dict = torch.load(checkpoint_path, map_location=device)
                if isinstance(state_dict, dict):
                    if 'state_dict' in state_dict:
                        state_dict = state_dict['state_dict']
                    elif 'model' in state_dict:
                        state_dict = state_dict['model']
                
                # 加载权重（可能包含稀疏权重）
                model.load_state_dict(state_dict, strict=False)
                model.eval()
                
                # 可选：检查剪枝率（统计非零权重比例）
                total_params = 0
                zero_params = 0
                for param in model.parameters():
                    total_params += param.numel()
                    zero_params += (param == 0).sum().item()
                
                if total_params > 0:
                    sparsity = zero_params / total_params * 100
                    print(f"[INFO] Pruned model loaded, sparsity: {sparsity:.2f}%")
                
                print(f"[INFO] Pruned model loaded successfully")
            except Exception as e:
                print(f"[WARN] Failed to load pruned model: {e}")
                print(f"[WARN] Falling back to baseline model")
                model = load_dust3r_model(device=device)
        else:
            print(f"[WARN] Checkpoint not found, loading baseline model")
            model = load_dust3r_model(device=device)
    
    else:
        # 默认加载 baseline 模型
        print(f"[INFO] Loading baseline model...")
        model = load_dust3r_model(device=device)
    
    model.eval()
    return model

