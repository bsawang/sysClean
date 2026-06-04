---
name: sysclean
description: C 盘空间清理工具 — Web UI 选择分类扫描，实时进度，风险标注，确认后清理
---

# SysClean — C 盘空间清理 Skill

## Description
通过浏览器访问 Web UI，对 C 盘进行分类扫描和清理。支持临时文件、系统缓存、安装残留等分类，
每项标注风险等级和具体说明，确认后执行清理。

## Usage

### 1. 启动服务
```bash
cd /path/to/sysclean
pip install -r requirements.txt
python app.py
```

### 2. 打开浏览器
访问 http://localhost:5000 （或 ?lang=en 切换英文）

### 3. 操作流程
1. 在左侧勾选需要扫描的分类
2. 点击「开始扫描」
3. 查看实时进度和发现结果
4. 扫描完成后，逐项勾选要清理的文件
5. 点击「清理选中」
6. 在确认弹窗中检查待删清单
7. 确认后执行清理
8. 查看完成报告

### 4. 清理完后关闭
在终端按 Ctrl+C 停止服务

## Safety Rules (Claude MUST follow)
- **绝对不执行任何清理操作** — 必须等待用户在 Web UI 中勾选并二次确认
- 首次启动后引导用户打开浏览器
- 告知用户风险等级的含义（安全/注意/高风险）
- 如果用户询问是否可以删除，引导用户查看风险说明
