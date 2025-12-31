#!/usr/bin/env python3
"""诊断Teacher模型加载问题"""

import sys
from pathlib import Path

# 添加路径
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

dust3r_path = PROJECT_ROOT / 'third_party' / 'dust3r'
croco_path = dust3r_path / 'croco'

print("="*60)
print("Teacher模型加载诊断")
print("="*60)

print(f"\n[1] 检查路径:")
print(f"  PROJECT_ROOT: {PROJECT_ROOT}")
print(f"  dust3r_path: {dust3r_path}")
print(f"  croco_path: {croco_path}")
print(f"  dust3r_path.exists(): {dust3r_path.exists()}")
print(f"  croco_path.exists(): {croco_path.exists()}")

print(f"\n[2] 添加路径到sys.path:")
for p in [str(dust3r_path), str(croco_path)]:
    if p not in sys.path:
        sys.path.insert(0, p)
        print(f"  ✅ 添加: {p}")
    else:
        print(f"  ⚠️ 已存在: {p}")

print(f"\n[3] 尝试导入dust3r:")
try:
    from dust3r.model import AsymmetricCroCo3DStereo
    print("  ✅ 导入成功")
except Exception as e:
    print(f"  ❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print(f"\n[4] 尝试加载Teacher模型:")
try:
    model_name = 'naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt'
    print(f"  模型名称: {model_name}")
    model = AsymmetricCroCo3DStereo.from_pretrained(model_name)
    params = sum(p.numel() for p in model.parameters())
    print(f"  ✅ Teacher模型加载成功: {params/1e6:.2f}M参数")
except Exception as e:
    print(f"  ❌ 加载失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*60)
print("✅ 所有检查通过！Teacher模型可以正常加载")
print("="*60)

