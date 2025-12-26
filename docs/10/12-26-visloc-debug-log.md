# 2025-12-26 DUSt3R Visloc 评估调试工作日志

## 目标
在 7-scenes heads 数据集上运行 DUSt3R 官方 visloc 评估，复现论文 Table 6 结果：
- **论文期望结果**: heads 场景 2cm / 1.37° (2D-matching 方法)

---

## 问题发现

### 问题1: 之前的评估数据损坏
- 发现之前下载的 7-scenes 数据集图像文件为 0 字节（损坏/不完整）
- 导致之前所有评估结果无效

### 解决方案
删除损坏数据，重新从 Microsoft 官方源下载：
```powershell
Remove-Item -Recurse -Force datasets/7-scenes/heads
# 下载官方数据
Invoke-WebRequest -Uri "http://download.microsoft.com/download/2/8/5/28564B23-0828-408F-8631-23B1EFF1DAC8/heads.zip" -OutFile heads.zip
```

---

## 问题2: Kapture 格式转换

### 问题描述
DUSt3R visloc 需要 Kapture 格式的数据集结构：
```
7-scenes/heads/
├── mapping/
│   └── sensors/
│       └── records_data/
│           └── seq-02/
│               ├── frame-000000.color.png
│               └── frame-000000.depth.reg
├── query/
│   └── sensors/
│       └── records_data/
│           └── seq-01/
│               └── frame-000000.color.png
└── pairfiles/
    └── query/
        └── pairs_top20.txt
```

### 解决方案
创建了 `scripts/import_7scenes_kapture.py` 脚本进行格式转换。

---

## 问题3: Pairsfile 路径错误

### 错误信息
```
FileNotFoundError: pairfiles/query/pairs_seq.txt not found
```

### 原因
参数中使用了 `pairsfile='pairs_seq'`，但实际文件名是 `pairs_top20.txt`

### 解决方案
```python
# 错误
pairsfile='pairs_seq'
# 正确
pairsfile='pairs_top20'
```

---

## 问题4: Depth 文件格式错误（第一次）

### 问题描述
最初的 depth 转换代码在文件开头写入了 W, H header：
```python
# 错误的实现
with open(output_path, 'wb') as f:
    np.array([W, H], dtype=np.int32).tofile(f)  # 多余的 header!
    depth_meters.astype(np.float32).tofile(f)
```

### 错误现象
Kapture 无法正确读取 depth 文件，导致 `pts3d_rescaled` 全为 NaN。

### 解决方案
修改为 raw float32 格式（无 header）：
```python
# 正确的实现
with open(output_path, 'wb') as f:
    depth_meters.astype(np.float32).tofile(f)
```

---

## 问题5: PnP 全部失败（所有结果为 inf）

### 错误现象
```
median_pos_error=inf, median_angular_error=inf
```

所有 1000 张图像的 PnP 都失败，结果文件显示：
```
1.0 -0.0 -0.0 -0.0 0.0 0.0 0.0  # identity pose (失败时的默认值)
```

### 调试过程

#### Step 1: 检查数据集加载
```python
dataset = VislocSevenScenes(...)
views = dataset[0]
print(views[1]['pts3d_rescaled'].shape)  # torch.Size([384, 512, 3])
print(views[1]['valid_rescaled'].sum())  # 179952 valid points
```
**结论**: 数据加载正确。

#### Step 2: 检查 inference 输出
```python
output = inference([tuple(imgs)], model, 'cuda', ...)
confidence_masks[0].sum()  # 129794
confidence_masks[1].sum()  # 102939
```
**结论**: 模型推理正常，有足够的置信点。

#### Step 3: 检查匹配
```python
num_matches = find_reciprocal_matches(PQ, PM)
print(num_matches)  # 30835 matches
```
**结论**: 匹配成功，有 30835 个互惠匹配点。

#### Step 4: 发现根本原因 - 缺少 poselib！
```python
import poselib
# ModuleNotFoundError: No module named 'poselib'
```

### 解决方案
```powershell
pip install poselib
```

