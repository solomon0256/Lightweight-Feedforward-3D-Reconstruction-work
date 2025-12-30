# Windows本地与vast.ai服务器配置说明

> **日期**: 2025-12-30  
> **目标**: 说明Windows本地开发环境和vast.ai服务器环境的区别，以及需要做的配置

---

## 🔍 关键理解

### Windows本地 vs vast.ai服务器

| 环境 | 操作系统 | PyTorch状态 | 用途 |
|------|----------|-------------|------|
| **Windows本地** | Windows 10/11 | 需要安装 | 代码开发、本地验证 |
| **vast.ai服务器** | Linux (Ubuntu) | ✅ 开箱即用 | 实际训练和实验 |

---

## ✅ vast.ai服务器：PyTorch开箱即用

### 选择PyTorch (Vast)模板后

**PyTorch已经预装好了！** ✅

**连接服务器后，直接验证**：
```bash
# 1. SSH连接服务器
ssh -p <端口> root@<vast.ai域名>

# 2. 验证PyTorch（开箱即用，无需安装）
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}')"

# 预期输出：
# PyTorch: 2.x.x+cu121
# CUDA: True

# 3. 验证GPU
nvidia-smi

# 预期输出：显示A100 GPU信息
```

**结论**: ✅ **vast.ai服务器上PyTorch开箱即用，无需安装！**

---

## 💻 Windows本地：需要配置（可选）

### 如果你只在服务器上工作

**Windows本地不需要安装PyTorch！**

**工作流程**:
1. ✅ Windows本地：编写代码、编辑文件
2. ✅ 上传到服务器：使用SCP或Git
3. ✅ 服务器上运行：所有实验在服务器上执行

**Windows本地只需要**:
- ✅ 代码编辑器（VS Code / Cursor）
- ✅ Git（用于版本控制）
- ✅ SSH客户端（用于连接服务器）
- ✅ 文件传输工具（WinSCP，可选）

---

### 如果你想在Windows本地也运行代码（可选）

**需要安装PyTorch CUDA版本**：

#### 方法1：使用conda（推荐）

```powershell
# 1. 安装Anaconda或Miniconda
# 下载：https://www.anaconda.com/products/distribution

# 2. 创建虚拟环境
conda create -n dust3r python=3.10
conda activate dust3r

# 3. 安装PyTorch CUDA版本
# 访问：https://pytorch.org/get-started/locally/
# 选择：Windows + CUDA 12.1（或你的CUDA版本）

# 例如（CUDA 12.1）：
conda install pytorch torchvision torchaudio pytorch-cuda=12.1 -c pytorch -c nvidia

# 4. 验证安装
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}')"
```

#### 方法2：使用pip

```powershell
# 1. 确保有Python 3.8+
python --version

# 2. 安装PyTorch CUDA版本
# 访问：https://pytorch.org/get-started/locally/
# 复制对应的pip命令

# 例如（CUDA 12.1）：
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 3. 验证安装
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}')"
```

---

## 🚀 推荐工作流程

### 方案1：只在服务器上工作（最简单）⭐⭐⭐⭐⭐

**Windows本地**:
- ✅ 只安装：Git、SSH客户端、代码编辑器
- ❌ 不需要安装PyTorch

**工作流程**:
```
1. Windows本地：编写/编辑代码
2. Git提交：git add/commit/push
3. 服务器上：git pull
4. 服务器上：运行实验
```

**优点**:
- ✅ 简单，不需要配置Windows环境
- ✅ 所有实验在GPU服务器上运行
- ✅ 不需要担心Windows CUDA兼容性

---

### 方案2：Windows本地也运行（可选）

**Windows本地**:
- ✅ 安装PyTorch CUDA版本
- ✅ 安装项目依赖

**工作流程**:
```
1. Windows本地：编写/编辑代码
2. Windows本地：快速验证（可选）
3. 服务器上：完整实验
```

**优点**:
- ✅ 可以在本地快速验证
- ✅ 不依赖服务器也能开发

**缺点**:
- ⚠️ 需要配置Windows CUDA环境
- ⚠️ 本地GPU性能可能不如服务器

---

## 📋 具体配置步骤

### 步骤1：vast.ai服务器配置（必须）

#### 1.1 连接服务器

```powershell
# Windows PowerShell
ssh -p <端口> root@<vast.ai域名>
```

#### 1.2 验证PyTorch（开箱即用）

