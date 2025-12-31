#!/usr/bin/env python3
"""
将MegaDepth预处理后的数据转换为训练脚本需要的pairs列表格式

用法:
    python scripts/prepare_megadepth_pairs.py \
        --processed_dir datasets/megadepth_processed \
        --pairs_file datasets/megadepth_pairs.npz \
        --output_train datasets/train_pairs.lst \
        --output_val datasets/val_pairs.lst \
        --train_ratio 0.9
"""

import argparse
import numpy as np
import os
from pathlib import Path
import random

def load_pairs_info(pairs_file):
    """加载DUSt3R提供的pairs文件"""
    data = np.load(pairs_file, allow_pickle=True)
    scenes = data['scenes']
    images = data['images']
    pairs = data['pairs']
    return scenes, images, pairs

def find_image_path(processed_dir, scene_id, image_name):
    """
    在processed目录中查找图像文件
    
    processed_dir结构: processed_dir/<scene>/<subscene>/<image>.jpg
    """
    processed_path = Path(processed_dir)
    
    # 遍历所有scene目录
    for scene_dir in processed_path.iterdir():
        if not scene_dir.is_dir():
            continue
            
        # 在scene/subscene目录中查找
        for subscene_dir in scene_dir.iterdir():
            if not subscene_dir.is_dir():
                continue
                
            img_path = subscene_dir / f"{image_name}.jpg"
            if img_path.exists():
                return str(img_path.absolute())
    
    return None

def generate_pairs_list(processed_dir, pairs_file, output_train, output_val, train_ratio=0.9, seed=42):
    """生成训练和验证pairs列表"""
    
    random.seed(seed)
    np.random.seed(seed)
    
    print(f"加载pairs文件: {pairs_file}")
    scenes, images, pairs = load_pairs_info(pairs_file)
    
    print(f"总共 {len(pairs)} 个图像对")
    print(f"总共 {len(scenes)} 个场景")
    print(f"总共 {len(images)} 张图像")
    
    # 转换为绝对路径
    processed_dir = Path(processed_dir).absolute()
    
    # 收集所有有效的pairs
    valid_pairs = []
    missing_count = 0
    
    print("\n查找图像文件...")
    for idx, (scene_idx, im1_idx, im2_idx, score) in enumerate(pairs):
        if idx % 10000 == 0 and idx > 0:
            print(f"  处理进度: {idx}/{len(pairs)} (找到 {len(valid_pairs)} 个有效对)")
        
        # 获取图像名称
        im1_name = images[im1_idx]
        im2_name = images[im2_idx]
        scene_name = scenes[scene_idx]
        
        # 构建图像路径（假设预处理后的结构）
        # 注意：需要根据实际预处理输出结构调整
        scene_id, subscene = scene_name.split()
        
        # 尝试多种可能的路径
        possible_paths = [
            processed_dir / scene_id / subscene / f"{im1_name}.jpg",
            processed_dir / scene_id / f"dense{subscene}" / "imgs" / im1_name,
        ]
        
        im1_path = None
        im2_path = None
        
        for base_path in possible_paths:
            if base_path.exists():
                # 找到第一个图像，推断第二个图像的位置
                im1_path = str(base_path)
                im2_path = str(base_path.parent / f"{im2_name}.jpg")
                if not Path(im2_path).exists():
                    im2_path = None
                break
        
        # 如果还是找不到，使用find_image_path
        if im1_path is None:
            im1_path = find_image_path(processed_dir, scene_id, im1_name)
            if im1_path:
                im2_path = find_image_path(processed_dir, scene_id, im2_name)
        
        if im1_path and im2_path and Path(im1_path).exists() and Path(im2_path).exists():
            valid_pairs.append((im1_path, im2_path))
        else:
            missing_count += 1
    
    print(f"\n找到 {len(valid_pairs)} 个有效图像对")
    print(f"缺失 {missing_count} 个图像对")
    
    # 随机打乱
    random.shuffle(valid_pairs)
    
    # 划分训练集和验证集
    split_idx = int(len(valid_pairs) * train_ratio)
    train_pairs = valid_pairs[:split_idx]
    val_pairs = valid_pairs[split_idx:]
    
    print(f"\n训练集: {len(train_pairs)} 对")
    print(f"验证集: {len(val_pairs)} 对")
    
    # 写入文件
    output_train = Path(output_train)
    output_val = Path(output_val)
    output_train.parent.mkdir(parents=True, exist_ok=True)
    output_val.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"\n写入训练集: {output_train}")
    with open(output_train, 'w') as f:
        for im1, im2 in train_pairs:
            f.write(f"{im1}|{im2}\n")
    
    print(f"写入验证集: {output_val}")
    with open(output_val, 'w') as f:
        for im1, im2 in val_pairs:
            f.write(f"{im1}|{im2}\n")
    
    print("\n✅ 完成！")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--processed_dir', required=True, help='预处理后的数据目录')
    parser.add_argument('--pairs_file', required=True, help='DUSt3R提供的pairs.npz文件')
    parser.add_argument('--output_train', required=True, help='输出训练集列表文件')
    parser.add_argument('--output_val', required=True, help='输出验证集列表文件')
    parser.add_argument('--train_ratio', type=float, default=0.9, help='训练集比例')
    parser.add_argument('--seed', type=int, default=42, help='随机种子')
    
    args = parser.parse_args()
    
    generate_pairs_list(
        args.processed_dir,
        args.pairs_file,
        args.output_train,
        args.output_val,
        args.train_ratio,
        args.seed
    )