安装后 PnP 成功：
```python
pose, info = poselib.estimate_absolute_pose(...)
print('inliers:', info['inliers'])  # 大量 True
print('R:', pose.R)  # 有效旋转矩阵
print('t:', pose.t)  # 有效平移向量
```

---

## 问题6: 评估结果与论文差距大

### 当前结果
```
median_pos_error=1.1565m, median_angular_error=65.49°
acc@0.1m,1deg=0.000
acc@0.25m,2deg=0.000
acc@0.5m,5deg=0.000
acc@5m,10deg=0.300
```

### 论文期望结果
```
heads: 2cm / 1.37° (2D-matching)
heads: 4cm / 1.33° (scaled rel-pose)
```

### 差距分析
- 位置误差: 1.16m vs 0.02m = **58倍差距**
- 角度误差: 65.49° vs 1.37° = **48倍差距**

### 可能原因（待排查）

#### 1. cam_to_world 变换问题
7-scenes 的 pose 格式可能与 DUSt3R 期望的不同：
- 7-scenes pose 文件格式: 4x4 矩阵，可能是 world_to_cam 而非 cam_to_world
- 需要验证是否需要求逆

#### 2. 坐标系不一致
- 7-scenes 使用的坐标系可能与 DUSt3R 期望的不同
- OpenCV vs OpenGL 坐标系差异

#### 3. Depth 单位问题
- 7-scenes depth: 16-bit PNG, 单位 mm
- 转换为 meters: `depth_mm / 1000.0`
- 需要验证转换是否正确

#### 4. 内参问题
7-scenes 官方内参:
```
fx = fy = 585.0
cx = 320.0, cy = 240.0
```
但我们的转换脚本使用了:
```
fx = fy = 525.0  # 可能错误!
```

---

## 关键代码文件

### 1. scripts/import_7scenes_kapture.py
用于将 7-scenes 原始数据转换为 Kapture 格式。

关键函数：
- `convert_depth_to_reg()`: 将 16-bit PNG depth 转换为 float32 meters
- `create_kapture_structure()`: 创建目录结构和配置文件

### 2. third_party/dust3r/dust3r_visloc/datasets/sevenscenes.py
DUSt3R 的 7-scenes 数据集加载器。

关键逻辑：
```python
# Line 104: 从 depth 恢复世界坐标 3D 点
pts3d_full, pts3d_valid = depthmap_to_absolute_camera_coordinates(
    depthmap, intrinsics, cam_to_world
)
```

### 3. third_party/dust3r/visloc.py
主评估脚本。

关键逻辑：
```python
# Line 92: 使用 DUSt3R 预测的 3D 点进行匹配
pts3d = [pred1['pts3d'].squeeze(0), pred2['pts3d_in_other_view'].squeeze(0)]

# Line 110: 使用 GT depth 的 3D 点进行 PnP
valid_pts3d = map_view['pts3d_rescaled'][matches_im1[:, 1], matches_im1[:, 0]]
```

---

## 数据集状态

### 当前结构
```
datasets/7-scenes/heads/
├── mapping/
│   └── sensors/
│       ├── records_camera.txt (1000 entries)
│       ├── records_depth.txt (1000 entries)
│       ├── rigs.txt
│       ├── sensors.txt
│       ├── trajectories.txt (1000 poses)
│       └── records_data/
│           └── seq-02/ (2000 files: 1000 color + 1000 depth)
├── query/
│   └── sensors/
│       ├── records_camera.txt (1000 entries)
│       ├── rigs.txt
│       ├── sensors.txt
│       ├── trajectories.txt (1000 poses)
│       └── records_data/
│           └── seq-01/ (1000 color files, no depth)
└── pairfiles/
    └── query/
        └── pairs_top20.txt (20000 pairs)
```

### Depth 文件格式
- 文件名: `frame-XXXXXX.depth.reg`
- 格式: Raw float32 binary
- 尺寸: 640 x 480
- 单位: meters
- 范围: 0 ~ 1.056m (heads 场景)

---

## 下一步计划

### 优先级1: 验证 pose 格式
```python
# 检查 7-scenes pose 是否需要求逆
pose = np.loadtxt('frame-000000.pose.txt')
# 验证是 cam_to_world 还是 world_to_cam
```

