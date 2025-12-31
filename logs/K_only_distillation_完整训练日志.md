# K-only 知识蒸馏完整训练日志

**训练时间**: 2025-12-30 17:03 ~ 2025-12-30 19:04  
**总耗时**: 2.01 GPU 小时  
**服务器**: vast.ai (ssh -p 26079 root@ssh5.vast.ai)

---

## 1. 实验配置

```
============================================================
DUSt3R Knowledge Distillation
============================================================
  Exp ID: expconfigs/distill.yaml_42
  Device: cuda
  Dry run: False
============================================================
```

### 数据集
- **训练样本**: 999 pairs
- **验证样本**: 999 pairs
- **数据集**: 7-Scenes (真实数据)

### Teacher 模型
- **来源**: HuggingFace `naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt`
- **参数量**: 571.17M
- **模型大小**: 2178.85 MB
- **FLOPs**: 1.14G

### Student 模型
- **架构**: dust3r_student_s
- **参数量**: 46.43M
- **模型大小**: 177.11 MB
- **FLOPs**: 0.09G
- **压缩率**: 8.1% (相对于 Teacher)

### 训练超参数
```
  Max epochs: 30
  Early stop patience: 10
  Initial beta: 0.5
  Temperature: 3.0
  Learning rate: 2.00e-04
```

---

## 2. 完整训练过程

| Epoch | Train Loss | Val Loss | LR | β | 备注 |
|-------|------------|----------|-----|------|------|
| 1 | 0.0206 | 0.0196 | 2.00e-04 | 0.50 | 初始 |
| 2 | 0.0177 | 0.0165 | 2.00e-04 | 0.50 | 快速下降 |
| 3 | 0.0159 | 0.0165 | 2.00e-04 | 0.50 | |
| 4 | 0.0159 | 0.0164 | 2.00e-04 | 0.50 | |
| 5 | 0.0160 | 0.0165 | 2.00e-04 | 0.50 | |
| 6 | 0.0159 | 0.0165 | 2.00e-04 | 0.50 | |
| 7 | 0.0159 | 0.0167 | 2.00e-04 | 0.50 | |
| 8 | 0.0158 | 0.0164 | 2.00e-04 | 0.50 | |
| 9 | 0.0157 | 0.0163 | 2.00e-04 | 0.50 | |
| 10 | 0.0158 | 0.0164 | 2.00e-04 | 0.50 | |
| 11 | 0.0157 | 0.0162 | 2.00e-04 | 0.50 | |
| 12 | 0.0157 | 0.0162 | 2.00e-04 | 0.50 | |
| 13 | 0.0156 | 0.0163 | 2.00e-04 | 0.50 | |
| **14** | **0.0156** | **0.0161** | 2.00e-04 | 0.50 | **最佳 Val Loss** |
| 15 | 0.0156 | 0.0162 | 2.00e-04 | 0.50 | |
| 16 | 0.0155 | 0.0164 | 2.00e-04 | 0.50 | |
| 17 | 0.0156 | 0.0162 | 2.00e-04 | 0.50 | |
| 18 | 0.0155 | 0.0162 | 2.00e-04 | 0.50 | |
| 19 | 0.0155 | 0.0162 | 2.00e-04 | 0.50 | |
| 20 | 0.0155 | 0.0162 | 2.00e-04 | 0.50 | |
| **21** | **0.0155** | **0.0161** | 2.00e-04 | 0.50 | **并列最佳 Val Loss** |
| 22 | 0.0155 | 0.0162 | 2.00e-04 | 0.50 | |
| 23 | 0.0160 | 0.0167 | 2.00e-04 | 0.52 | β 开始增加 |
| 24 | 0.0166 | 0.0174 | 2.00e-04 | 0.54 | **Early Stop 触发** |

---

## 3. 训练结果统计

### Loss 变化
```
Train Loss: 0.0206 → 0.0155 (下降 24.8%)
Val Loss:   0.0196 → 0.0161 (下降 17.9%)
```

### 收敛分析
- **快速收敛阶段**: Epoch 1-3 (Loss 大幅下降)
- **稳定阶段**: Epoch 4-22 (Loss 平稳，微小波动)
- **过拟合阶段**: Epoch 23-24 (Loss 上升，触发 Early Stop)

### 最终模型
- **最佳 Checkpoint**: `outputs/checkpoints/student_fp32_best.pth`
- **保存于 Epoch**: 14 或 21 (Val Loss = 0.0161)

---

## 4. JSON 日志详情

