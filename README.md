# 🧹 SysClean — C 盘空间清理工具 / C Drive Cleanup Tool

<p align="center">
  <a href="#en">🇬🇧 English</a> · <a href="#zh">🇨🇳 中文</a>
</p>

---

## <a id="en"></a>🇬🇧 English

A local Windows disk cleanup tool with Web UI. Scan temp files, system cache, installer residue, and browser cache — view results with risk levels, then select and confirm before cleaning.

### Quick Start

```bash
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5000** in your browser.

> **Tip:** Append `?lang=en` or `?lang=zh` to the URL to switch between English and Chinese UI at any time.

### For AI Agents

This is a **Flask web app** with a browser-based UI. It does NOT require any specific AI platform — any agent (Claude, Gemini, Cursor, Copilot, etc.) or human can use it.

#### How to operate

1. Run `python app.py` to start the server
2. Guide the user to open http://localhost:5000 in their browser
3. The user interacts with the Web UI directly (select categories → scan → review → clean)
4. You only need to start the server and explain the flow

#### Safety

- **No automatic deletion** — all clean operations require user confirmation in the browser
- Every item has a **risk label** (Safe / Caution / High Risk) with explanation
- Files go to **Recycle Bin** by default (Windows)

#### Workflow

1. Check categories to scan on the left panel
2. Click **"Start Scan"**
3. Watch real-time progress and discovered files
4. After scan completes, check files to clean
5. Click **"Clean Selected"**
6. Review the deletion list in the confirmation dialog
7. Confirm to execute cleanup
8. View completion report

### Language

Add `?lang=en` to the URL for English UI, or `?lang=zh` for Chinese. Default is Chinese.

### Claude Code Users

See [sysclean.md](./sysclean.md) for Claude-specific instructions.

---

## <a id="zh"></a>🇨🇳 中文

本地 Windows 磁盘清理工具，提供 Web 界面。支持扫描临时文件、系统缓存、安装残留和浏览器缓存 — 按风险等级展示结果，勾选确认后清理。

### 快速开始

```bash
pip install -r requirements.txt
python app.py
```

在浏览器中打开 **http://localhost:5000**。

> **提示：** 在 URL 后添加 `?lang=en` 或 `?lang=zh` 可随时切换中英文界面。

### 给 AI 助手的说明

这是一个基于 **Flask** 的 Web 应用，通过浏览器操作。不依赖任何特定的 AI 平台 — 任何 AI 助手（Claude、Gemini、Cursor、Copilot 等）或人类用户均可使用。

#### 操作方式

1. 运行 `python app.py` 启动服务
2. 引导用户在浏览器中打开 http://localhost:5000
3. 用户直接在 Web 界面中操作（选择分类 → 扫描 → 查看 → 清理）
4. 你只需启动服务器并说明流程

#### 安全机制

- **不会自动删除** — 所有清理操作都需要用户在浏览器中确认
- 每项文件都有**风险标签**（安全 / 注意 / 高风险）并附有说明
- 默认情况下文件会进入**回收站**（Windows）

#### 操作流程

1. 在左侧勾选需要扫描的分类
2. 点击 **「开始扫描」**
3. 查看实时进度和发现结果
4. 扫描完成后，逐项勾选要清理的文件
5. 点击 **「清理选中」**
6. 在确认弹窗中检查待删清单
7. 确认后执行清理
8. 查看完成报告

### 界面语言

URL 后添加 `?lang=en` 切换英文，`?lang=zh` 切换中文。默认为中文。

### Claude Code 用户

Claude 专属说明请参见 [sysclean.md](./sysclean.md)。

---

## 📄 License

MIT