### 优先级2: 验证内参
```python
# 使用官方内参 fx=fy=585 重新转换
```

### 优先级3: 对比官方实现
查看 DUSt3R 官方是否提供了 7-scenes 数据准备脚本。

---

## 命令记录

### 安装 poselib
```powershell
pip install poselib
```

### 运行 visloc 评估
```powershell
cd third_party/dust3r
python visloc.py \
    --model_name DUSt3R_ViTLarge_BaseDecoder_512_dpt \
    --dataset "VislocSevenScenes('C:/Users/SoLoMoN/Documents/GitHub/Lightweight-Feedforward-3D-Reconstruction-work/datasets/7-scenes/', subscene='heads', pairsfile='pairs_top20', topk=1)" \
    --pnp_mode poselib \
    --reprojection_error_diag_ratio 0.008 \
    --output_dir C:/Users/SoLoMoN/Documents/GitHub/Lightweight-Feedforward-3D-Reconstruction-work/outputs/visloc_heads
```

### 调试脚本
```python
# 检查数据加载
dataset = VislocSevenScenes(...)
views = dataset[0]
print('pts3d_rescaled:', views[1]['pts3d_rescaled'].shape)
print('valid count:', views[1]['valid_rescaled'].sum())

# 检查匹配
num_matches = find_reciprocal_matches(PQ, PM)
print('matches:', num_matches)

# 检查 PnP
pose, info = poselib.estimate_absolute_pose(...)
print('inliers:', sum(info['inliers']))
```

---

---

## 问题6: 内参错误 (CRITICAL)

### 问题发现
通过查阅 DUSt3R 官方代码 `dust3r_visloc/datasets/sevenscenes.py`：
```python
# for 7scenes, SIMPLE_PINHOLE
camera_params = kdata.sensors[camera_id].camera_params
W, H, f, cx, cy = camera_params
```

发现 DUSt3R 直接从 kapture 的 `sensors.txt` 读取内参！

### 当前错误的 sensors.txt
```
kinect_rgb, kinect_rgb, camera, SIMPLE_PINHOLE, 640, 480, 525.0, 320.0, 240.0
```

### 问题根源
7-scenes 数据集有两个常用内参版本：
- **fx=fy=525**: 一些早期实现使用
- **fx=fy=585**: 官方 Kinect 内参（正确值）

我们的转换脚本 `import_7scenes_kapture.py` 使用了错误的 525.0！

### 7-scenes 官方内参
```
fx = fy = 585.0  (focal length)
cx = 320.0       (principal point x)
cy = 240.0       (principal point y)
resolution: 640 x 480
```

### 影响分析
内参错误会导致：
1. **深度图 → 3D 点转换错误**: `x = (u - cx) * depth / fx`
2. **PnP 求解位姿错误**: 2D-3D 对应关系全部偏移
3. **位置误差放大**: 10% 的焦距误差可能导致米级位移误差

### 修复方案
更新 `sensors.txt` 文件：
```
kinect_rgb, kinect_rgb, camera, SIMPLE_PINHOLE, 640, 480, 585.0, 320.0, 240.0
kinect_depth, kinect_depth, depth, SIMPLE_PINHOLE, 640, 480, 585.0, 320.0, 240.0
```

---

## 总结

| 问题 | 状态 | 解决方案 |
|------|------|----------|
| 数据损坏 | ✅ 已解决 | 重新下载官方数据 |
| Kapture 格式 | ✅ 已解决 | 创建转换脚本 |
| Pairsfile 路径 | ✅ 已解决 | 使用正确的文件名 |
| Depth 格式 | ✅ 已解决 | 去除 header |
| 缺少 poselib | ✅ 已解决 | pip install poselib |
| **内参错误** | ⚠️ **待修复** | **525 → 585** |
| 结果差距大 | ❌ 待验证 | 修复内参后重新测试 |

**当前状态**: 发现关键问题 - 内参使用了错误的焦距 (525 vs 585)。这很可能是结果差距大的主要原因。需要：
1. 修复 sensors.txt 中的内参
2. 重新运行 visloc 评估
3. 验证结果是否接近论文水平
