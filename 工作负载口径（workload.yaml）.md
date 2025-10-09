它在干什么？
把“输入尺寸、批大小、配对规则、测试集名单、量化校准集”一次性固定下来，避免后面每个实验各写各的。

放哪里：
/experiments/DUSt3R_PQK/configs/workload.yaml

直接可用模板：

## 工作负载口径 — workload.yaml

它在干什么？

把“输入尺寸、批大小、配对规则、测试集名单、量化校准集”一次性固定下来，避免后面每个实验各写各的。

放置位置（建议）：

/experiments/DUSt3R_PQK/configs/workload.yaml

直接可用模板：

```yaml
# configs/workload.yaml
seed: 42
device: "cuda"        # 或 "cpu"（评测时按需改）

# 统一输入/批次/静态shape（方便 TensorRT）
input:
  shape: [1, 3, 512, 512]   # BS=1, 3通道, 512x512
  static_shape: true

# 图对构造规则（DUSt3R 是成对推理）
pair_graph:
  strategy: "knn_neighbor"  # 或 "topk_similarity"
  k: 4                      # 每张图连 K 个邻近/最相似图
  shuffle: false            # 评测固定顺序
  max_pairs_per_scene: 200  # 限制单场景pair数（评测稳定）

# 数据与清单路径
data:
  dataset_id: "YOUR_DATASET_TAG"   # 自己定义的标识
  split: "val"                     # 评测用 val/test
  eval_pairs_list: "data/eval_pairs/pairs_val.txt"  # 每行: path_i|path_j
  scenes_list:   "data/eval_pairs/scenes_val.txt"   # 可选：按场景评测

# 量化校准集（PTQ/QAT 共用）
calibration:
  images_root: "data/calibration/"
  min_images: 512
  sampling: "uniform"   # 或 "stratified_by_scene"
  hash_file: "data/calibration/CALIBSET.sha1"  # 用于可复现校验

# 端侧配置占位（Jetson 等）
edge_profile:
  enable: false
  soc: "jetson-agx-orin"
  power_mode: "30W"
  fan_mode: "max"
```

你要做的最少动作（10–20 分钟）：

- 把评测对图清单文件写好：

  `data/eval_pairs/pairs_val.txt`（每行：/abs/path/imgA.jpg|/abs/path/imgB.jpg）

- （可选）`data/eval_pairs/scenes_val.txt`（每行一个场景 ID）

- 准备量化校准集：把 ≥512 张代表性图片放进 `data/calibration/`，并生成一个校验和文件（例如：`sha1sum * > CALIBSET.sha1`）。

- 把 `dataset_id` 和 `split` 按你自己的数据命名填写好。

附注：上述模板可直接复制为 YAML 文件并放到建议路径，或在评测脚本中读取并覆盖少量字段以适配不同实验。