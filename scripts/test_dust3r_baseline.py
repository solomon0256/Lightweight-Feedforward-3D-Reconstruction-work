#!/usr/bin/env python3
"""
DUSt3R Baseline 验证脚本
========================
验证 DUSt3R 是否能正常运行

用法:
    python scripts/test_dust3r_baseline.py
    python scripts/test_dust3r_baseline.py --device cuda
    python scripts/test_dust3r_baseline.py --device cpu
"""

import sys
import os
import argparse
import time

# 设置路径 - 顺序很重要！dust3r 必须在 croco 前面
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# 切换到项目根目录
os.chdir(PROJECT_ROOT)

DUST3R_PATH = os.path.join(PROJECT_ROOT, "third_party", "dust3r")
CROCO_PATH = os.path.join(DUST3R_PATH, "croco")

# 确保 croco/models/__init__.py 存在（CRoCo 需要但没有提供）
croco_models_init = os.path.join(CROCO_PATH, "models", "__init__.py")
if not os.path.exists(croco_models_init):
    open(croco_models_init, 'w').close()

# 添加到 Python 路径
sys.path.insert(0, CROCO_PATH)
sys.path.insert(0, DUST3R_PATH)


def test_baseline(device="auto"):
    """运行 baseline 测试"""
    
    print("\n" + "=" * 60)
    print("  DUSt3R Baseline 验证")
    print("=" * 60)
    
    # 自动检测设备
    import torch
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    
    print(f"\nPyTorch: {torch.__version__}")
    print(f"Device: {device}")
    if device == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    
    results = {}
    
    # Test 1: 加载模型
    print("\n" + "-" * 40)
    print("[1/4] 加载模型...")
    print("-" * 40)
    
    try:
        from dust3r.model import AsymmetricCroCo3DStereo
        
        t0 = time.time()
        model = AsymmetricCroCo3DStereo.from_pretrained(
            "naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt"
        )
        model = model.to(device)
        model.eval()
        load_time = time.time() - t0
        
        params = sum(p.numel() for p in model.parameters())
        print(f"✓ 模型加载成功")
        print(f"  参数量: {params:,} ({params/1e6:.1f}M)")
        print(f"  加载耗时: {load_time:.1f}s")
        
        results["model_params"] = params
        results["load_time"] = load_time
        
    except Exception as e:
        print(f"✗ 模型加载失败: {e}")
        return None
    
    # Test 2: 创建测试图像
    print("\n" + "-" * 40)
    print("[2/4] 创建测试图像...")
    print("-" * 40)
    
    import numpy as np
    from PIL import Image
    import tempfile
    
    tmp_dir = tempfile.mkdtemp()
    
    # 创建两张有视差的测试图像
    img1 = np.zeros((384, 512, 3), dtype=np.uint8)
    img1[100:200, 150:350] = [255, 0, 0]   # 红色方块
    img1[200:300, 200:400] = [0, 255, 0]   # 绿色方块
    
    img2 = np.zeros((384, 512, 3), dtype=np.uint8)
    img2[100:200, 170:370] = [255, 0, 0]   # 视差偏移
    img2[200:300, 220:420] = [0, 255, 0]
    
    img1_path = os.path.join(tmp_dir, "view1.png")
    img2_path = os.path.join(tmp_dir, "view2.png")
    Image.fromarray(img1).save(img1_path)
    Image.fromarray(img2).save(img2_path)
    
    print(f"✓ 测试图像已创建")
    print(f"  尺寸: 512x384")
    print(f"  临时目录: {tmp_dir}")
    
    # Test 3: 运行推理
    print("\n" + "-" * 40)
    print("[3/4] 运行推理...")
    print("-" * 40)
    
    try:
        from dust3r.utils.image import load_images
        from dust3r.image_pairs import make_pairs
        from dust3r.inference import inference
        
        imgs = load_images([img1_path, img2_path], size=512, verbose=False)
        pairs = make_pairs(imgs, scene_graph="complete", prefilter=None, symmetrize=True)
        
        print(f"  图像对数量: {len(pairs)}")
        
        # 预热（如果是 GPU）
        if device == "cuda":
            torch.cuda.synchronize()
        
        t0 = time.time()
        with torch.no_grad():
            output = inference(pairs, model, device, batch_size=1, verbose=False)
        
        if device == "cuda":
            torch.cuda.synchronize()
        
        infer_time = time.time() - t0
        
        print(f"✓ 推理完成")
        print(f"  耗时: {infer_time:.2f}s")
        
        results["inference_time"] = infer_time
        
        # 显存占用
        if device == "cuda":
            mem_used = torch.cuda.max_memory_allocated() / 1e9
            print(f"  峰值显存: {mem_used:.2f} GB")
            results["peak_memory_gb"] = mem_used
        
    except Exception as e:
        print(f"✗ 推理失败: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    # Test 4: 验证输出
    print("\n" + "-" * 40)
    print("[4/4] 验证输出格式...")
    print("-" * 40)
    
    try:
        pred1 = output["pred1"]
        pred2 = output["pred2"]
        
        pts3d = pred1["pts3d"]
        conf = pred1["conf"]
        
        print(f"✓ 输出格式正确")
        print(f"  pred1 keys: {list(pred1.keys())}")
        print(f"  pts3d shape: {pts3d.shape}")
        print(f"  conf shape: {conf.shape}")
        print(f"  pts3d range: [{pts3d.min():.3f}, {pts3d.max():.3f}]")
        print(f"  conf range: [{conf.min():.3f}, {conf.max():.3f}]")
        
        results["pts3d_shape"] = list(pts3d.shape)
        results["conf_shape"] = list(conf.shape)
        
    except Exception as e:
        print(f"✗ 输出验证失败: {e}")
        return None
    
    # 清理
    import shutil
    shutil.rmtree(tmp_dir)
    
    # 总结
    print("\n" + "=" * 60)
    print("  ✅ BASELINE 验证通过！")
    print("=" * 60)
    
    print("\n📊 测试结果:")
    print(f"  模型参数: {results['model_params']/1e6:.1f}M")
    print(f"  加载时间: {results['load_time']:.1f}s")
    print(f"  推理时间: {results['inference_time']:.2f}s")
    if "peak_memory_gb" in results:
        print(f"  峰值显存: {results['peak_memory_gb']:.2f} GB")
    print(f"  输出形状: pts3d={results['pts3d_shape']}, conf={results['conf_shape']}")
    
    return results


def main():
    parser = argparse.ArgumentParser(description="DUSt3R Baseline 验证")
    parser.add_argument("--device", type=str, default="auto",
                        choices=["auto", "cuda", "cpu"],
                        help="运行设备 (default: auto)")
    args = parser.parse_args()
    
    results = test_baseline(device=args.device)
    
    if results is None:
        print("\n❌ 测试失败")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
