## 评测与日志口径（eval.yaml + schema）

说明：

把“算哪些质量/效率/资源指标、阈值、止损线”统一写死，并定义日志字段，保证所有实验写出同一套列。

建议放置路径：

- `configs/eval.yaml`（指标与阈值）
- `logs/unified_log_schema.json`（日志字段定义）

### `configs/eval.yaml` 模板

```yaml
# configs/eval.yaml
metrics:
  quality:
    - name: "chamfer"        # 单位：场景/对图平均
    - name: "absrel"
    - name: "rmse"
    - name: "delta1"
    - name: "reproj_px"      # 重投影像素误差
  efficiency:
    - name: "t_pair_p50_ms"  # 单pair端到端时延(含预后处理)：p50
    - name: "t_pair_p95_ms"  # 尾延迟：p95
    - name: "t_scene_s"      # 固定pair_graph下整场景耗时
    - name: "pairs_per_sec"  # 吞吐
  resources:
    - name: "params_M"
    - name: "flops_G"
    - name: "size_MB"
    - name: "vram_GB"

thresholds:         # 成功/止损口径（可在任务卡覆盖）
  quality_drop_main_pct: 1.5    # 相对 Teacher 允许精度跌幅（%）
  quality_drop_q_only_pct: 2.0  # 量化单独节点的容忍线
  speedup_pair_p50_pct: 50      # 相对学生FP32，t_pair p50 至少降低（%）
  speedup_pair_p95_pct: 35      # p95 至少降低（%）

early_stop:
  no_improve_ckpt: 3            # 连续N个ckpt无改进停止
  max_epoch:
    distill: 30
    qat: 20
    prune_ft: 20

report:
  export_table: "reports/result_table.xlsx"
  plots_dir: "reports/plots/"
```

### `logs/unified_log_schema.json` 模板（精简可用）

```json
{
  "required": [
    "exp_id","combo","seed","dataset_id","split",
    "params_M","flops_G","size_MB","vram_GB",
    "chamfer","absrel","rmse","delta1","reproj_px",
    "t_pair_p50_ms","t_pair_p95_ms","t_scene_s","pairs_per_sec",
    "gpu_hours","commit_hash","datetime"
  ],
  "properties": {
    "exp_id": {"type":"string"},
    "combo":  {"type":"string"},
    "rho":    {"type":["number","null"]},
    "T":      {"type":["number","null"]},
    "beta":   {"type":["number","null"]},
    "gamma":  {"type":["number","null"]},
    "bits_w": {"type":["integer","null"]},
    "bits_a": {"type":["integer","null"]},
    "keep_list": {"type":["string","null"]},

    "params_M":{"type":"number"},
    "flops_G": {"type":"number"},
    "size_MB": {"type":"number"},
    "vram_GB": {"type":"number"},

    "chamfer":{"type":"number"},
    "absrel":{"type":"number"},
    "rmse":{"type":"number"},
    "delta1":{"type":"number"},
    "reproj_px":{"type":"number"},

    "t_pair_p50_ms":{"type":"number"},
    "t_pair_p95_ms":{"type":"number"},
    "t_scene_s":{"type":"number"},
    "pairs_per_sec":{"type":"number"},

    "edge_device":{"type":["object","null"],
      "properties":{
        "model":{"type":"string"},
        "soc":{"type":"string"},
        "ram":{"type":"string"},
        "power_avg_W":{"type":["number","null"]},
        "power_peak_W":{"type":["number","null"]},
        "throttle":{"type":["boolean","null"]}
      }
    },

    "dataset_id":{"type":"string"},
    "split":{"type":"string"},
    "num_pairs":{"type":["integer","null"]},
    "calibration_set_hash":{"type":["string","null"]},

    "pytorch_ver":{"type":["string","null"]},
    "cuda_ver":{"type":["string","null"]},
    "tensorrt_ver":{"type":["string","null"]},
    "modelopt_ver":{"type":["string","null"]},
    "commit_hash":{"type":"string"},

    "notes":{"type":["string","null"]},
    "gpu_hours":{"type":"number"},
    "seed":{"type":"integer"},
    "datetime":{"type":"string","description":"ISO8601"}
  }
}
```

### 度量口径（人话版）

- t_pair：一对图像从读入→前处理→模型→后处理→结果出炉的完整时延；统计 p50/p95。

- t_scene：按 `pair_graph` 把一整个场景要跑的 pairs 全跑完需要多少秒。

- pairs/sec：吞吐量；对 DUSt3R 比 FPS 更合适。

- quality_drop_main_pct：和 Teacher 的相对跌幅（%）。

- calibration_set_hash：校准集文件的哈希，用来证明量化用的是同一批图片。

附注：把上述 YAML/JSON 模板直接保存为相应文件可用于统一评测脚本读取与日志校验。