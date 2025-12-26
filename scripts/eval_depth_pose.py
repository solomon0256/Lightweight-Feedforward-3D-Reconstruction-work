#!/usr/bin/env python
"""
DUSt3R Baseline 精度评测脚本
在 7-Scenes 数据集上评测深度估计和相对位姿估计精度

评测指标:
- 深度: AbsRel, RMSE, δ1 (δ < 1.25)
- 位姿: RRE (Relative Rotation Error), RTE (Relative Translation Error)
"""

import os
import sys
import json
import numpy as np
from pathlib import Path
from tqdm import tqdm
import torch
from PIL import Image
import cv2

# 添加 DUSt3R 路径
DUST3R_PATH = Path(__file__).parent.parent / "third_party" / "dust3r"
sys.path.insert(0, str(DUST3R_PATH))

from dust3r.inference import inference
from dust3r.model import AsymmetricCroCo3DStereo
from dust3r.utils.image import load_images
from dust3r.image_pairs import make_pairs
from dust3r.cloud_opt import global_aligner, GlobalAlignerMode

# ==================== 深度评测指标 ====================

def compute_depth_metrics(pred_depth, gt_depth, valid_mask=None):
    """
    计算深度估计指标（完整版）
    
    Args:
        pred_depth: 预测深度图 (H, W)
        gt_depth: GT深度图 (H, W), 单位: mm -> 转换为 m
        valid_mask: 有效像素掩码
    
    Returns:
        dict: 包含完整深度指标：
            - abs_rel: 绝对相对误差 mean(|d-g|/g)
            - sq_rel: 平方相对误差 mean((d-g)²/g)
            - rmse: 均方根误差 sqrt(mean((d-g)²))
            - rmse_log: 对数均方根误差 sqrt(mean((log d - log g)²))
            - delta1: δ < 1.25 的比例
            - delta2: δ < 1.25² 的比例
            - delta3: δ < 1.25³ 的比例
            - si_log: 尺度不变对数误差
            - scale: 对齐尺度因子
    """
    if valid_mask is None:
        valid_mask = (gt_depth > 0) & (gt_depth < 10)  # 10m 以内有效
    
    pred = pred_depth[valid_mask]
    gt = gt_depth[valid_mask]
    
    if len(pred) == 0:
        return {
            'abs_rel': np.nan, 'sq_rel': np.nan, 
            'rmse': np.nan, 'rmse_log': np.nan,
            'delta1': np.nan, 'delta2': np.nan, 'delta3': np.nan,
            'si_log': np.nan, 'scale': np.nan
        }
    
    # 对齐尺度 (中位数尺度)
    scale = np.median(gt) / (np.median(pred) + 1e-8)
    pred = pred * scale
    
    # ========== 主要误差指标 ==========
    # AbsRel: 绝对相对误差
    abs_rel = np.mean(np.abs(pred - gt) / gt)
    
    # SqRel: 平方相对误差
    sq_rel = np.mean(((pred - gt) ** 2) / gt)
    
    # RMSE: 均方根误差
    rmse = np.sqrt(np.mean((pred - gt) ** 2))
    
    # RMSE_log: 对数均方根误差 (需要过滤掉非正值)
    log_mask = (pred > 0) & (gt > 0)
    if np.sum(log_mask) > 0:
        log_pred = np.log(pred[log_mask])
        log_gt = np.log(gt[log_mask])
        rmse_log = np.sqrt(np.mean((log_pred - log_gt) ** 2))
        
        # SI_log: 尺度不变对数误差
        # si_log = sqrt(mean((log d - log g)²) - (mean(log d - log g))²)
        log_diff = log_pred - log_gt
        si_log = np.sqrt(np.mean(log_diff ** 2) - (np.mean(log_diff) ** 2))
    else:
        rmse_log = np.nan
        si_log = np.nan
    
    # ========== 阈值准确率 ==========
    thresh = np.maximum(pred / gt, gt / pred)
    delta1 = np.mean(thresh < 1.25)        # δ < 1.25
    delta2 = np.mean(thresh < 1.25 ** 2)   # δ < 1.5625
    delta3 = np.mean(thresh < 1.25 ** 3)   # δ < 1.953125
    
    return {
        'abs_rel': float(abs_rel),
        'sq_rel': float(sq_rel),
        'rmse': float(rmse),
        'rmse_log': float(rmse_log) if not np.isnan(rmse_log) else None,
        'delta1': float(delta1),
        'delta2': float(delta2),
        'delta3': float(delta3),
        'si_log': float(si_log) if not np.isnan(si_log) else None,
        'scale': float(scale)
    }


