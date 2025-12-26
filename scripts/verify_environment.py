"""
环境验证脚本
用于验证实验环境是否正确配置
"""
import json
import sys
from pathlib import Path

def verify_environment():
    print("=" * 50)
    print("环境验证")
    print("=" * 50)
    
    errors = []
    warnings = []
    
    # === Python 版本 ===
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"\n[1/6] Python 版本: {py_ver}")
    if sys.version_info < (3, 10):
        errors.append(f"Python 版本过低: {py_ver}, 需要 >= 3.10")
    
    # === PyTorch ===
    try:
        import torch
        print(f"[2/6] PyTorch 版本: {torch.__version__}")
        
        if torch.cuda.is_available():
            print(f"      CUDA 可用: ✅")
            print(f"      GPU: {torch.cuda.get_device_name(0)}")
            print(f"      CUDA 版本: {torch.version.cuda}")
            print(f"      cuDNN 版本: {torch.backends.cudnn.version()}")
            
            # 测试 GPU 计算
            x = torch.randn(100, 100, device='cuda')
            y = torch.matmul(x, x)
            print(f"      GPU 计算测试: ✅")
        else:
            errors.append("CUDA 不可用!")
    except ImportError:
        errors.append("PyTorch 未安装")
    
    # === DUSt3R ===
    print(f"\n[3/6] DUSt3R 模块...")
    try:
        # 添加 DUSt3R 路径
        dust3r_path = Path(__file__).parent.parent / "third_party" / "dust3r"
        if str(dust3r_path) not in sys.path:
            sys.path.insert(0, str(dust3r_path))
        
        from dust3r.model import AsymmetricCroCo3DStereo
        from dust3r.inference import inference
        print(f"      DUSt3R 导入: ✅")
    except ImportError as e:
        errors.append(f"DUSt3R 导入失败: {e}")
    
    # === 关键依赖 ===
    print(f"\n[4/6] 关键依赖...")
    deps = ['numpy', 'cv2', 'PIL', 'scipy', 'einops', 'roma', 'tqdm']
    for dep in deps:
        try:
            __import__(dep if dep != 'cv2' else 'cv2', fromlist=[''])
            print(f"      {dep}: ✅")
        except ImportError:
            errors.append(f"{dep} 未安装")
    
    # === 模型权重 ===
    print(f"\n[5/6] 模型权重...")
    cache_path = Path.home() / ".cache/huggingface/hub/models--naver--DUSt3R_ViTLarge_BaseDecoder_512_dpt"
    if cache_path.exists():
        print(f"      HuggingFace cache: ✅")
    else:
        warnings.append("模型权重未缓存，首次运行会自动下载")
    
    # === 配置文件 ===
    print(f"\n[6/6] 配置文件...")
    config_dir = Path(__file__).parent.parent / "config"
    required_files = ['environment_snapshot.json', 'requirements_freeze.txt']
    for f in required_files:
        if (config_dir / f).exists():
            print(f"      {f}: ✅")
        else:
            warnings.append(f"配置文件缺失: {f}")
    
    # === 结果 ===
    print("\n" + "=" * 50)
    if errors:
        print("❌ 验证失败!")
        print("\n错误:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("✅ 环境验证通过!")
    
    if warnings:
        print("\n⚠️ 警告:")
        for w in warnings:
            print(f"  - {w}")
    
    print("=" * 50)
    return len(errors) == 0

if __name__ == "__main__":
    success = verify_environment()
    sys.exit(0 if success else 1)
