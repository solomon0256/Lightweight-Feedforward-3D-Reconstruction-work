#!/usr/bin/env python3
"""
快速准备真实7-Scenes数据集的pairs列表

从7-Scenes原始数据或kapture格式数据创建训练/验证pairs列表
格式: path/to/img1.jpg|path/to/img2.jpg
"""

import os
import sys
from pathlib import Path
import argparse

def find_images_in_dir(root_dir: Path, extensions=['.png', '.jpg', '.jpeg'], only_color=True):
    """递归查找所有图像文件"""
    images = []
    for ext in extensions:
        found = root_dir.rglob(f'*{ext}')
        for img in found:
            # 如果only_color=True，只选择color.png，排除depth.png
            if only_color and 'depth' in str(img).lower():
                continue
            images.append(img)
    return sorted([str(img) for img in images])

def create_pairs_from_7scenes_raw(seven_scenes_root: Path, scene: str = 'heads'):
    """
    从7-Scenes原始数据创建pairs
    
    结构:
    seven_scenes_root/heads/
    ├── seq-01/  (query/test)
    │   ├── frame-000000.color.png
    │   └── ...
    └── seq-02/  (mapping/train)
        ├── frame-000000.color.png
        └── ...
    """
    scene_dir = seven_scenes_root / scene
    
    # 查找mapping (seq-02) 和 query (seq-01) 图像
    mapping_dir = scene_dir / 'seq-02'
    query_dir = scene_dir / 'seq-01'
    
    train_images = []
    val_images = []
    
    if mapping_dir.exists():
        train_images = find_images_in_dir(mapping_dir)
        print(f"[INFO] 找到 {len(train_images)} 张训练图像 (mapping)")
    
    if query_dir.exists():
        val_images = find_images_in_dir(query_dir)
        print(f"[INFO] 找到 {len(val_images)} 张验证图像 (query)")
    
    # 创建训练pairs: mapping内部配对（相邻帧）
    train_pairs = []
    for i in range(len(train_images) - 1):
        train_pairs.append(f"{train_images[i]}|{train_images[i+1]}")
    
    # 创建验证pairs: query内部配对（相邻帧）
    val_pairs = []
    for i in range(len(val_images) - 1):
        val_pairs.append(f"{val_images[i]}|{val_images[i+1]}")
    
    return train_pairs, val_pairs

def create_pairs_from_kapture(kapture_root: Path, scene: str = 'heads'):
    """
    从kapture格式数据创建pairs
    
    结构:
    kapture_root/heads/
    ├── mapping/sensors/records_data/...
    └── query/sensors/records_data/...
    """
    scene_dir = kapture_root / scene
    
    mapping_dir = scene_dir / 'mapping' / 'sensors' / 'records_data'
    query_dir = scene_dir / 'query' / 'sensors' / 'records_data'
    
    train_images = []
    val_images = []
    
    if mapping_dir.exists():
        train_images = find_images_in_dir(mapping_dir)
        print(f"[INFO] 找到 {len(train_images)} 张训练图像 (mapping)")
    
    if query_dir.exists():
        val_images = find_images_in_dir(query_dir)
        print(f"[INFO] 找到 {len(val_images)} 张验证图像 (query)")
    
    # 创建训练pairs: mapping内部配对（相邻帧）
    train_pairs = []
    for i in range(len(train_images) - 1):
        train_pairs.append(f"{train_images[i]}|{train_images[i+1]}")
    
    # 创建验证pairs: query内部配对（相邻帧）
    val_pairs = []
    for i in range(len(val_images) - 1):
        val_pairs.append(f"{val_images[i]}|{val_images[i+1]}")
    
    return train_pairs, val_pairs

def main():
    parser = argparse.ArgumentParser(description='准备真实7-Scenes数据集的pairs列表')
    parser.add_argument('--seven-scenes-root', type=str, default='datasets/7-scenes-raw',
                        help='7-Scenes原始数据根目录')
    parser.add_argument('--kapture-root', type=str, default='datasets/7-scenes',
                        help='Kapture格式数据根目录')
    parser.add_argument('--scene', type=str, default='heads',
                        help='场景名称 (heads, chess, fire, etc.)')
    parser.add_argument('--output-dir', type=str, default='datasets',
                        help='输出pairs列表的目录')
    parser.add_argument('--format', choices=['raw', 'kapture', 'auto'], default='auto',
                        help='数据格式 (auto会自动检测)')
    
    args = parser.parse_args()
    
    project_root = Path(__file__).resolve().parent.parent
    seven_scenes_root = project_root / args.seven_scenes_root
    kapture_root = project_root / args.kapture_root
    output_dir = project_root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("="*60)
    print("准备真实7-Scenes数据集pairs列表")
    print("="*60)
    print(f"场景: {args.scene}")
    print(f"7-Scenes原始数据: {seven_scenes_root}")
    print(f"Kapture数据: {kapture_root}")
    print(f"输出目录: {output_dir}")
    print()
    
    train_pairs = []
    val_pairs = []
    
    # 自动检测数据格式
    if args.format == 'auto':
        scene_raw = seven_scenes_root / args.scene
        scene_kapture = kapture_root / args.scene
        
        if scene_raw.exists() and (scene_raw / 'seq-01').exists():
            print(f"[INFO] 检测到7-Scenes原始数据格式")
            train_pairs, val_pairs = create_pairs_from_7scenes_raw(seven_scenes_root, args.scene)
        elif scene_kapture.exists():
            print(f"[INFO] 检测到Kapture格式数据")
            train_pairs, val_pairs = create_pairs_from_kapture(kapture_root, args.scene)
        else:
            print(f"[ERROR] 未找到数据！")
            print(f"  检查路径: {scene_raw}")
            print(f"  检查路径: {scene_kapture}")
            return 1
    elif args.format == 'raw':
        train_pairs, val_pairs = create_pairs_from_7scenes_raw(seven_scenes_root, args.scene)
    elif args.format == 'kapture':
        train_pairs, val_pairs = create_pairs_from_kapture(kapture_root, args.scene)
    
    # 保存pairs列表
    train_pairs_file = output_dir / 'train_pairs.lst'
    val_pairs_file = output_dir / 'val_pairs.lst'
    
    with open(train_pairs_file, 'w') as f:
        f.write('\n'.join(train_pairs))
    print(f"[INFO] 训练pairs已保存: {train_pairs_file} ({len(train_pairs)} pairs)")
    
    with open(val_pairs_file, 'w') as f:
        f.write('\n'.join(val_pairs))
    print(f"[INFO] 验证pairs已保存: {val_pairs_file} ({len(val_pairs)} pairs)")
    
    print()
    print("="*60)
    print("✅ 完成！")
    print("="*60)
    print(f"训练pairs: {len(train_pairs)}")
    print(f"验证pairs: {len(val_pairs)}")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())

