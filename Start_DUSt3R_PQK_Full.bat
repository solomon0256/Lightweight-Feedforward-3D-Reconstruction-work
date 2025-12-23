@echo off
REM DUSt3R-PQK 轻量化实验项目 - 完整启动
REM 双击此文件: 打开 VS Code + 激活虚拟环境 + 打开终端

cd /d "C:\Users\SoLoMoN\Documents\GitHub\Lightweight-Feedforward-3D-Reconstruction-work"

REM 打开 VS Code
start "" code .

REM 打开 PowerShell 并激活虚拟环境
start powershell -NoExit -Command "cd 'C:\Users\SoLoMoN\Documents\GitHub\Lightweight-Feedforward-3D-Reconstruction-work'; .\.venv\Scripts\Activate.ps1; Write-Host ''; Write-Host '=== DUSt3R-PQK 环境已激活 ===' -ForegroundColor Green; Write-Host 'PyTorch:' (python -c 'import torch; print(torch.__version__)'); Write-Host 'CUDA:' (python -c 'import torch; print(torch.cuda.is_available())'); Write-Host ''"
