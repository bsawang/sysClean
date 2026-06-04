# 🧹 SysClean — C 盘空间清理工具 / C Drive Cleanup Tool

<p align="center">
  <a href="#zh">🇨🇳 中文</a> · <a href="#en">🇬🇧 English</a>
</p>

---

<div id="zh"></div>

## 🇨🇳 中文

本地 Windows 磁盘清理工具，提供 Web 界面。支持扫描临时文件、系统缓存、安装残留和浏览器缓存 — 按风险等级展示结果，勾选确认后清理。

### 在 Claude Code 中安装

通过 Git 地址直接安装 Skill：

```bash
claude skills add https://github.com/bsawang/sysclean
```

安装后在 Claude Code 会话中调用 `/sysclean` 即可使用。

### 作为 Skill 使用（给 AI 助手）

当 AI 收到清理请求时，执行以下流程：

1. 运行 `python app.py` 启动服务
2. 引导用户在浏览器中打开 **http://localhost:5000**
3. 用户直接在 Web 界面中操作（选择分类 → 扫描 → 查看 → 清理）
4. AI 解释风险等级和操作流程，但绝不自动删除文件

> **提示：** 在 URL 后添加 `?lang=en` 或 `?lang=zh` 可随时切换中英文界面。也可以在界面右上角的下拉菜单中直接切换。

#### 操作流程

| 步骤 | 操作 |
|------|------|
| 1 | 在左侧勾选需要扫描的分类 |
| 2 | 点击 **「开始扫描」** |
| 3 | 查看实时进度和发现结果 |
| 4 | 扫描完成后，逐项勾选要清理的文件 |
| 5 | 点击 **「清理选中」** |
| 6 | 在确认弹窗中检查待删清单 |
| 7 | 确认后执行清理 |
| 8 | 查看完成报告 |

#### 安全机制

- **不会自动删除** — 所有清理操作都需要用户在浏览器中确认
- 每项文件都有**风险标签**（安全 / 注意 / 高风险）并附有说明
- 默认情况下文件会进入**回收站**（Windows）
- 使用**自定义 Web 弹窗**（非原生 `alert/confirm`），统一界面风格且支持双语

### 其他环境使用

你也可以像普通 Flask 应用一样手动启动：

```bash
pip install -r requirements.txt
python app.py
```

然后在浏览器中打开 **http://localhost:5000**。

不依赖任何 AI 平台 — 普通用户也可直接通过 Web 界面操作。

### 界面语言

URL 后添加 `?lang=en` 切换英文，`?lang=zh` 切换中文。默认为中文。
也可通过界面右上角的下拉菜单**实时切换**，无需刷新页面。

---

<div id="en"></div>

## 🇬🇧 English

A local Windows disk cleanup tool with Web UI. Scan temp files, system cache, installer residue, and browser cache — view results with risk levels, then select and confirm before cleaning.

### Install in Claude Code

Install the skill directly via Git URL:

```bash
claude skills add https://github.com/bsawang/sysclean
```

Once installed, invoke `/sysclean` in any Claude Code session.

### Usage as a Skill (for AI Agents)

When the AI is invoked with a cleanup request, it:

1. Runs `python app.py` to start the server
2. Guides the user to open **http://localhost:5000** in their browser
3. The user interacts with the Web UI directly (select categories → scan → review → clean)
4. The AI explains risk levels and flow, but never deletes files automatically

> **Tip:** Append `?lang=en` or `?lang=zh` to the URL to switch between English and Chinese UI at any time. You can also toggle the language via the dropdown in the top-right corner.

#### Workflow

| Step | Action |
|------|--------|
| 1 | Check categories to scan on the left panel |
| 2 | Click **"Start Scan"** |
| 3 | Watch real-time progress and discovered files |
| 4 | After scan completes, check files to clean |
| 5 | Click **"Clean Selected"** |
| 6 | Review the deletion list in the confirmation dialog |
| 7 | Confirm to execute cleanup |
| 8 | View completion report |

#### Safety

- **No automatic deletion** — all clean operations require user confirmation in the browser
- Every item has a **risk label** (Safe / Caution / High Risk) with explanation
- Files go to **Recycle Bin** by default (Windows)
- **Custom Web modals** replace native `alert/confirm` for a consistent bilingual UI

### Usage in Other Environments

You can also start SysClean manually like any Flask app:

```bash
pip install -r requirements.txt
python app.py
```

Then open **http://localhost:5000** in your browser.

No AI platform required — any human user can operate it directly via the Web UI.

### Language

Add `?lang=en` to the URL for English UI, or `?lang=zh` for Chinese (default). You can also **switch in real time** via the dropdown in the top-right corner — no page refresh needed.

---

## 📄 License

MIT
