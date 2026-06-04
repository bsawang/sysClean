"""
SysClean - Flask Application

Provides web API for scanning and cleaning Windows system files.
Routes handle disk info, scan operations, cleanup execution via SSE,
and process listing with i18n support.
"""

import json
import os
import threading

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


def _scan_sandbox(sbox_path: str, categories: list[str]) -> list[ScanItem]:
    """Scan the sandbox directory and return ScanItems based on categories."""
    from scanner import classify_risk
    items = []
    counter = 0

    for root, dirs, files in os.walk(sbox_path):
        # Determine category from the directory name
        rel = os.path.relpath(root, sbox_path).lower()
        if not files:
            continue

        if "temp" in categories and ("temp" in rel or "cache" in rel):
            cat = "temp"
        elif "cache" in categories and ("dxcache" in rel or "glcache" in rel):
            cat = "cache"
        elif "installer" in categories and ("updater" in rel or "shell_cache" in rel):
            cat = "installer"
        elif "browser" in categories and "chrome" in rel:
            cat = "browser"
        else:
            cat = "temp" if categories else "temp"

        if cat not in categories:
            continue

        total = sum(
            os.path.getsize(os.path.join(root, f))
            for f in files if os.path.isfile(os.path.join(root, f))
        )
        if total == 0:
            continue

        risk = classify_risk(root)
        risk_label = {
            "safe": "安全的模拟文件，可放心删除",
            "caution": "注意：模拟的应用数据文件",
            "danger": "高风险：模拟的系统文件",
        }.get(risk.value, "模拟文件")

        counter += 1
        items.append(ScanItem(
            id=f"sbox_{counter}",
            category=cat,
            path=root,
            size=total,
            risk=risk,
            risk_desc=f"[沙盒] {risk_label}",
            item_count=len(files),
        ))

    return items


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
    """Return C: drive or sandbox disk usage information."""
    global sandbox_enabled, sandbox_path
    if sandbox_enabled and sandbox_path:
        total = 0
        for root, dirs, files in os.walk(sandbox_path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        return jsonify({
            "total": total,
            "used": total,
            "free": 0,
            "percent": 100.0,
            "sandbox": True,
            "sandbox_path": sandbox_path,
        })
    usage = psutil.disk_usage("C:/")
    return jsonify({
        "total": usage.total,
        "used": usage.used,
        "free": usage.free,
        "percent": usage.percent,
        "sandbox": False,
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
            if sandbox_enabled and sandbox_path:
                # Sandbox mode: scan the sandbox directory
                scan_results = _scan_sandbox(sandbox_path, categories)
            else:
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
    """Start cleaning selected items and stream progress via SSE."""
    data = request.get_json(force=True)
    ids = data.get("ids")

    if not ids or not isinstance(ids, list):
        return jsonify({"error": "ids must be a non-empty list"}), 400

    selected = [item for item in scan_results if item.id in ids]
    if not selected:
        return jsonify({"error": "no matching items found for the given ids"}), 400

    executor = CleanExecutor()

    def generate():
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

import tempfile, random, string

SANDBOX_SIZE = 75 * 1024 * 1024  # 75 MB of dummy data


def _create_sandbox_files(path: str):
    """Populate a sandbox directory with realistic junk files."""
    dirs = {
        "Temp": 5,
        "NVIDIA/DXCache": 1,
        "NVIDIA/GLCache": 1,
        "Google/Chrome/User Data/Default/Cache": 3,
        "updater": 2,
        "npm-cache": 4,
        "pip/cache": 3,
        "app_shell_cache": 1,
    }
    file_id = 0
    for rel_dir, count in dirs.items():
        full_dir = os.path.join(path, rel_dir)
        os.makedirs(full_dir, exist_ok=True)
        for _ in range(count):
            size = random.randint(1, 15) * 1024 * 1024
            ext = random.choice([".tmp", ".log", ".cache", ".exe", ".bin"])
            fp = os.path.join(full_dir, f"sandbox_{file_id}{ext}")
            with open(fp, "wb") as f:
                f.write(os.urandom(size))
            file_id += 1

    # A "system" directory that should NOT be touched
    sys_dir = os.path.join(path, "Windows", "System32")
    os.makedirs(sys_dir, exist_ok=True)
    with open(os.path.join(sys_dir, "kernel32.dll"), "w") as f:
        f.write("SIMULATED SYSTEM FILE - DO NOT DELETE")

    # Create a marker file
    with open(os.path.join(path, "README.txt"), "w") as f:
        f.write("这是 SysClean 沙盒环境，所有文件均为模拟数据，可安全删除。\n")
        f.write("This is a SysClean sandbox. All files are simulated data.\n")


@app.route("/api/sandbox/start", methods=["POST"])
def api_sandbox_start():
    """Create a sandbox environment with dummy files."""
    global sandbox_enabled, sandbox_path, scan_results
    if sandbox_enabled:
        return jsonify({"error": "沙盒已激活，请先退出"}), 409

    path = tempfile.mkdtemp(prefix="sysclean_sandbox_")
    try:
        _create_sandbox_files(path)
        sandbox_enabled = True
        sandbox_path = path
        scan_results = []  # clear old results
        return jsonify({
            "status": "started",
            "path": path,
            "message": "沙盒模式已激活，所有操作均在隔离环境中进行",
        })
    except Exception as e:
        import shutil
        shutil.rmtree(path, ignore_errors=True)
        return jsonify({"error": f"沙盒创建失败: {e}"}), 500


@app.route("/api/sandbox/stop", methods=["POST"])
def api_sandbox_stop():
    """Remove the sandbox and return to normal mode."""
    global sandbox_enabled, sandbox_path, scan_results
    if not sandbox_enabled:
        return jsonify({"error": "沙盒未激活"}), 400

    path = sandbox_path
    sandbox_enabled = False
    sandbox_path = ""
    scan_results = []

    import shutil
    shutil.rmtree(path, ignore_errors=True)
    return jsonify({
        "status": "stopped",
        "message": "沙盒已清理，已返回正常模式",
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