# ==================== 位姿评测指标 ====================

def compute_pose_error(pred_R, pred_t, gt_R, gt_t):
    """
    计算相对位姿误差
    
    Args:
        pred_R: 预测旋转矩阵 (3, 3)
        pred_t: 预测平移向量 (3,)
        gt_R: GT旋转矩阵 (3, 3)
        gt_t: GT平移向量 (3,)
    
    Returns:
        dict: 包含 RRE (度), RTE (cm)
    """
    # 相对旋转误差 (度)
    R_err = pred_R @ gt_R.T
    trace = np.clip(np.trace(R_err), -1, 3)
    rre = np.rad2deg(np.arccos((trace - 1) / 2))
    
    # 相对平移误差 (cm)
    # 对齐尺度
    scale = np.linalg.norm(gt_t) / (np.linalg.norm(pred_t) + 1e-8)
    pred_t_scaled = pred_t * scale
    rte = np.linalg.norm(pred_t_scaled - gt_t) * 100  # m -> cm
    
    return {
        'rre_deg': float(rre),
        'rte_cm': float(rte),
        'scale': float(scale)
    }


def load_7scenes_pose(pose_file):
    """加载 7-Scenes 位姿文件 (cam-to-world 4x4 矩阵)"""
    pose = np.loadtxt(pose_file)
    R = pose[:3, :3]
    t = pose[:3, 3]
    return R, t


def load_7scenes_depth(depth_file):
    """加载 7-Scenes 深度图
    
    kapture 格式: float32 二进制文件, 单位: 米
    原始 PNG 格式: 16-bit PNG, 单位: mm
    """
    depth_file = str(depth_file)
    
    if depth_file.endswith('.png'):
        # 原始 PNG 格式
        depth = cv2.imread(depth_file, cv2.IMREAD_UNCHANGED)
        if depth is None:
            return None
        # 转换为米
        depth = depth.astype(np.float32) / 1000.0
        # 无效深度 (65535) 设为 0
        depth[depth > 60] = 0
    else:
        # kapture 二进制格式 (float32)
        try:
            with open(depth_file, 'rb') as f:
                data = f.read()
            # 7-scenes 深度是 480x640 的 float32
            depth = np.frombuffer(data, dtype=np.float32).reshape(480, 640)
        except Exception as e:
            print(f"加载深度图失败: {e}")
            return None
    
    return depth


# ==================== 主评测函数 ====================

