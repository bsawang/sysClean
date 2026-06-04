# SysClean — C 盘空间清理工具 / C Drive Cleanup Tool

A local Windows disk cleanup tool with Web UI. Scan temp files, system cache,
installer residue, and browser cache — view results with risk levels, then
select and confirm before cleaning.

## Quick Start

```bash
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5000** in your browser.

## For AI Agents

This is a **Flask web app** with a browser-based UI. It does NOT require any
specific AI platform — any agent (Claude, Gemini, Cursor, Copilot, etc.) or
human can use it.

### How to operate

1. Run `python app.py` to start the server
2. Guide the user to open http://localhost:5000 in their browser
3. The user interacts with the Web UI directly (select categories → scan → review → clean)
4. You only need to start the server and explain the flow

### Safety

- **No automatic deletion** — all clean operations require user confirmation in the browser
- Every item has a **risk label** (Safe / Caution / High Risk) with explanation
- Files go to **Recycle Bin** by default (Windows)

### Language

Add `?lang=en` to the URL for English UI, or `?lang=zh` for Chinese. Default is Chinese.

## Claude Code Users

See `sysclean.md` for Claude-specific instructions.
