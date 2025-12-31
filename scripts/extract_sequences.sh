#!/bin/bash
# 解压7-Scenes各场景的sequence zip文件

cd /root/Lightweight-Feedforward-3D-Reconstruction-work/datasets/7-scenes

for scene in chess fire heads office pumpkin redkitchen stairs; do
    echo "解压 $scene 场景的sequence文件..."
    cd "$scene"
    for zip in seq-*.zip; do
        if [ -f "$zip" ]; then
            echo "  解压 $zip..."
            unzip -q "$zip" && rm -f "$zip" && echo "  ✅ $zip 完成"
        fi
    done
    cd ..
done

echo ""
echo "=== 验证结果 ==="
for scene in chess fire heads office pumpkin redkitchen stairs; do
    file_count=$(find "$scene" -name "*.color.png" -o -name "*.depth.png" 2>/dev/null | wc -l)
    echo "$scene: $file_count 个图像文件"
done

echo ""
echo "✅ 所有sequence解压完成！"