```bash
# 在服务器上执行
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}')"

# 预期输出：
# PyTorch: 2.x.x+cu121
# CUDA: True
```

**如果PyTorch已安装** ✅：无需任何操作，直接使用！

**如果PyTorch未安装**（极少见）：
```bash
# 安装PyTorch（通常不需要）
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

#### 1.3 安装项目依赖

```bash
# 克隆项目
git clone --recursive <repo-url>
cd Lightweight-Feedforward-3D-Reconstruction-work

# 安装项目依赖
pip install -r requirements.txt
```

---

### 步骤2：Windows本地配置（可选）

#### 2.1 安装Git（如果还没有）

```powershell
# 下载：https://git-scm.com/download/win
# 安装后验证
git --version
```

#### 2.2 安装SSH客户端

**Windows 10/11自带SSH**，直接使用：
```powershell
# 验证SSH
ssh --version
```

#### 2.3 安装代码编辑器

- **VS Code**: https://code.visualstudio.com/
- **Cursor**: 你已经在用 ✅

#### 2.4 安装PyTorch（可选，如果想本地运行）

```powershell
# 使用conda（推荐）
conda install pytorch torchvision torchaudio pytorch-cuda=12.1 -c pytorch -c nvidia

# 或使用pip
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

---

## ⚠️ 常见问题

### 问题1：Windows本地需要安装PyTorch吗？

**答案**: ❌ **不需要！**

**原因**:
- ✅ 所有实验在服务器上运行
- ✅ Windows本地只用于编写代码
- ✅ 代码通过Git或SCP上传到服务器

**例外**: 如果你想在Windows本地也运行代码（快速验证），才需要安装PyTorch。

---

### 问题2：vast.ai服务器上PyTorch需要安装吗？

**答案**: ✅ **不需要！PyTorch (Vast)模板已经预装了PyTorch**

**验证方法**:
```bash
# 连接服务器后
python -c "import torch; print(torch.__version__)"
```

**如果已安装** ✅：直接使用，无需任何操作！

**如果未安装**（极少见）：
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

---

### 问题3：Windows本地和服务器环境不一致怎么办？

**答案**: ✅ **这是正常的，不需要一致！**

**原因**:
- ✅ Windows本地：只用于编写代码
- ✅ 服务器：用于运行实验
- ✅ 代码通过Git同步，环境在服务器上配置

**最佳实践**:
- ✅ 在服务器上运行所有实验
- ✅ Windows本地只用于代码编辑
- ✅ 使用Git同步代码

---

## 📝 快速检查清单

### vast.ai服务器（必须）

- [ ] 选择 **PyTorch (Vast)** 模板
- [ ] 连接服务器：`ssh -p <端口> root@<vast.ai域名>`
- [ ] 验证PyTorch：`python -c "import torch; print(torch.__version__)"`
- [ ] 验证GPU：`nvidia-smi`
- [ ] 克隆项目：`git clone --recursive <repo-url>`
- [ ] 安装依赖：`pip install -r requirements.txt`

### Windows本地（可选）

- [ ] 安装Git（如果还没有）
- [ ] 安装SSH客户端（Windows自带）
- [ ] 安装代码编辑器（VS Code / Cursor）
- [ ] **可选**：安装PyTorch（如果想本地运行）

---

## ✅ 总结

### vast.ai服务器

✅ **PyTorch开箱即用** - 选择PyTorch (Vast)模板后，无需安装PyTorch！

**需要做的**:
1. 连接服务器
2. 验证PyTorch（确认已安装）
3. 安装项目依赖（`pip install -r requirements.txt`）

---

### Windows本地

❌ **不需要安装PyTorch** - 除非你想在本地也运行代码

**需要做的**:
1. 安装Git（用于版本控制）
2. 安装SSH客户端（Windows自带）
3. 安装代码编辑器（VS Code / Cursor）
4. **可选**：安装PyTorch（如果想本地运行）

---

## 🎯 推荐方案

### 最简单方案：只在服务器上工作

**Windows本地**:
- ✅ Git
- ✅ SSH客户端
- ✅ 代码编辑器
- ❌ 不需要PyTorch

**vast.ai服务器**:
- ✅ PyTorch已预装（开箱即用）
- ✅ 只需安装项目依赖

**工作流程**:
1. Windows本地：编写代码
2. Git提交：`git add/commit/push`
3. 服务器上：`git pull`
4. 服务器上：运行实验

---

**最后更新**: 2025-12-30

