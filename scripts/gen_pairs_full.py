#!/usr/bin/env python3
import os
import random

base = '/workspace/Lightweight-Feedforward-3D-Reconstruction-work/datasets/7-scenes-raw'
scenes = ['chess', 'fire', 'heads', 'office', 'pumpkin', 'redkitchen', 'stairs']
pairs = []

for scene in scenes:
    scene_path = os.path.join(base, scene)
    seqs = [d for d in os.listdir(scene_path) if d.startswith('seq-') and not d.endswith('.zip')]
    for seq in seqs:
        seq_path = os.path.join(scene_path, seq)
        imgs = sorted([f for f in os.listdir(seq_path) if f.endswith('.color.png')])
        for i in range(len(imgs)-1):
            p1 = os.path.join(seq_path, imgs[i])
            p2 = os.path.join(seq_path, imgs[i+1])
            pairs.append(p1 + '|' + p2)

random.shuffle(pairs)
n = len(pairs)
train = pairs[:int(n*0.8)]
val = pairs[int(n*0.8):]

with open('/workspace/Lightweight-Feedforward-3D-Reconstruction-work/datasets/train_pairs.lst', 'w') as f:
    f.write('\n'.join(train))
with open('/workspace/Lightweight-Feedforward-3D-Reconstruction-work/datasets/val_pairs.lst', 'w') as f:
    f.write('\n'.join(val))

print('Total pairs:', n)
print('Train:', len(train), 'Val:', len(val))
