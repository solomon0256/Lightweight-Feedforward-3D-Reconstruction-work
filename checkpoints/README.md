# Checkpoints 目录

此目录用于存放模型权重文件。

## ⚠️ 重要说明

模型文件太大（>1GB），**不会上传到 GitHub**。

请在云服务器上运行以下命令下载：

```bash
# 下载推荐的 512_dpt 模型 (~1.3GB)
python scripts/download_checkpoints.py --model 512_dpt

# 或下载所有模型
python scripts/download_checkpoints.py --all

# 查看可用模型
python scripts/download_checkpoints.py --list
```

## 可用模型

| 模型 | 大小 | 说明 |
|------|------|------|
| `512_dpt` | ~1.3GB | **推荐**，512x384，DPT head，精度最高 |
| `512_linear` | ~1.1GB | 512x384，Linear head |
| `224_linear` | ~1.1GB | 224x224，Linear head |
| `croco_v2` | ~1.1GB | CroCo V2 预训练（训练用） |

## 文件结构

下载后应有：
```
checkpoints/
├── README.md (本文件)
├── DUSt3R_ViTLarge_BaseDecoder_512_dpt.pth
└── (其他模型，按需下载)
```