```json
{
  "exp_id": "K_only_42",
  "combo": "K-only",
  "seed": 42,
  "dataset_id": "YOUR_DATASET_TAG",
  "split": "val",
  "rho": null,
  "T": 3.0,
  "beta": 0.5,
  "gamma": 0.0,
  "bits_w": null,
  "bits_a": null,
  "keep_list": null,
  "params_M": 46.427721,
  "flops_G": 0.092855442,
  "size_MB": 177.1077003479004,
  "vram_GB": 2.8825464248657227,
  "chamfer": 0.0,
  "absrel": 0.0,
  "rmse": 0.0,
  "delta1": 0.0,
  "reproj_px": 0.0,
  "t_pair_p50_ms": 0.0,
  "t_pair_p95_ms": 0.0,
  "t_scene_s": 0.0,
  "pairs_per_sec": 0.0,
  "edge_device": null,
  "num_pairs": null,
  "calibration_set_hash": null,
  "pytorch_ver": "2.5.1+cu121",
  "cuda_ver": "12.1",
  "tensorrt_ver": null,
  "modelopt_ver": null,
  "commit_hash": "d040abe9",
  "notes": "K-only distillation, final val_loss=0.0174",
  "gpu_hours": 2.0145069277777776,
  "datetime": "2025-12-30T19:04:44.595250"
}
```

---

## 5. 原始日志

```
============================================================
DUSt3R Knowledge Distillation
============================================================
  Exp ID: expconfigs/distill.yaml_42
  Device: cuda
  Dry run: False
============================================================
[INFO] Train samples: 999, Val samples: 999
[INFO] Loading Teacher model (real DUSt3R from HuggingFace)...
Warning, cannot find cuda-compiled version of RoPE2D, using a slow pytorch version instead
[INFO] Loading Teacher from HuggingFace: naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt
[INFO] Teacher model loaded: 571.17M parameters

[INFO] Model Statistics:
Warning: Using rough FLOPs estimation. Install 'fvcore' or 'thop' for accurate results.
Warning: Using rough FLOPs estimation. Install 'fvcore' or 'thop' for accurate results.
  Teacher: Params: 571.17M (trainable: 571.17M), FLOPs: 1.14G, Size: 2178.85MB, VRAM: 0.00GB
  Student: Params: 46.43M (trainable: 46.43M), FLOPs: 0.09G, Size: 177.11MB, VRAM: 0.00GB
  Compression: 8.1% params

================================================================================
[2025-12-30T17:03:50.842357] 实验完成通知: K-only_real_data
状态: RUNNING
  message: 实验开始训练
  train_samples: 999
  val_samples: 999
  teacher_params: 571.17M
  student_params: 46.43M
  max_epochs: 30
================================================================================


============================================================
Starting Distillation Training
============================================================
  Max epochs: 30
  Early stop patience: 10
  Initial beta: 0.5
  Temperature: 3.0
============================================================

/workspace/Lightweight-Feedforward-3D-Reconstruction-work/third_party/dust3r/dust3r/model.py:206: FutureWarning: `torch.cuda.amp.autocast(args...)` is deprecated. Please use `torch.amp.autocast('cuda', args...)` instead.
  with torch.cuda.amp.autocast(enabled=False):
Epoch 1/30 | Train: 0.0206 | Val: 0.0196 | LR: 2.00e-04 | β: 0.50
Epoch 2/30 | Train: 0.0177 | Val: 0.0165 | LR: 2.00e-04 | β: 0.50
Epoch 3/30 | Train: 0.0159 | Val: 0.0165 | LR: 2.00e-04 | β: 0.50
Epoch 4/30 | Train: 0.0159 | Val: 0.0164 | LR: 2.00e-04 | β: 0.50
Epoch 5/30 | Train: 0.0160 | Val: 0.0165 | LR: 2.00e-04 | β: 0.50
Epoch 6/30 | Train: 0.0159 | Val: 0.0165 | LR: 2.00e-04 | β: 0.50
Epoch 7/30 | Train: 0.0159 | Val: 0.0167 | LR: 2.00e-04 | β: 0.50
Epoch 8/30 | Train: 0.0158 | Val: 0.0164 | LR: 2.00e-04 | β: 0.50
Epoch 9/30 | Train: 0.0157 | Val: 0.0163 | LR: 2.00e-04 | β: 0.50
Epoch 10/30 | Train: 0.0158 | Val: 0.0164 | LR: 2.00e-04 | β: 0.50
Epoch 11/30 | Train: 0.0157 | Val: 0.0162 | LR: 2.00e-04 | β: 0.50
Epoch 12/30 | Train: 0.0157 | Val: 0.0162 | LR: 2.00e-04 | β: 0.50
Epoch 13/30 | Train: 0.0156 | Val: 0.0163 | LR: 2.00e-04 | β: 0.50
Epoch 14/30 | Train: 0.0156 | Val: 0.0161 | LR: 2.00e-04 | β: 0.50
Epoch 15/30 | Train: 0.0156 | Val: 0.0162 | LR: 2.00e-04 | β: 0.50
Epoch 16/30 | Train: 0.0155 | Val: 0.0164 | LR: 2.00e-04 | β: 0.50
Epoch 17/30 | Train: 0.0156 | Val: 0.0162 | LR: 2.00e-04 | β: 0.50
Epoch 18/30 | Train: 0.0155 | Val: 0.0162 | LR: 2.00e-04 | β: 0.50
Epoch 19/30 | Train: 0.0155 | Val: 0.0162 | LR: 2.00e-04 | β: 0.50
Epoch 20/30 | Train: 0.0155 | Val: 0.0162 | LR: 2.00e-04 | β: 0.50
Epoch 21/30 | Train: 0.0155 | Val: 0.0161 | LR: 2.00e-04 | β: 0.50
Epoch 22/30 | Train: 0.0155 | Val: 0.0162 | LR: 2.00e-04 | β: 0.50
Epoch 23/30 | Train: 0.0160 | Val: 0.0167 | LR: 2.00e-04 | β: 0.52
Epoch 24/30 | Train: 0.0166 | Val: 0.0174 | LR: 2.00e-04 | β: 0.54

[INFO] Early stopping at epoch 24
/workspace/Lightweight-Feedforward-3D-Reconstruction-work/scripts/train_distill.py:746: FutureWarning: You are using `torch.load` with `weights_only=False` (the current default value), which uses the default pickle module implicitly. It is possible to construct malicious pickle data which will execute arbitrary code during unpickling (See https://github.com/pytorch/pytorch/blob/main/SECURITY.md#untrusted-models for more details). In a future release, the default value for `weights_only` will be flipped to `True`. This limits the functions that could be executed during unpickling. Arbitrary objects will no longer be allowed to be loaded via this mode unless they are explicitly allowlisted by the user via `torch.serialization.add_safe_globals`. We recommend you start setting `weights_only=True` for any use case where you don't have full control of the loaded file. Please open an issue on GitHub for any issues related to this experimental feature.
  student.load_state_dict(torch.load(best_path, map_location=device))
Warning: Using rough FLOPs estimation. Install 'fvcore' or 'thop' for accurate results.
/workspace/Lightweight-Feedforward-3D-Reconstruction-work/third_party/dust3r/dust3r/inference.py:44: FutureWarning: `torch.cuda.amp.autocast(args...)` is deprecated. Please use `torch.amp.autocast('cuda', args...)` instead.
  with torch.cuda.amp.autocast(enabled=bool(use_amp)):
[WARN] VRAM measurement with DUSt3R inference failed: 'dict' object has no attribute 'shape'

============================================================
Training Complete!
  Best checkpoint: /workspace/Lightweight-Feedforward-3D-Reconstruction-work/outputs/checkpoints/student_fp32_best.pth
  JSON log: /workspace/Lightweight-Feedforward-3D-Reconstruction-work/logs/K_only_42.json
  GPU hours: 2.01h
============================================================
[WARN] 完成通知发送失败: 'str' object has no attribute 'get'
```

