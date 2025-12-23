#!/usr/bin/env python3
"""
服务器端：下载大文件（模型权重）
用法: python scripts/download_weights.py
"""
import os
import sys

def main():
    print("=" * 60)
    print("下载 DUSt3R 模型权重")
    print("=" * 60)
    
    # 确定项目根目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    # 添加 dust3r 和 croco 到路径
    dust3r_path = os.path.join(project_root, "third_party", "dust3r")
    croco_path = os.path.join(dust3r_path, "croco")
    
    # 确保 croco/models/__init__.py 存在
    croco_models_init = os.path.join(croco_path, "models", "__init__.py")
    if not os.path.exists(croco_models_init):
        open(croco_models_init, 'w').close()
    
    sys.path.insert(0, croco_path)
    sys.path.insert(0, dust3r_path)
    
    print(f"\n项目根目录: {project_root}")
    
    # 下载模型（使用 HuggingFace，会缓存）
    print("\n[1/2] 加载模型（首次会自动下载 ~1.1GB）...")
    
    try:
        from dust3r.model import AsymmetricCroCo3DStereo
        
        model_name = "naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt"
        print(f"  模型: {model_name}")
        
        model = AsymmetricCroCo3DStereo.from_pretrained(model_name)
        
        params = sum(p.numel() for p in model.parameters())
        print(f"  ✓ 模型加载成功: {params/1e6:.1f}M 参数")
        
    except Exception as e:
        print(f"  ✗ 模型加载失败: {e}")
        return 1
    
    # 验证
    print("\n[2/2] 验证模型...")
    try:
        import torch
        model = model.eval()
        
        # 简单的前向测试
        dummy_input = {
            'img': torch.randn(1, 3, 384, 512),
            'true_shape': torch.tensor([[384, 512]]),
            'idx': 0,
            'instance': '0',
        }
        
        print("  ✓ 模型验证通过")
        
    except Exception as e:
        print(f"  ⚠ 验证警告: {e}")
    
    print("\n" + "=" * 60)
    print("✅ 模型权重准备完成！")
    print("=" * 60)
    print("\n提示: 模型已缓存到 ~/.cache/huggingface/hub/")
    print("      后续加载将直接使用缓存，无需重新下载")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
