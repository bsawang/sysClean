"""
SysClean - Flask Application

Provides web API for scanning and cleaning Windows system files.
Routes handle disk info, scan operations, cleanup execution via SSE,
and process listing with i18n support.
"""

import json
import os
import subprocess
import threading
import winreg
from pathlib import Path

import ctypes
import psutil
from typing import Optional
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

# ---------------------------------------------------------------------------
# Global operation state machine — prevents concurrent operations
# ---------------------------------------------------------------------------
_operation_lock = threading.Lock()
_operation_state: Optional[str] = None  # None | "scanning" | "cleaning" | "uninstalling" | "emptying_recycle" | "rebuilding_index"


def acquire_operation(op_name: str) -> bool:
    """Attempt to acquire the global operation lock.

    Returns True if acquired, False if another operation is in progress.
    """
    global _operation_state
    with _operation_lock:
        if _operation_state is not None:
            return False
        _operation_state = op_name
        return True


def release_operation():
    """Release the global operation lock."""
    global _operation_state
    with _operation_lock:
        _operation_state = None


def get_operation_state() -> Optional[str]:
    """Return current operation state (thread-safe)."""
    global _operation_state
    with _operation_lock:
        return _operation_state


def is_admin() -> bool:
    """Check if the current process is running with administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


app = Flask(__name__)

# In-memory state
scan_results: list[ScanItem] = []
scan_in_progress = False
scan_lock = threading.Lock()
scan_engine = ScannerEngine()

# Sandbox mode
sandbox_enabled = False


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


@app.route("/api/operation/status")
def api_operation_status():
    """Return whether an operation is in progress and its type."""
    state = get_operation_state()
    return jsonify({
        "busy": state is not None,
        "operation": state,
        "admin": is_admin(),
    })


@app.route("/api/scan/start", methods=["POST"])
def api_scan_start():
    """Start a scan in a background thread, guarded by global operation lock."""
    global scan_in_progress
    data = request.get_json(force=True)
    categories = data.get("categories")

    if not categories or not isinstance(categories, list):
        return jsonify({"error": "categories must be a non-empty list"}), 400

    if not acquire_operation("scanning"):
        return jsonify({"error": "另一个操作正在进行中"}), 409

    with scan_lock:
        if scan_in_progress:
            release_operation()
            return jsonify({"error": "扫描正在进行中"}), 409
        scan_in_progress = True

    def _run_scan():
        global scan_results, scan_in_progress
        try:
            scan_results = list(scan_engine.scan(categories))
        finally:
            with scan_lock:
                scan_in_progress = False
            release_operation()

    t = threading.Thread(target=_run_scan, daemon=True)
    try:
        t.start()
    except Exception:
        release_operation()
        with scan_lock:
            scan_in_progress = False
        raise
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
    if not acquire_operation("cleaning"):
        return jsonify({"error": "另一个操作正在进行中"}), 409

    data = request.get_json(force=True)
    ids = data.get("ids")

    if not ids or not isinstance(ids, list):
        release_operation()
        return jsonify({"error": "ids must be a non-empty list"}), 400

    selected = [item for item in scan_results if item.id in ids]
    if not selected:
        release_operation()
        return jsonify({"error": "no matching items found for the given ids"}), 400

    def generate():
        executor = CleanExecutor()
        try:
            for event in executor.clean_items(selected):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            release_operation()

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
    global sandbox_enabled, scan_results
    if sandbox_enabled:
        return jsonify({"error": "沙盒已激活，请先退出"}), 409

    sandbox_enabled = True
    return jsonify({
        "status": "started",
        "message": "沙盒模式已激活 — 真实扫描，模拟清理，不会删除任何文件",
    })


@app.route("/api/sandbox/stop", methods=["POST"])
def api_sandbox_stop():
    """Deactivate sandbox mode."""
    global sandbox_enabled, scan_results
    if not sandbox_enabled:
        return jsonify({"error": "沙盒未激活"}), 400

    sandbox_enabled = False
    return jsonify({
        "status": "stopped",
        "message": "沙盒模式已退出",
    })


@app.route("/api/sandbox/status")
def api_sandbox_status():
    """Return whether sandbox mode is active."""
    return jsonify({
        "enabled": sandbox_enabled,
    })


# ---------------------------------------------------------------------------
# Recycle Bin API (Windows Shell)
# ---------------------------------------------------------------------------

# SHQueryRecycleBin flags
SHERB_NOCONFIRMATION = 0x00000001
SHERB_NOPROGRESSUI = 0x00000002
SHERB_NOSOUND = 0x00000004


class SHQUERYRBINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("i64Size", ctypes.c_longlong),
        ("i64NumItems", ctypes.c_longlong),
    ]


def _query_recycle_bin():
    """Query the Recycle Bin for total size and item count.

    Returns:
        (size_bytes, item_count) tuple, or (0, 0) on failure.
    """
    try:
        rbinfo = SHQUERYRBINFO()
        rbinfo.cbSize = ctypes.sizeof(SHQUERYRBINFO)
        result = ctypes.windll.shell32.SHQueryRecycleBinW(
            None, ctypes.byref(rbinfo)
        )
        if result == 0:
            return rbinfo.i64Size, rbinfo.i64NumItems
    except Exception:
        pass
    return 0, 0


@app.route("/api/recycle/status")
def api_recycle_status():
    """Return Recycle Bin size and item count."""
    size, count = _query_recycle_bin()
    return jsonify({
        "size": size,
        "size_fmt": _format_size(size),
        "count": count,
    })


@app.route("/api/recycle/empty", methods=["POST"])
def api_recycle_empty():
    """Empty the Recycle Bin. Guarded by global operation lock."""
    if not acquire_operation("emptying_recycle"):
        return jsonify({"error": "另一个操作正在进行中"}), 409
    try:
        # SHEmptyRecycleBinW with flags: no confirm, no progress, no sound
        result = ctypes.windll.shell32.SHEmptyRecycleBinW(
            None, None,
            SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND,
        )
        if result == 0:
            return jsonify({"status": "emptied"})
        else:
            return jsonify({"error": f"清空回收站失败 (code {result})"}), 500
    finally:
        release_operation()


# ---------------------------------------------------------------------------
# Windows Search Index API
# ---------------------------------------------------------------------------

SEARCH_INDEX_PATH = Path(
    "C:\\ProgramData\\Microsoft\\Search\\Data\\Applications\\Windows\\Windows.edb"
)
WSEARCH_SERVICE_NAME = "WSearch"


def _get_real_search_index_path() -> str:
    """Resolve junctions/symlinks to get the real index file path."""
    try:
        return os.path.realpath(str(SEARCH_INDEX_PATH))
    except Exception:
        return str(SEARCH_INDEX_PATH)


def _get_search_index_size() -> int:
    """Return size of Windows.edb in bytes, or 0 if not accessible."""
    try:
        return SEARCH_INDEX_PATH.stat().st_size if SEARCH_INDEX_PATH.exists() else 0
    except OSError:
        return 0


def _is_search_service_running() -> Optional[bool]:
    """Check if WSearch service is running.

    Returns:
        True if running, False if stopped, None if status unknown.
    """
    try:
        import subprocess
        r = subprocess.run(
            ["sc", "query", WSEARCH_SERVICE_NAME],
            capture_output=True, text=True, timeout=10,
        )
        return "RUNNING" in r.stdout
    except Exception:
        return None


@app.route("/api/search/status")
def api_search_status():
    """Return Search Index status: size, service state, rebuilding flag."""
    size = _get_search_index_size()
    running = _is_search_service_running()
    state = get_operation_state()
    real_path = _get_real_search_index_path()
    return jsonify({
        "size": size,
        "size_fmt": _format_size(size),
        "service_running": running,
        "rebuilding": state == "rebuilding_index",
        "real_path": real_path,
    })


@app.route("/api/search/rebuild", methods=["POST"])
def api_search_rebuild():
    """Rebuild Windows Search index: stop service → delete db → start service.

    Guarded by global operation lock. Requires admin privileges.
    """
    if not is_admin():
        return jsonify({"error": "需要管理员权限才能重建搜索索引"}), 403

    if not acquire_operation("rebuilding_index"):
        return jsonify({"error": "另一个操作正在进行中"}), 409

    def _rebuild():
        import subprocess
        import time
        try:
            # Step 1: Stop WSearch service
            subprocess.run(
                ["net", "stop", WSEARCH_SERVICE_NAME, "/y"],
                capture_output=True, text=True, timeout=30,
            )
            time.sleep(1)

            # Step 2: Delete the index database
            if SEARCH_INDEX_PATH.exists():
                try:
                    SEARCH_INDEX_PATH.unlink()
                except OSError:
                    pass

            # Step 3: Delete log files in the same directory
            index_dir = SEARCH_INDEX_PATH.parent
            if index_dir.exists():
                for f in index_dir.iterdir():
                    if f.name.endswith(".log") or f.name.endswith(".jrs"):
                        try:
                            f.unlink()
                        except OSError:
                            pass

            # Step 4: Restart service
            subprocess.run(
                ["net", "start", WSEARCH_SERVICE_NAME],
                capture_output=True, text=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            pass
        except Exception as exc:
            print(f"Search index rebuild failed: {exc}")
        finally:
            release_operation()

    t = threading.Thread(target=_rebuild, daemon=True)
    t.start()
    return jsonify({"status": "rebuilding"})


@app.route("/api/search/toggle", methods=["POST"])
def api_search_toggle():
    """Toggle WSearch service on/off without deleting index.

    Requires admin privileges. Guarded by global operation lock.
    """
    if not is_admin():
        return jsonify({"error": "需要管理员权限才能控制服务"}), 403

    data = request.get_json(force=True)
    enable = data.get("enable", False)

    if not acquire_operation("rebuilding_index"):
        return jsonify({"error": "另一个操作正在进行中"}), 409

    try:
        import subprocess
        action = "start" if enable else "stop"
        args = ["net", action, WSEARCH_SERVICE_NAME]
        if action == "stop":
            args.append("/y")
        r = subprocess.run(args, capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return jsonify({"status": "ok", "running": enable})
        else:
            return jsonify({"error": f"服务{action}失败: {r.stderr.strip()}"}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "服务控制超时"}), 500
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        release_operation()


# ---------------------------------------------------------------------------
# Software Uninstall API
# ---------------------------------------------------------------------------


def _read_registered_programs():
    """Read installed programs from Windows registry.

    Returns:
        List of dicts with keys: name, version, publisher, install_date,
        estimated_size, uninstall_string, source.
    """
    programs = []
    seen = set()

    registry_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]

    for hkey, subkey in registry_paths:
        try:
            key = winreg.OpenKey(hkey, subkey, 0, winreg.KEY_READ)
        except OSError:
            continue
        try:
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    sub_name = winreg.EnumKey(key, i)
                except OSError:
                    break
                try:
                    sub_key = winreg.OpenKey(key, sub_name)
                except OSError:
                    continue
                with sub_key:
                    try:
                        name, _ = winreg.QueryValueEx(sub_key, "DisplayName")
                    except OSError:
                        continue

                    if name in seen:
                        continue
                    seen.add(name)

                    def _read_str(k, field):
                        try:
                            v, _ = winreg.QueryValueEx(k, field)
                            return str(v)
                        except (OSError, ValueError):
                            return ""

                    def _read_int(k, field):
                        try:
                            v, _ = winreg.QueryValueEx(k, field)
                            return int(v)
                        except (OSError, ValueError):
                            return 0

                    ustr = _read_str(sub_key, "UninstallString")

                    # Try InstallLocation, then fallback to DisplayIcon directory
                    install_path = _read_str(sub_key, "InstallLocation")
                    if not install_path or not os.path.isdir(install_path):
                        icon = _read_str(sub_key, "DisplayIcon")
                        if icon and os.path.isfile(icon):
                            install_path = os.path.dirname(icon)
                        elif icon and os.path.isdir(icon):
                            install_path = icon

                    last_used = ""
                    est_size = _read_int(sub_key, "EstimatedSize") * 1024

                    if install_path and os.path.isdir(install_path):
                        # Last used time from directory
                        try:
                            from datetime import datetime
                            mtime = os.path.getmtime(install_path)
                            last_used = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
                        except Exception:
                            pass

                    # Detect install type
                    try:
                        is_msi = _read_int(sub_key, "WindowsInstaller") == 1
                    except Exception:
                        is_msi = "msiexec" in ustr.lower()
                    install_type = "MSI" if is_msi else "Win32"

                    programs.append({
                        "name": name,
                        "version": _read_str(sub_key, "DisplayVersion"),
                        "publisher": _read_str(sub_key, "Publisher"),
                        "install_date": _read_str(sub_key, "InstallDate"),
                        "install_location": install_path,
                        "last_used": last_used,
                        "install_type": install_type,
                        "estimated_size": est_size,
                        "uninstall_string": ustr,
                        "display_icon": _read_str(sub_key, "DisplayIcon"),
                        "source": "registry",
                    })
        finally:
            winreg.CloseKey(key)

    return programs


@app.route("/api/uninstall/list")
def api_uninstall_list():
    """Return a list of installed programs."""
    programs = _read_registered_programs()
    programs.sort(key=lambda p: p["name"].lower())

    for p in programs:
        p["size_fmt"] = _format_size(p["estimated_size"]) if p["estimated_size"] > 0 else ""

    return jsonify({
        "programs": programs,
        "total": len(programs),
        "admin": is_admin(),
    })


@app.route("/api/uninstall/start", methods=["POST"])
def api_uninstall_start():
    """Start serial uninstall of selected programs via SSE."""
    data = request.get_json(force=True)
    names = data.get("names")

    if not names or not isinstance(names, list):
        return jsonify({"error": "names must be a non-empty list"}), 400

    if not acquire_operation("uninstalling"):
        return jsonify({"error": "另一个操作正在进行中"}), 409

    def generate():
        all_progs = _read_registered_programs()
        lookup = {p["name"]: p["uninstall_string"] for p in all_progs}
        try:
            total = len(names)
            for i, name in enumerate(names):
                yield {
                    "type": "uninstall_progress",
                    "current": name,
                    "completed": i,
                    "total": total,
                }

                ustr = lookup.get(name, "")
                if not ustr:
                    yield {
                        "type": "uninstall_result",
                        "name": name,
                        "success": False,
                        "reason": "No uninstall string found",
                    }
                    continue

                try:
                    proc = subprocess.run(
                        ustr,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                    success = proc.returncode == 0
                    yield {
                        "type": "uninstall_result",
                        "name": name,
                        "success": success,
                        "reason": "" if success else f"Exit code: {proc.returncode}",
                    }
                except subprocess.TimeoutExpired:
                    yield {
                        "type": "uninstall_result",
                        "name": name,
                        "success": False,
                        "reason": "Timeout (120s)",
                    }
                except Exception as exc:
                    yield {
                        "type": "uninstall_result",
                        "name": name,
                        "success": False,
                        "reason": str(exc),
                    }

            yield {
                "type": "uninstall_complete",
                "total": total,
                "completed": total,
            }
        finally:
            release_operation()

    def generate_sse():
        for event in generate():
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return Response(generate_sse(), mimetype="text/event-stream")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not is_admin():
        import sys
        import ctypes.wintypes
        print("[SysClean] Not running as admin, relaunching with admin privileges...")
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit(0)

    print("[SysClean] Starting...")
    print("   Visit http://localhost:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)