def evaluate_pair(model, img1_path, img2_path, gt_depth1, gt_pose1, gt_pose2, device='cuda'):
    """
    评测一对图像的深度和位姿估计精度
    """
    # 加载图像
    images = load_images([str(img1_path), str(img2_path)], size=512)
    pairs = make_pairs(images, scene_graph='complete', prefilter=None, symmetrize=True)
    
    # 推理
    with torch.no_grad():
        output = inference(pairs, model, device, batch_size=1)
    
    # 获取预测深度 (第一张图)
    pred_depth1 = output['pred1']['pts3d'][0, :, :, 2].cpu().numpy()  # Z 坐标作为深度
    
    # 计算深度指标
    if gt_depth1 is not None:
        # 调整尺寸
        h, w = gt_depth1.shape
        pred_depth1_resized = cv2.resize(pred_depth1, (w, h), interpolation=cv2.INTER_LINEAR)
        depth_metrics = compute_depth_metrics(pred_depth1_resized, gt_depth1)
    else:
        depth_metrics = {'abs_rel': np.nan, 'rmse': np.nan, 'delta1': np.nan}
    
    # 计算位姿指标 (相对位姿)
    # DUSt3R 输出的是点云，需要从点云恢复位姿
    # 简化: 使用 global_aligner
    try:
        scene = global_aligner(output, device=device, mode=GlobalAlignerMode.PairViewer)
        poses = scene.get_im_poses().cpu().numpy()  # (2, 4, 4)
        
        # 相对位姿: pose2 相对于 pose1
        pred_rel = np.linalg.inv(poses[0]) @ poses[1]
        pred_R = pred_rel[:3, :3]
        pred_t = pred_rel[:3, 3]
        
        # GT 相对位姿
        gt_rel = np.linalg.inv(gt_pose1) @ gt_pose2
        gt_R = gt_rel[:3, :3]
        gt_t = gt_rel[:3, 3]
        
        pose_metrics = compute_pose_error(pred_R, pred_t, gt_R, gt_t)
    except Exception as e:
        print(f"位姿估计失败: {e}")
        pose_metrics = {'rre_deg': np.nan, 'rte_cm': np.nan}
    
    return depth_metrics, pose_metrics


