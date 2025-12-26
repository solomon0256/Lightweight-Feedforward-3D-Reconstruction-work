#!/usr/bin/env python3
"""
7-Scenes 数据集准备脚本

按照 DUSt3R 官方 visloc 评测要求准备 7-Scenes 数据集：
https://github.com/naver/dust3r/tree/main/dust3r_visloc/README.md

步骤：
1. 从 Microsoft 官方下载 7-Scenes 数据集
2. 使用 kapture 转换为 kapture 格式
3. 生成 pairsfile

数据集来源: https://www.microsoft.com/en-us/research/project/rgb-d-dataset-7-scenes/
"""

import os
import sys
import subprocess
import urllib.request
from pathlib import Path
import zipfile

# 7-Scenes 场景列表
SCENES = ['chess', 'fire', 'heads', 'office', 'pumpkin', 'redkitchen', 'stairs']

# 下载链接
BASE_URL = "http://download.microsoft.com/download/2/8/5/28564B23-0828-408F-8631-23B1EFF1DAC8"

def download_scene(scene: str, output_dir: Path):
    """下载单个场景"""
    url = f"{BASE_URL}/{scene}.zip"
    output_file = output_dir / f"{scene}.zip"
    
    if output_file.exists():
        print(f"[跳过] {scene}.zip 已存在")
        return output_file
    
    print(f"[下载] {scene} 从 {url}")
    print(f"       目标: {output_file}")
    
    try:
        # 使用 urllib 下载
        urllib.request.urlretrieve(url, output_file, reporthook=download_progress)
        print()  # 换行
        return output_file
    except Exception as e:
        print(f"[错误] 下载失败: {e}")
        return None

def download_progress(count, block_size, total_size):
    """显示下载进度"""
    percent = int(count * block_size * 100 / total_size)
    print(f"\r       进度: {percent}%", end='', flush=True)

def extract_scene(zip_path: Path, output_dir: Path):
    """解压场景"""
    scene_name = zip_path.stem
    scene_dir = output_dir / scene_name
    
    if scene_dir.exists() and any(scene_dir.iterdir()):
        print(f"[跳过] {scene_name} 已解压")
        return scene_dir
    
    print(f"[解压] {zip_path.name}")
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(output_dir)
        
        # 解压内部的 seq-XX.zip 文件
        for inner_zip in scene_dir.glob("*.zip"):
            print(f"       解压内部: {inner_zip.name}")
            with zipfile.ZipFile(inner_zip, 'r') as zf:
                zf.extractall(scene_dir)
            inner_zip.unlink()  # 删除内部 zip
        
        return scene_dir
    except Exception as e:
        print(f"[错误] 解压失败: {e}")
        return None

def convert_to_kapture(scene_dir: Path, kapture_dir: Path):
    """使用 kapture 转换数据集"""
    scene_name = scene_dir.name
    
    mapping_dir = kapture_dir / scene_name / "mapping"
    query_dir = kapture_dir / scene_name / "query"
    
    if mapping_dir.exists() and query_dir.exists():
        print(f"[跳过] {scene_name} kapture 已存在")
        return True
    
    print(f"[转换] {scene_name} -> kapture 格式")
    
    try:
        # 转换 mapping
        cmd_mapping = [
            sys.executable, "-m", "kapture.converter.import_7scenes",
            "-i", str(scene_dir),
            "-o", str(mapping_dir),
            "-p", "mapping",
            "--image_transfer", "copy"
        ]
        print(f"       运行: kapture_import_7scenes.py -p mapping")
        result = subprocess.run(cmd_mapping, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[警告] mapping 转换输出: {result.stderr}")
        
        # 转换 query
        cmd_query = [
            sys.executable, "-m", "kapture.converter.import_7scenes",
            "-i", str(scene_dir),
            "-o", str(query_dir),
            "-p", "query",
            "--image_transfer", "copy"
        ]
        print(f"       运行: kapture_import_7scenes.py -p query")
        result = subprocess.run(cmd_query, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[警告] query 转换输出: {result.stderr}")
        
        return True
    except Exception as e:
        print(f"[错误] kapture 转换失败: {e}")
        print("请确保已安装 kapture: pip install kapture")
        return False

def check_dependencies():
    """检查依赖"""
    print("=" * 60)
    print("检查依赖...")
    print("=" * 60)
    
    # 检查 kapture
    try:
        import kapture
        print(f"✓ kapture 已安装")
    except ImportError:
        print("✗ kapture 未安装")
        print("  请运行: pip install kapture kapture-localization")
        return False
    
    return True

def main():
    import argparse
    parser = argparse.ArgumentParser(description='准备 7-Scenes 数据集 (DUSt3R 官方格式)')
    parser.add_argument('--output', type=str, default='datasets/7-scenes',
                        help='输出目录')
    parser.add_argument('--scenes', nargs='+', default=['heads'],
                        choices=SCENES + ['all'],
                        help='要下载的场景 (默认: heads)')
    parser.add_argument('--skip-download', action='store_true',
                        help='跳过下载步骤')
    parser.add_argument('--skip-kapture', action='store_true',
                        help='跳过 kapture 转换')
    args = parser.parse_args()
    
    # 处理场景列表
    if 'all' in args.scenes:
        scenes = SCENES
    else:
        scenes = args.scenes
    
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("7-Scenes 数据集准备脚本")
    print("=" * 60)
    print(f"输出目录: {output_dir}")
    print(f"场景列表: {scenes}")
    print()
    
    # 检查依赖
    if not args.skip_kapture:
        if not check_dependencies():
            print("\n请先安装依赖后重试")
            return 1
    
    # 下载和解压
    if not args.skip_download:
        print()
        print("=" * 60)
        print("步骤 1: 下载数据集")
        print("=" * 60)
        
        for scene in scenes:
            zip_path = download_scene(scene, output_dir)
            if zip_path:
                extract_scene(zip_path, output_dir)
    
    # 转换为 kapture 格式
    if not args.skip_kapture:
        print()
        print("=" * 60)
        print("步骤 2: 转换为 kapture 格式")
        print("=" * 60)
        
        kapture_dir = output_dir
        for scene in scenes:
            scene_dir = output_dir / scene
            if scene_dir.exists():
                convert_to_kapture(scene_dir, kapture_dir)
            else:
                print(f"[跳过] {scene} 目录不存在")
    
    print()
    print("=" * 60)
    print("完成!")
    print("=" * 60)
    print()
    print("数据集结构应该如下:")
    print(f"  {output_dir}/")
    print(f"  ├── heads/")
    print(f"  │   ├── mapping/")
    print(f"  │   │   └── sensors/")
    print(f"  │   │       ├── records_camera.txt")
    print(f"  │   │       ├── sensors.txt")
    print(f"  │   │       ├── trajectories.txt")
    print(f"  │   │       └── records_data/  (图像)")
    print(f"  │   ├── query/")
    print(f"  │   │   └── sensors/...")
    print(f"  │   └── pairsfile/query/  (需要单独生成)")
    print()
    print("运行 DUSt3R visloc 评测:")
    print(f"  python visloc.py --model_name DUSt3R_ViTLarge_BaseDecoder_512_dpt \\")
    print(f"    --dataset \"VislocSevenScenes('{output_dir}/', subscene='heads', pairsfile='APGeM-LM18_top20', topk=1)\" \\")
    print(f"    --pnp_mode poselib --reprojection_error_diag_ratio 0.008")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