---

## 6. 警告信息说明

| 警告 | 严重程度 | 影响 |
|------|----------|------|
| RoPE2D cuda-compiled not found | 低 | 使用慢速 PyTorch 版本，不影响结果 |
| FLOPs estimation rough | 低 | FLOPs 数值为估算，可接受 |
| torch.cuda.amp.autocast deprecated | 低 | 未来版本可能需要修改，当前正常 |
| torch.load weights_only=False | 中 | 安全警告，当前正常 |
| VRAM measurement failed | 中 | VRAM 统计失败，不影响训练 |
| 完成通知发送失败 | 低 | 通知功能问题，不影响结果 |

---

## 7. 与 Stanford 论文对比

| 指标 | 我们的结果 | Stanford 论文 |
|------|------------|--------------|
| Teacher | DUSt3R ViT-L | DUSt3R ViT-L |
| Teacher 参数量 | 571.17M | ~570M |
| Student 参数量 | 46.43M | 0.7M-11.5M |
| 压缩率 | 8.1% | 0.17%-2% |
| 训练数据 | 7-Scenes (999 pairs) | 单场景 (100 pairs) |
| Final Loss | 0.0161 | 0.007-0.011 |

**分析**: Stanford 的 Loss 更低是因为他们针对单场景过拟合，而我们是跨场景泛化训练。

---

## 8. 下一步行动

1. **下载模型**: 从服务器下载 `student_fp32_best.pth`
2. **运行评测**: 计算 Chamfer、AbsRel、RMSE、δ<1.25 等指标
3. **与 Teacher 对比**: 评估精度损失
4. **继续 PQK 实验**: 进行 Q-only 量化实验

---

*文档生成时间: 2025-12-31*