def run_evaluation(model, dataset_path, max_pairs=50, device='cuda'):
    """
    在 7-Scenes 数据集上运行评测
    """
    dataset_path = Path(dataset_path)
    
    # 收集测试帧 (从 query 目录)
    query_records = dataset_path / "query" / "sensors" / "records_camera.txt"
    if not query_records.exists():
        print(f"找不到 records_camera.txt: {query_records}")
        return None
    
    # 解析 records_camera.txt
    frames = []
    with open(query_records, 'r') as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue
            parts = line.strip().split(', ')
            if len(parts) >= 3:
                timestamp, sensor_id, img_name = parts[0], parts[1], parts[2]
                frames.append({
                    'timestamp': timestamp,
                    'img_name': img_name,
                    'img_path': dataset_path / "query" / "sensors" / "records_data" / img_name
                })
    
    print(f"找到 {len(frames)} 个查询帧")
    
    # 加载位姿轨迹
    trajectories = {}
    traj_file = dataset_path / "query" / "sensors" / "trajectories.txt"
    if traj_file.exists():
        with open(traj_file, 'r') as f:
            for line in f:
                if line.startswith('#') or not line.strip():
                    continue
                parts = line.strip().split(', ')
                if len(parts) >= 8:
                    ts = parts[0]
                    qw, qx, qy, qz = float(parts[2]), float(parts[3]), float(parts[4]), float(parts[5])
                    tx, ty, tz = float(parts[6]), float(parts[7]), float(parts[8]) if len(parts) > 8 else 0
                    
                    # 四元数转旋转矩阵
                    from scipy.spatial.transform import Rotation
                    R = Rotation.from_quat([qx, qy, qz, qw]).as_matrix()
                    
                    pose = np.eye(4)
                    pose[:3, :3] = R
                    pose[:3, 3] = [tx, ty, tz]
                    trajectories[ts] = pose
    
    print(f"加载 {len(trajectories)} 个位姿")
    
    # 创建图像对 (相邻帧)
    all_depth_metrics = []
    all_pose_metrics = []
    
    n_pairs = min(max_pairs, len(frames) - 1)
    step = max(1, (len(frames) - 1) // n_pairs)
    
    for i in tqdm(range(0, len(frames) - 1, step)[:n_pairs], desc="评测中"):
        frame1 = frames[i]
        frame2 = frames[min(i + 5, len(frames) - 1)]  # 间隔 5 帧，增加基线
        
        img1_path = frame1['img_path']
        img2_path = frame2['img_path']
        
        if not img1_path.exists() or not img2_path.exists():
            continue
        
        # 加载 GT 深度 (kapture 格式下深度文件可能没有 .png 后缀)
        depth1_path = str(img1_path).replace('.color.png', '.depth')
        if not Path(depth1_path).exists():
            depth1_path = str(img1_path).replace('.color.png', '.depth.png')
        if Path(depth1_path).exists():
            gt_depth1 = load_7scenes_depth(depth1_path)
        else:
            gt_depth1 = None
        
        # 加载 GT 位姿
        gt_pose1 = trajectories.get(frame1['timestamp'], np.eye(4))
        gt_pose2 = trajectories.get(frame2['timestamp'], np.eye(4))
        
        try:
            depth_m, pose_m = evaluate_pair(
                model, img1_path, img2_path, 
                gt_depth1, gt_pose1, gt_pose2, 
                device=device
            )
            all_depth_metrics.append(depth_m)
            all_pose_metrics.append(pose_m)
        except Exception as e:
            print(f"评测失败 [{i}]: {e}")
    
    # 汇总结果
    def agg(metrics, key):
        vals = [m[key] for m in metrics if m.get(key) is not None and not np.isnan(m.get(key, np.nan))]
        return np.mean(vals) if vals else np.nan
    
    results = {
        'depth': {
            'abs_rel': agg(all_depth_metrics, 'abs_rel'),
            'sq_rel': agg(all_depth_metrics, 'sq_rel'),
            'rmse': agg(all_depth_metrics, 'rmse'),
            'rmse_log': agg(all_depth_metrics, 'rmse_log'),
            'delta1': agg(all_depth_metrics, 'delta1'),
            'delta2': agg(all_depth_metrics, 'delta2'),
            'delta3': agg(all_depth_metrics, 'delta3'),
            'si_log': agg(all_depth_metrics, 'si_log'),
            'n_samples': len([m for m in all_depth_metrics if m.get('abs_rel') is not None and not np.isnan(m.get('abs_rel', np.nan))])
        },
        'pose': {
            'rre_deg': agg(all_pose_metrics, 'rre_deg'),
            'rte_cm': agg(all_pose_metrics, 'rte_cm'),
            'n_samples': len([m for m in all_pose_metrics if not np.isnan(m.get('rre_deg', np.nan))])
        }
    }
    
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description='DUSt3R 精度评测')
    parser.add_argument('--dataset', type=str, 
                        default='datasets/7-scenes/heads',
                        help='7-Scenes 数据集路径')
    parser.add_argument('--model', type=str,
                        default='naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt',
                        help='模型名称或路径')
    parser.add_argument('--device', type=str, default='cuda')
    parser.add_argument('--max-pairs', type=int, default=50,
                        help='最大评测对数')
    parser.add_argument('--output', type=str, default='logs/eval_results.json',
                        help='输出文件')
    args = parser.parse_args()
    
    # 加载模型
    print(f"加载模型: {args.model}")
    model = AsymmetricCroCo3DStereo.from_pretrained(args.model).to(args.device)
    model.eval()
    
    # 运行评测
    print(f"数据集: {args.dataset}")
    results = run_evaluation(model, args.dataset, args.max_pairs, args.device)
    
    if results:
        print("\n" + "="*60)
        print("评测结果:")
        print("="*60)
        print(f"\n【深度估计】(n={results['depth']['n_samples']})")
        print(f"  AbsRel:   {results['depth']['abs_rel']:.4f}")
        print(f"  SqRel:    {results['depth']['sq_rel']:.4f}")
        print(f"  RMSE:     {results['depth']['rmse']:.4f} m")
        print(f"  RMSE_log: {results['depth']['rmse_log']:.4f}")
        print(f"  δ1:       {results['depth']['delta1']:.4f}")
        print(f"  δ2:       {results['depth']['delta2']:.4f}")
        print(f"  δ3:       {results['depth']['delta3']:.4f}")
        print(f"  SI_log:   {results['depth']['si_log']:.4f}")
        
        print(f"\n【位姿估计】(n={results['pose']['n_samples']})")
        print(f"  RRE:    {results['pose']['rre_deg']:.2f}°")
        print(f"  RTE:    {results['pose']['rte_cm']:.2f} cm")
        
        # 保存结果
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n结果已保存: {output_path}")


if __name__ == '__main__':
    main()
