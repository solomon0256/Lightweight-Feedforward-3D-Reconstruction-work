# Cursor 连接 Notion 知识库指南

> **创建日期**: 2025-12-27  
> **目的**: 将 Cursor IDE 连接到 Notion 知识库，实现知识库与代码开发的集成

---

## 📋 概述

Cursor 支持通过 **MCP (Model Context Protocol)** 连接到 Notion，让你可以在 Cursor 中：
- 读取 Notion 页面内容
- 将项目文档同步到 Notion
- 在代码开发时参考知识库内容
- 自动更新项目进度到 Notion

---

## 🔧 配置步骤

### 步骤 1: 创建 Notion 集成

1. **登录 Notion**
   - 访问 [Notion 集成页面](https://www.notion.so/my-integrations)
   - 或：Notion → Settings & Members → Connections → Develop or manage integrations

2. **创建新集成**
   - 点击 "New integration"
   - 填写信息：
     - **Name**: `Cursor-DUSt3R-Project` (或你喜欢的名称)
     - **Type**: Internal Integration
     - **Associated workspace**: 选择你的工作区
   
3. **设置权限**
   - 建议权限：
     - ✅ Read content
     - ✅ Insert content
     - ✅ Update content
     - ✅ Comment (可选)

4. **获取 Token**
   - 创建成功后，复制 **Internal Integration Token**
   - 格式类似：`secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
   - ⚠️ **重要**: 妥善保存，只显示一次！

5. **分享页面给集成**
   - 在 Notion 中，打开你想连接的页面
   - 点击右上角 "..." → "Add connections"
   - 选择你刚创建的集成 `Cursor-DUSt3R-Project`
   - 这样集成才能访问该页面

---

### 步骤 2: 在 Cursor 中配置 MCP

#### 方法 A: 通过 Cursor 设置界面（推荐）

1. **打开 Cursor 设置**
   - 按 `Ctrl+,` 或 `Cmd+,`
   - 或：File → Preferences → Settings

2. **找到 MCP 设置**
   - 搜索 "MCP" 或 "Model Context Protocol"
   - 或导航到：Features → MCP Servers

3. **添加 MCP 服务器**
   - 点击 "Add New MCP Server" 或 "New MCP Server"
   - 这会打开 `cursor/mcp.json` 文件（或创建新文件）

#### 方法 B: 直接编辑配置文件

1. **找到配置文件位置**
   - Windows: `%APPDATA%\Cursor\User\mcp.json`
   - 或：Cursor Settings → 搜索 "mcp.json"

2. **编辑配置文件**

在 `mcp.json` 中添加以下配置：

```json
{
  "mcpServers": {
    "notion": {
      "command": "npx",
      "args": [
        "-y",
        "@suekou/mcp-notion-server"
      ],
      "env": {
        "NOTION_API_TOKEN": "你的_NOTION_TOKEN_在这里"
      }
    }
  }
}
```

**重要**: 将 `你的_NOTION_TOKEN_在这里` 替换为你在步骤 1 中获取的 Token！

---

### 步骤 3: 安装依赖（如果需要）

如果 `npx` 命令不可用，可能需要：

```powershell
# 检查 Node.js 是否安装
node --version

# 如果没有，需要先安装 Node.js
# 下载地址: https://nodejs.org/
```

---

### 步骤 4: 重启 Cursor

1. **完全关闭 Cursor**（所有窗口）
2. **重新打开 Cursor**
3. **验证连接**
   - 打开 Cursor Chat (Ctrl+L)
   - 尝试询问 Notion 相关内容
   - 或查看 MCP 服务器状态

---

## ✅ 验证连接

### 测试 1: 检查 MCP 服务器状态

在 Cursor 中：
1. 打开命令面板 (`Ctrl+Shift+P`)
2. 搜索 "MCP" 或 "Model Context"
3. 查看 MCP 服务器列表，应该看到 "notion" 服务器

### 测试 2: 在对话中测试

在 Cursor Chat 中尝试：
```
@notion 列出我的 Notion 页面
```

或：
```
从我的 Notion 知识库中查找关于 DUSt3R 的信息
```

---

## 🎯 使用场景

### 场景 1: 读取项目文档

```
@notion 读取我的项目计划页面
```

### 场景 2: 同步代码到 Notion

```
将当前代码更改记录到 Notion 项目日志
```

### 场景 3: 参考知识库内容

```
根据我的 Notion 知识库中的论文笔记，优化这段代码
```

---

## 🔍 故障排查

### 问题 1: MCP 服务器连接失败

**可能原因**:
- Notion Token 错误
- 页面未分享给集成
- Node.js 未安装

**解决方案**:
1. 检查 Token 是否正确（无多余空格）
2. 确认页面已分享给集成
3. 安装 Node.js: https://nodejs.org/

### 问题 2: 无法读取 Notion 内容

**可能原因**:
- 权限不足
- 页面 ID 错误

**解决方案**:
1. 检查集成权限设置
2. 确认页面已正确分享

### 问题 3: npx 命令不可用

**解决方案**:
```powershell
# 安装 Node.js
# 或使用完整路径
npm install -g @suekou/mcp-notion-server
```

---

## 📚 相关资源

- [Cursor MCP 文档](https://docs.cursor.com/guides/working-with-context)
- [Notion API 文档](https://developers.notion.com/)
- [MCP Notion Server](https://www.npmjs.com/package/@suekou/mcp-notion-server)

---

## 🔐 安全提示

1. **不要将 Token 提交到 Git**
   - 使用环境变量或 Cursor 的配置管理
   - 将 `mcp.json` 添加到 `.gitignore`

2. **定期轮换 Token**
   - 如果 Token 泄露，立即在 Notion 中撤销并重新创建

3. **最小权限原则**
   - 只给集成必要的权限

---

## 📝 下一步

配置完成后，你可以：

1. **创建项目知识库结构**
   - 在 Notion 中创建项目页面
   - 组织文档、笔记、进度跟踪

2. **设置自动同步**
   - 使用 Cursor 的自动化功能
   - 定期更新项目状态到 Notion

3. **集成到工作流**
   - 在代码开发时参考 Notion 文档
   - 将代码注释和文档同步到 Notion

---

*最后更新: 2025-12-27*

