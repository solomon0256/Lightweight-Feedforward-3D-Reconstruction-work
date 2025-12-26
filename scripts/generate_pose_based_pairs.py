#!/usr/bin/env python3
"""
基于pose距离生成7-scenes的pairs文件
对于每个query图像，找到mapping中空间位置最接近的top-k帧作为配对
这比简单的帧号匹配更合理，虽然不如真正的图像检索准确
"""

import os
import numpy as np
from pathlib import Path

def load_trajectories(kapture_path):
    """从kapture的trajectories.txt加载所有pose"""
    traj_file = os.path.join(kapture_path, 'sensors', 'trajectories.txt')
    poses = {}
    
    with open(traj_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(', ')
            if len(parts) < 8:
                continue
            timestamp = parts[0]
            # qw, qx, qy, qz, tx, ty, tz
            qw, qx, qy, qz = float(parts[2]), float(parts[3]), float(parts[4]), float(parts[5])
            tx, ty, tz = float(parts[6]), float(parts[7]), float(parts[8])
            poses[timestamp] = {
                'position': np.array([tx, ty, tz]),
                'quaternion': np.array([qw, qx, qy, qz])
            }
    return poses

def load_records(kapture_path):
    """从records_camera.txt加载timestamp到图像文件名的映射"""
    records_file = os.path.join(kapture_path, 'sensors', 'records_camera.txt')
    records = {}
    
    with open(records_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(', ')
            if len(parts) >= 3:
                timestamp = parts[0]
                image_path = parts[2]
                records[timestamp] = image_path
    return records

def compute_pose_distance(pose1, pose2, position_weight=1.0, rotation_weight=0.1):
    """计算两个pose之间的距离（位置+旋转）"""
    # 位置距离
    pos_dist = np.linalg.norm(pose1['position'] - pose2['position'])
    
    # 旋转距离（四元数点积的绝对值，1表示相同，0表示正交）
    q1, q2 = pose1['quaternion'], pose2['quaternion']
    rot_similarity = abs(np.dot(q1, q2))
    rot_dist = 1 - rot_similarity  # 转换为距离
    
    return position_weight * pos_dist + rotation_weight * rot_dist

def generate_pairs(dataset_root, subscene, topk=20):
    """为指定场景生成基于pose距离的pairs文件"""
    scene_path = os.path.join(dataset_root, subscene)
    query_path = os.path.join(scene_path, 'query')
    mapping_path = os.path.join(scene_path, 'mapping')
    
    # 加载数据
    print(f"Loading query data from {query_path}...")
    query_poses = load_trajectories(query_path)
    query_records = load_records(query_path)
    
    print(f"Loading mapping data from {mapping_path}...")
    map_poses = load_trajectories(mapping_path)
    map_records = load_records(mapping_path)
    
    print(f"Query images: {len(query_records)}, Mapping images: {len(map_records)}")
    
    # 准备mapping数据（预计算）
    map_timestamps = list(map_poses.keys())
    map_images = [map_records.get(ts) for ts in map_timestamps]
    
    # 生成pairs
    pairs = []
    
    for query_ts in sorted(query_records.keys()):
        if query_ts not in query_poses:
            continue
            
        query_image = query_records[query_ts]
        query_pose = query_poses[query_ts]
        
        # 计算到所有mapping图像的距离
        distances = []
        for i, map_ts in enumerate(map_timestamps):
            if map_ts not in map_poses:
                continue
            map_pose = map_poses[map_ts]
            dist = compute_pose_distance(query_pose, map_pose)
            distances.append((dist, map_images[i]))
        
        # 排序并取top-k
        distances.sort(key=lambda x: x[0])
        
        for rank, (dist, map_image) in enumerate(distances[:topk]):
            # 使用1/(rank+1)作为score，模拟检索分数
            score = 1.0 / (rank + 1)
            pairs.append(f"{query_image}, {map_image}, {score:.4f}")
    
    return pairs

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset_root', required=True, help='7-scenes root directory')
    parser.add_argument('--subscene', default='heads', help='Scene name (chess, fire, heads, etc.)')
    parser.add_argument('--topk', type=int, default=20, help='Number of pairs per query')
    parser.add_argument('--output', help='Output pairs file path')
    args = parser.parse_args()
    
    # 生成pairs
    pairs = generate_pairs(args.dataset_root, args.subscene, args.topk)
    
    # 输出路径
    if args.output:
        output_path = args.output
    else:
        output_path = os.path.join(args.dataset_root, args.subscene, 
                                   'pairfiles', 'query', f'pose_based_top{args.topk}.txt')
    
    # 确保目录存在
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # 写入文件
    with open(output_path, 'w') as f:
        f.write('\n'.join(pairs))
    
    print(f"Generated {len(pairs)} pairs, saved to {output_path}")

if __name__ == '__main__':
    main()
