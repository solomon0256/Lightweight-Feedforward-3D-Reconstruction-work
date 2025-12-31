# 服务器部署说明

**最后更新**: 2025-01-01  
**服务器**: 99.28.52.219:25834

---

## 快速开始

### 1. 连接服务器

```bash
ssh -p 25834 root@99.28.52.219 -L 8080:localhost:8080
```

### 2. 部署代码

```bash
cd /root
git clone --recursive https://github.com/solomon0256/Lightweight-Feedforward-3D-Reconstruction-work.git
cd Lightweight-Feedforward-3D-Reconstruction-work
```

或如果已存在：
```bash
cd /root/Lightweight-Feedforward-3D-Reconstruction-work
git pull origin main
git submodule update --init --recursive
```

### 3. 运行一键部署脚本

```bash
bash scripts/服务器部署完整脚本.sh
```

或分步执行：

```bash
# 环境设置
bash scripts/setup_server.sh

# 验证环境
python scripts/test_dust3r_baseline.py --device cuda

# 准备MegaDepth数据集（在tmux中运行）
tmux new -s megadepth
bash scripts/download_megadepth.sh

# 生成pairs列表
python scripts/prepare_megadepth_pairs.py \
    --processed_dir datasets/megadepth_processed \
    --pairs_file datasets/megadepth/megadepth_pairs.npz \
    --output_train datasets/train_pairs.lst \
    --output_val datasets/val_pairs.lst

# Dry-run测试
python scripts/train_distill.py --exp-config distill.yaml --dry-run --max-epochs 2

# 正式训练（在tmux中运行）
tmux new -s distill_train
python scripts/train_distill.py --exp-config distill.yaml
```

---

## 详细文档

- **快速开始指南**: `docs/快速开始指南.md`
- **完整执行步骤**: `docs/服务器部署执行步骤.md`
- **执行计划总结**: `docs/执行计划总结.md`

---

## 关键文件

- **配置**: `expconfigs/distill.yaml`
- **训练脚本**: `scripts/train_distill.py`
- **下载脚本**: `scripts/download_megadepth.sh`
- **Pairs生成**: `scripts/prepare_megadepth_pairs.py`

---

## 配置说明

### Student-S架构（当前配置）

```
Encoder: 9层, 8头, 512维 (head_dim=64)
Decoder: 6层, 8头, 512维 (head_dim=64)
参数量: ~80M
```

### 训练参数

```
Batch size: 1
Learning rate: 2e-4
Max epochs: 30
Early stop patience: 10
```

---

## 注意事项

1. **使用tmux**: 长时间任务（下载、训练）必须在tmux中运行
2. **MegaDepth数据**: 需要从官网手动下载原始数据
3. **监控日志**: 使用 `tail -f /tmp/*.log` 查看进度
4. **GPU显存**: 如果不足，调整 `expconfigs/distill.yaml` 中的 `batch_size`

