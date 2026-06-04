"""
SysClean - Flask Application

Provides web API for scanning and cleaning Windows system files.
Routes handle disk info, scan operations, cleanup execution via SSE,
and process listing with i18n support.
"""

import json
import os
import threading
import time

import psutil
from flask import Flask, render_template, request, Response, jsonify, g

from scanner import ScannerEngine, ScanItem, RiskLevel
from cleaner import CleanExecutor

# i18n — real module arrives in Task 5; fallback to stubs so app.py is
# importable today.
try:
    from i18n import get_text, get_all_texts
except ImportError:
    def get_text(key, lang="zh", **kwargs):
        return key

    def get_all_texts(lang="zh"):
        return {}

app = Flask(__name__)

# In-memory state
scan_results: list[ScanItem] = []
scan_in_progress = False
scan_lock = threading.Lock()
scan_engine = ScannerEngine()

# Sandbox mode
sandbox_enabled = False
sandbox_path: str = ""  # empty = not in sandbox mode


# ---------------------------------------------------------------------------
# Before-request hook: language detection
# ---------------------------------------------------------------------------

@app.before_request
def set_language():
    """Detect language from query param ?lang=en|zh, default zh."""
    g.lang = request.args.get("lang", "zh")
    if g.lang not in ("zh", "en"):
        g.lang = "zh"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_size(size: float) -> str:
    """Convert bytes to a human-readable string (B/KB/MB/GB/TB)."""
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024.0:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{value:.2f} PB"


_RISK_LABELS: dict[RiskLevel, dict[str, str]] = {
    RiskLevel.SAFE: {"zh": "安全", "en": "Safe"},
    RiskLevel.CAUTION: {"zh": "谨慎", "en": "Caution"},
    RiskLevel.DANGER: {"zh": "危险", "en": "Danger"},
}


def _risk_label(risk: RiskLevel, lang: str) -> str:
    """Return the localised display label for a risk level."""
    return _RISK_LABELS.get(risk, {}).get(lang, risk.value)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Render the main page."""
    return render_template("index.html", lang=getattr(g, "lang", "zh"))


@app.route("/api/translations")
def api_translations():
    """Return the full language pack for the current language."""
    return jsonify(get_all_texts(getattr(g, "lang", "zh")))


@app.route("/api/disk")
def api_disk():
    """Return C: drive (or sandbox indicator) disk usage."""
    global sandbox_enabled
    usage = psutil.disk_usage("C:/")
    return jsonify({
        "total": usage.total,
        "used": usage.used,
        "free": usage.free,
        "percent": usage.percent,
        "sandbox": sandbox_enabled,
    })


@app.route("/api/scan/start", methods=["POST"])
def api_scan_start():
    """Start a scan in a background thread and return immediately."""
    global scan_in_progress
    data = request.get_json(force=True)
    categories = data.get("categories")

    if not categories or not isinstance(categories, list):
        return jsonify({"error": "categories must be a non-empty list"}), 400

    with scan_lock:
        if scan_in_progress:
            return jsonify({"error": "扫描正在进行中"}), 409
        scan_in_progress = True

    def _run_scan():
        global scan_results, scan_in_progress
        try:
            scan_results = list(scan_engine.scan(categories))
        finally:
            with scan_lock:
                scan_in_progress = False

    t = threading.Thread(target=_run_scan, daemon=True)
    t.start()
    return jsonify({"status": "started"})


@app.route("/api/scan/results")
def api_scan_results():
    """Return all scan results as a JSON list."""
    global scan_in_progress
    lang = getattr(g, "lang", "zh")
    with scan_lock:
        in_progress = scan_in_progress
    results = []
    for item in scan_results:
        results.append({
            "id": item.id,
            "category": item.category,
            "path": item.path,
            "size": item.size,
            "size_fmt": _format_size(item.size),
            "risk": item.risk.value,
            "risk_label": _risk_label(item.risk, lang),
            "risk_desc": item.risk_desc,
            "item_count": item.item_count,
        })
    return jsonify({"items": results, "total": len(results), "scanning": in_progress})


@app.route("/api/clean/start", methods=["POST"])
def api_clean_start():
    """Start cleaning selected items and stream progress via SSE.
    In sandbox mode, simulate progress without deleting files."""
    global sandbox_enabled
    data = request.get_json(force=True)
    ids = data.get("ids")

    if not ids or not isinstance(ids, list):
        return jsonify({"error": "ids must be a non-empty list"}), 400

    selected = [item for item in scan_results if item.id in ids]
    if not selected:
        return jsonify({"error": "no matching items found for the given ids"}), 400

    def generate():
        if sandbox_enabled:
            total = len(selected)
            for i, item in enumerate(selected, 1):
                time.sleep(0.3)
                yield f"data: {json.dumps({'type': 'clean_progress', 'completed': i, 'total': total, 'path': item.path, 'success': True, 'freed_so_far': item.size * i})}\n\n"
            yield f"data: {json.dumps({'type': 'clean_complete', 'total_items': total, 'completed': total, 'failed_count': 0, 'total_freed': sum(it.size for it in selected)})}\n\n"
        else:
            executor = CleanExecutor()
            for event in executor.clean_items(selected):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/processes")
def api_processes():
    """Return the top 30 processes by memory usage."""
    procs = []
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            mem_mb = p.info["memory_info"].rss / (1024.0 * 1024.0)
            procs.append({
                "pid": p.info["pid"],
                "name": p.info["name"],
                "memory_mb": round(mem_mb, 2),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError):
            continue

    procs.sort(key=lambda x: x["memory_mb"], reverse=True)
    return jsonify(procs[:30])


# ---------------------------------------------------------------------------
# Sandbox mode
# ---------------------------------------------------------------------------

@app.route("/api/sandbox/start", methods=["POST"])
def api_sandbox_start():
    """Activate sandbox mode: real scanning, simulated cleanup."""
    global sandbox_enabled, sandbox_path, scan_results
    if sandbox_enabled:
        return jsonify({"error": "沙盒已激活，请先退出"}), 409

    sandbox_enabled = True
    sandbox_path = "(沙盒模式)"
    scan_results = []
    return jsonify({
        "status": "started",
        "message": "沙盒模式已激活 — 真实扫描，模拟清理，不会删除任何文件",
    })


@app.route("/api/sandbox/stop", methods=["POST"])
def api_sandbox_stop():
    """Deactivate sandbox mode."""
    global sandbox_enabled, sandbox_path, scan_results
    if not sandbox_enabled:
        return jsonify({"error": "沙盒未激活"}), 400

    sandbox_enabled = False
    sandbox_path = ""
    scan_results = []
    return jsonify({
        "status": "stopped",
        "message": "沙盒模式已退出",
    })


@app.route("/api/sandbox/status")
def api_sandbox_status():
    """Return whether sandbox mode is active."""
    return jsonify({
        "enabled": sandbox_enabled,
        "path": sandbox_path if sandbox_enabled else "",
    })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("[SysClean] Starting...")
    print("   Visit http://localhost:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)
