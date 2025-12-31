# 🚀 开始部署！

所有准备工作已完成！现在可以在服务器上开始执行部署。

---

## ✅ 已完成的准备工作

1. ✅ **脚本创建**
   - `scripts/download_megadepth.sh` - MegaDepth数据集下载
   - `scripts/prepare_megadepth_pairs.py` - 生成训练pairs列表
   - `scripts/服务器部署完整脚本.sh` - 一键部署脚本

2. ✅ **配置文件更新**
   - `expconfigs/distill.yaml` - Student-S配置（9层encoder, 512维, 8头）

3. ✅ **文档创建**
   - `docs/快速开始指南.md`
   - `docs/服务器部署执行步骤.md`
   - `docs/执行计划总结.md`
   - `README_DEPLOYMENT.md`

---

## 📋 立即执行步骤

### 第一步：在服务器上获取最新代码

```bash
ssh -p 25834 root@99.28.52.219
cd /root/Lightweight-Feedforward-3D-Reconstruction-work
git pull origin main
git submodule update --init --recursive
```

### 第二步：运行一键部署脚本

```bash
bash scripts/服务器部署完整脚本.sh
```

或者分步执行（参考 `docs/快速开始指南.md`）：

```bash
# 1. 环境设置
bash scripts/setup_server.sh

# 2. 验证环境
python scripts/test_dust3r_baseline.py --device cuda

# 3. 准备MegaDepth（在tmux中）
tmux new -s megadepth
bash scripts/download_megadepth.sh

# 4. 生成pairs列表
python scripts/prepare_megadepth_pairs.py \
    --processed_dir datasets/megadepth_processed \
    --pairs_file datasets/megadepth/megadepth_pairs.npz \
    --output_train datasets/train_pairs.lst \
    --output_val datasets/val_pairs.lst

# 5. Dry-run测试
python scripts/train_distill.py --exp-config distill.yaml --dry-run --max-epochs 2

# 6. 正式训练（在tmux中）
tmux new -s distill_train
python scripts/train_distill.py --exp-config distill.yaml
```

---

## 📚 参考文档

- **快速开始**: `docs/快速开始指南.md`
- **详细步骤**: `docs/服务器部署执行步骤.md`
- **计划总结**: `docs/执行计划总结.md`

---

## ⚠️ 重要提示

1. **使用tmux**: 长时间任务必须在tmux中运行
2. **MegaDepth数据**: 需要从官网手动下载原始数据
3. **监控日志**: 使用 `tail -f /tmp/*.log` 查看进度

---

**准备就绪！开始部署吧！** 🎯

