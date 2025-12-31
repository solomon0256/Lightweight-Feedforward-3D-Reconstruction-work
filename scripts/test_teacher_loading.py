#!/usr/bin/env python3
"""测试Teacher模型加载"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'third_party' / 'dust3r'))

print("="*60)
print("测试Teacher模型加载")
print("="*60)

try:
    print("\n1. 导入模块...")
    from dust3r.model import AsymmetricCroCo3DStereo
    print("   ✅ 模块导入成功")
    
    print("\n2. 加载模型（HuggingFace）...")
    import signal
    
    def timeout_handler(signum, frame):
        raise TimeoutError("模型加载超时（30秒）")
    
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(30)  # 30秒超时
    
    try:
        model_name = 'naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt'
        print(f"   模型名称: {model_name}")
        print("   开始加载（可能需要下载模型）...")
        
        model = AsymmetricCroCo3DStereo.from_pretrained(model_name)
        
        signal.alarm(0)  # 取消超时
        print("   ✅ 模型加载成功")
        
        print("\n3. 移动到GPU...")
        import torch
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        model = model.to(device)
        model.eval()
        print(f"   ✅ 模型已移动到 {device}")
        
        params = sum(p.numel() for p in model.parameters())
        print(f"\n4. 模型信息:")
        print(f"   参数量: {params/1e6:.2f}M")
        print(f"   设备: {device}")
        
        print("\n" + "="*60)
        print("✅ 测试成功！模型可以正常加载")
        print("="*60)
        
    except TimeoutError as e:
        signal.alarm(0)
        print(f"\n❌ {e}")
        print("   模型加载超时，可能是网络问题或模型太大")
        sys.exit(1)
    except Exception as e:
        signal.alarm(0)
        print(f"\n❌ 模型加载失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
        
except Exception as e:
    print(f"\n❌ 导入模块失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


