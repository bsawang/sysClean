# SysClean Scan Content Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend SysClean from 4 scan categories to 11 (7 new + 4 existing) and add 3 independent operation modules (RecycleBin, Search Index rebuild, Software Uninstall).

**Architecture:** Add 6 new scanner methods + 1 expanded browser scanner to `ScannerEngine` in `scanner.py`. Add global operation state machine to `app.py` for cross-operation concurrency control. Add 3 independent operation modules as separate API endpoints + UI views. Keep `cleaner.py` unchanged.

**Tech Stack:** Python 3.11+, Flask, Windows Shell API (ctypes), Windows Service Controller (pywin32/ctypes), SSE for streaming progress.

**Spec:** `docs/superpowers/specs/2026-06-04-scan-content-expansion-design.md`

---

## File Structure

| File | Status | Responsibility |
|------|--------|---------------|
| `scanner.py` | **Modify** | Add 6 new scanner methods + expanded browser scanner + risk patterns |
| `cleaner.py` | Unchanged | No changes needed |
| `app.py` | **Modify** | Global state machine, admin check, 3 new API modules, extended scan dispatch |
| `templates/index.html` | **Modify** | New sidebar items, 3 new views, isBusy polling, completion report hints |
| `i18n/zh.json` | **Modify** | All new Chinese strings |
| `i18n/en.json` | **Modify** | All new English strings |
| `static/style.css` | **Modify** | Styles for new UI elements (minimal) |

---

## Phase 1: Global Operation State Machine + Admin Privilege

### Task 1.1: Add operation state machine to app.py

**Files:**
- Modify: `app.py` (add after existing imports, before `app = Flask(__name__)`)

- [ ] **Step 1: Add global state variables and functions**

Add after the existing `import psutil` line:

```python
import ctypes
import threading
from typing import Optional

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
    """Return current operation state without acquiring the lock."""
    global _operation_state
    with _operation_lock:
        return _operation_state


def is_admin() -> bool:
    """Check if the current process is running with administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False
```

- [ ] **Step 2: Add `/api/operation/status` endpoint**

Add after the existing `/api/disk` route:

```python
@app.route("/api/operation/status")
def api_operation_status():
    """Return whether an operation is in progress and its type."""
    state = get_operation_state()
    return jsonify({
        "busy": state is not None,
        "operation": state,
        "admin": is_admin(),
    })
```

- [ ] **Step 3: Update existing `/api/scan/start` to use global lock**

Replace the existing `api_scan_start` function:

```python
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
    t.start()
    return jsonify({"status": "started"})
```

- [ ] **Step 4: Verify no syntax errors**

Run: `python -c "import app"`
Expected: no error output

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: add global operation state machine and admin check"
```

---

### Task 1.2: Update frontend with isBusy polling

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: Add isBusy polling JavaScript**

In the `<script>` section, after the existing `// Formatting helpers` comment block, add:

```javascript
// ====================================================================
// Global operation state (isBusy)
// ====================================================================
let isBusy = false;
let busyPollInterval = null;
const BUSY_MSG = '当前有操作进行中，请等待完成';

function startBusyPolling() {
    if (busyPollInterval) return;
    busyPollInterval = setInterval(checkBusy, 2000);
}

function stopBusyPolling() {
    if (busyPollInterval) {
        clearInterval(busyPollInterval);
        busyPollInterval = null;
    }
}

function checkBusy() {
    fetch('/api/operation/status')
        .then(function(r) { return r.json(); })
        .then(function(d) {
            isBusy = d.busy;
            var admin = d.admin;
            updateButtons();
            updateAdminHints(admin);
            if (!isBusy) stopBusyPolling();
        });
}

function updateButtons() {
    document.querySelectorAll('.btn-operation').forEach(function(btn) {
        btn.disabled = isBusy;
    });
}

function updateAdminHints(admin) {
    document.querySelectorAll('.admin-hint').forEach(function(el) {
        el.style.display = admin ? 'none' : 'inline';
    });
}
```

- [ ] **Step 2: Add admin check on page load**

In the existing `DOMContentLoaded` event listener, add:
```javascript
checkBusy();
```

Add it after the existing `checkSandbox();` call.

- [ ] **Step 3: Add `.btn-operation` class to existing buttons**

In the sidebar, add `btn-operation` class to the "Start Scan" button:
```html
<button class="btn btn-primary btn-block btn-operation" ...
```

In the results view action buttons, add `btn-operation` to "Clean Selected":
```html
<button class="btn btn-danger btn-sm btn-operation" ...
```

- [ ] **Step 4: Verify the template loads**

Run: `python -c "import app; app.test_client().get('/')"`
Expected: 200 response

- [ ] **Step 5: Commit**

```bash
git add templates/index.html
git commit -m "feat: add isBusy frontend polling and admin check"
```

---

### Task 1.3: Add i18n strings for busy/admin

**Files:**
- Modify: `i18n/zh.json`
- Modify: `i18n/en.json`

- [ ] **Step 1: Add to zh.json**

Insert before the closing `}`:
```json
  "operation.busy": "当前有操作进行中，请等待完成",
  "admin.required": "需要管理员权限",
  "admin.limited": "部分结果受权限限制"
}
```

- [ ] **Step 2: Add to en.json**

Insert before the closing `}`:
```json
  "operation.busy": "Another operation is in progress, please wait",
  "admin.required": "Admin privileges required",
  "admin.limited": "Limited by user permissions"
}
```

- [ ] **Step 3: Commit**

```bash
git add i18n/zh.json i18n/en.json
git commit -m "feat: add i18n strings for operation busy and admin hints"
```

---

## Phase 2: Scanner Categories + Risk Patterns

### Task 2.1: Add new scanner methods to scanner.py

**Files:**
- Modify: `scanner.py`

- [ ] **Step 1: Add `scan_thumbcache` method**

Add after the existing `scan_browser` method:

```python
def scan_thumbcache(self):
    """Scan Windows thumbnail cache (thumbcache_*.db, iconcache_*.db)."""
    explorer = (
        self.user_home
        / "AppData"
        / "Local"
        / "Microsoft"
        / "Windows"
        / "Explorer"
    )
    if not explorer.exists():
        return
    size, count = self._walk_size(explorer)
    if size > 0 or count > 0:
        yield ScanItem(
            id=self._next_id("THUMB"),
            category="thumbcache",
            path=str(explorer),
            size=size,
            risk=classify_risk(str(explorer), size),
            risk_desc="Windows thumbnail and icon cache files",
            item_count=count,
        )
```

- [ ] **Step 2: Add `scan_prefetch` method**

```python
def scan_prefetch(self):
    """Scan Windows Prefetch files (C:\\Windows\\Prefetch)."""
    prefetch = Path("C:\\Windows\\Prefetch")
    if not prefetch.exists():
        return
    size, count = self._walk_size(prefetch)
    if size > 0 or count > 0:
        yield ScanItem(
            id=self._next_id("PREF"),
            category="prefetch",
            path=str(prefetch),
            size=size,
            risk=classify_risk(str(prefetch), size),
            risk_desc="Application launch prefetch files",
            item_count=count,
        )
```

- [ ] **Step 3: Add `scan_sysdumps` method**

```python
def scan_sysdumps(self):
    """Scan crash dumps, Windows Error Reporting, and logs.

    Note: some paths require admin privileges and may be silently
    skipped for non-admin users.
    """
    local = self.user_home / "AppData" / "Local"
    candidates = [
        (local / "CrashDumps", "Application crash dumps", RiskLevel.SAFE),
        (local / "Microsoft" / "Windows" / "WER", "User Windows Error Reporting", RiskLevel.SAFE),
        (Path("C:\\ProgramData") / "Microsoft" / "Windows" / "WER", "System Windows Error Reporting", RiskLevel.SAFE),
        (Path("C:\\Windows\\Minidump"), "System minidumps", RiskLevel.CAUTION),
        (Path("C:\\Windows\\Logs"), "Windows logs", RiskLevel.SAFE),
        (Path("C:\\Windows\\System32\\LogFiles"), "System log files", RiskLevel.SAFE),
    ]
    for path_, desc, risk in candidates:
        if not path_.exists():
            continue
        size, count = self._walk_size(path_)
        if size > 0 or count > 0:
            yield ScanItem(
                id=self._next_id("DUMP"),
                category="sysdumps",
                path=str(path_),
                size=size,
                risk=risk,
                risk_desc=desc,
                item_count=count,
            )

    # memory.dmp — separate check since it's a single file
    memory_dmp = Path("C:\\Windows\\memory.dmp")
    if memory_dmp.exists():
        try:
            msize = memory_dmp.stat().st_size
        except OSError:
            msize = 0
        if msize > 0:
            yield ScanItem(
                id=self._next_id("DUMP"),
                category="sysdumps",
                path=str(memory_dmp),
                size=msize,
                risk=RiskLevel.CAUTION,
                risk_desc="Full system memory dump",
                item_count=1,
            )
```

- [ ] **Step 4: Extend `scan_browser` with Edge and Firefox**

Replace the existing `scan_browser` method entirely:

```python
def scan_browser(self):
    """Scan browser cache directories: Chrome, Edge, Firefox."""
    local = self.user_home / "AppData" / "Local"
    appdata = self.user_home / "AppData" / "Roaming"

    chrome_cache = (
        local / "Google" / "Chrome" / "User Data" / "Default" / "Cache"
    )
    chrome_code_cache = (
        local / "Google" / "Chrome" / "User Data" / "Default" / "Code Cache"
    )
    edge_cache = (
        local / "Microsoft" / "Edge" / "User Data" / "Default" / "Cache"
    )
    edge_code_cache = (
        local / "Microsoft" / "Edge" / "User Data" / "Default" / "Code Cache"
    )

    browser_paths = [
        (chrome_cache, "Chrome browser cache"),
        (chrome_code_cache, "Chrome Code Cache"),
        (edge_cache, "Edge browser cache"),
        (edge_code_cache, "Edge Code Cache"),
    ]

    # Chrome and Edge (well-known paths)
    for path_, desc in browser_paths:
        if not path_.exists():
            continue
        size, count = self._walk_size(path_)
        if size > 0 or count > 0:
            yield ScanItem(
                id=self._next_id("BRWS"),
                category="browser",
                path=str(path_),
                size=size,
                risk=classify_risk(str(path_), size),
                risk_desc=desc,
                item_count=count,
            )

    # Firefox — walk all profiles
    firefox_root = local / "Mozilla" / "Firefox" / "Profiles"
    if firefox_root.exists():
        for profile_dir in firefox_root.iterdir():
            if not profile_dir.is_dir():
                continue
            cache2 = profile_dir / "cache2"
            if cache2.exists():
                sz, cnt = self._walk_size(cache2)
                if sz > 0 or cnt > 0:
                    yield ScanItem(
                        id=self._next_id("BRWS"),
                        category="browser",
                        path=str(cache2),
                        size=sz,
                        risk=classify_risk(str(cache2), sz),
                        risk_desc=f"Firefox cache ({profile_dir.name})",
                        item_count=cnt,
                    )
            thumbnails = profile_dir / "thumbnails"
            if thumbnails.exists():
                sz, cnt = self._walk_size(thumbnails)
                if sz > 0 or cnt > 0:
                    yield ScanItem(
                        id=self._next_id("BRWS"),
                        category="browser",
                        path=str(thumbnails),
                        size=sz,
                        risk=classify_risk(str(thumbnails), sz),
                        risk_desc=f"Firefox thumbnails ({profile_dir.name})",
                        item_count=cnt,
                    )
```

- [ ] **Step 5: Add `scan_package` method**

```python
def scan_package(self):
    """Scan package manager caches (npm, yarn, pnpm, pip, NuGet, Go, Cargo)."""
    local = self.user_home / "AppData" / "Local"
    roaming = self.user_home / "AppData" / "Roaming"
    user = self.user_home

    candidates = [
        (roaming / "npm-cache", "npm cache", RiskLevel.SAFE),
        (user / ".yarn" / "cache", "Yarn cache", RiskLevel.SAFE),
        (local / "pnpm" / "store", "pnpm store", RiskLevel.SAFE),
        (local / "pip" / "cache", "pip cache", RiskLevel.SAFE),
        (user / ".nuget" / "packages", "NuGet package cache", RiskLevel.CAUTION),
        (user / "go" / "pkg" / "mod", "Go module cache", RiskLevel.SAFE),
        (user / ".cargo" / "registry", "Cargo registry cache", RiskLevel.SAFE),
    ]
    for path_, desc, risk in candidates:
        if not path_.exists():
            continue
        size, count = self._walk_size(path_)
        if size > 0 or count > 0:
            yield ScanItem(
                id=self._next_id("PKG"),
                category="package",
                path=str(path_),
                size=size,
                risk=risk,
                risk_desc=desc,
                item_count=count,
            )
```

- [ ] **Step 6: Add `scan_devcache` method**

```python
def scan_devcache(self):
    """Scan VSCode/development tool caches."""
    roaming = self.user_home / "AppData" / "Roaming"
    code = roaming / "Code"

    candidates = [
        (code / "Cache", "VSCode main cache", RiskLevel.SAFE),
        (code / "CachedData", "VSCode cached data", RiskLevel.SAFE),
        (code / "User" / "workspaceStorage", "VSCode workspace state*", RiskLevel.SAFE),
    ]
    for path_, desc, risk in candidates:
        if not path_.exists():
            continue
        size, count = self._walk_size(path_)
        if size > 0 or count > 0:
            yield ScanItem(
                id=self._next_id("DEV"),
                category="devcache",
                path=str(path_),
                size=size,
                risk=risk,
                risk_desc=desc,
                item_count=count,
            )
```

- [ ] **Step 7: Add `scan_othercache` method**

```python
def scan_othercache(self):
    """Scan other system caches (INetCache, FontCache, Store, Java)."""
    local = self.user_home / "AppData" / "Local"
    user = self.user_home

    candidates = [
        (local / "Microsoft" / "Windows" / "INetCache", "Internet temporary files", RiskLevel.SAFE),
        (local / "Microsoft" / "Windows" / "Caches", "System caches", RiskLevel.SAFE),
        (local / "FontCache", "Windows font cache", RiskLevel.SAFE),
        (local / "Microsoft" / "Windows" / "Store" / "Cache", "Microsoft Store cache", RiskLevel.SAFE),
        (user / ".java" / "deployment" / "cache", "Java deployment cache", RiskLevel.SAFE),
    ]
    for path_, desc, risk in candidates:
        if not path_.exists():
            continue
        size, count = self._walk_size(path_)
        if size > 0 or count > 0:
            yield ScanItem(
                id=self._next_id("OTHER"),
                category="othercache",
                path=str(path_),
                size=size,
                risk=risk,
                risk_desc=desc,
                item_count=count,
            )
```

- [ ] **Step 8: Update the `scan()` dispatcher**

Replace the existing `scan()` method:

```python
def scan(self, categories):
    """Scan specified categories.

    Args:
        categories: Iterable of category names to scan.
                    Supported: ``temp``, ``cache``, ``installer``,
                    ``browser``, ``thumbcache``, ``prefetch``,
                    ``sysdumps``, ``package``, ``devcache``,
                    ``othercache``.

    Yields:
        ScanItem objects from each matching scanner method.
    """
    dispatchers = {
        "temp": self.scan_temp,
        "cache": self.scan_cache,
        "installer": self.scan_installer,
        "browser": self.scan_browser,
        "thumbcache": self.scan_thumbcache,
        "prefetch": self.scan_prefetch,
        "sysdumps": self.scan_sysdumps,
        "package": self.scan_package,
        "devcache": self.scan_devcache,
        "othercache": self.scan_othercache,
    }
    for cat in categories:
        dispatcher = dispatchers.get(cat)
        if dispatcher:
            yield from dispatcher()
```

- [ ] **Step 9: Verify scanner.py parses**

Run: `python -c "from scanner import ScannerEngine; print('OK')"`
Expected: `OK`

- [ ] **Step 10: Commit**

```bash
git add scanner.py
git commit -m "feat: add 6 new scanner methods and extend browser scanner"
```

---

### Task 2.2: Add risk patterns to scanner.py

**Files:**
- Modify: `scanner.py`

- [ ] **Step 1: Extend `_SAFE_PATTERNS`**

Find the existing `_SAFE_PATTERNS` list and add the new patterns at the end (before the closing `]`):

```python
    # New patterns for scan expansion
    "*\\Explorer\\thumbcache_*.db",
    "*\\Explorer\\iconcache_*.db",
    "*\\Windows\\Prefetch\\*",
    "*\\CrashDumps\\*",
    "*\\WER\\*",
    "*\\Logs\\*",
    "*\\LogFiles\\*",
    "*\\Microsoft\\Edge\\*Cache\\*",
    "*\\cache2\\*",
    "*\\CachedData\\*",
    "*\\workspaceStorage\\*",
    "*\\INetCache\\*",
    "*\\FontCache\\*",
    "*\\Windows\\Caches\\*",
    "*\\Windows\\Store\\Cache\\*",
    "*\\.yarn\\cache\\*",
    "*\\pnpm\\store\\*",
    "*\\go\\pkg\\mod\\*",
    "*\\.cargo\\registry\\*",
    "*\\.java\\deployment\\cache\\*",
```

- [ ] **Step 2: Extend `_CAUTION_PATTERNS`**

Find the existing `_CAUTION_PATTERNS` list and add:

```python
    "*\\$Recycle.Bin\\*",
    "*\\.nuget\\packages\\*",
    "*\\Minidump\\*",
```

- [ ] **Step 3: Commit**

```bash
git add scanner.py
git commit -m "feat: add risk patterns for new scan categories"
```

---

### Task 2.3: Update sidebar UI with new categories

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: Add new category items to sidebar**

In the sidebar `<aside class="sidebar">`, after the existing browser category `</label>` (between browser and the Start Scan button), add:

```html
<!-- Category: thumbcache -->
<label class="cat-item">
  <input type="checkbox" value="thumbcache" checked>
  <svg class="cat-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>
  </svg>
  <span class="cat-label" data-i18n="cat.thumbcache">Thumbnail Cache</span>
  <span class="cat-badge" data-i18n="cat.thumbcache.badge">Explorer</span>
</label>

<!-- Category: prefetch -->
<label class="cat-item">
  <input type="checkbox" value="prefetch" checked>
  <svg class="cat-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
  </svg>
  <span class="cat-label" data-i18n="cat.prefetch">Prefetch</span>
  <span class="cat-badge" data-i18n="cat.prefetch.badge">Prefetch</span>
</label>

<!-- Category: sysdumps -->
<label class="cat-item">
  <input type="checkbox" value="sysdumps" checked>
  <svg class="cat-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
  </svg>
  <span class="cat-label" data-i18n="cat.sysdumps">System Dumps</span>
  <span class="cat-badge" data-i18n="cat.sysdumps.badge">Dumps</span>
  <span class="admin-hint" style="display:none;font-size:0.7rem;color:#d29922;margin-left:4px" data-i18n="admin.limited">⚠</span>
</label>

<!-- Category: package -->
<label class="cat-item">
  <input type="checkbox" value="package" checked>
  <svg class="cat-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
  </svg>
  <span class="cat-label" data-i18n="cat.package">Package Cache</span>
  <span class="cat-badge" data-i18n="cat.package.badge">npm/pip</span>
</label>

<!-- Category: devcache -->
<label class="cat-item">
  <input type="checkbox" value="devcache" checked>
  <svg class="cat-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
  </svg>
  <span class="cat-label" data-i18n="cat.devcache">Dev Cache</span>
  <span class="cat-badge" data-i18n="cat.devcache.badge">VSCode</span>
</label>

<!-- Category: othercache -->
<label class="cat-item">
  <input type="checkbox" value="othercache" checked>
  <svg class="cat-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>
  </svg>
  <span class="cat-label" data-i18n="cat.othercache">Other Cache</span>
  <span class="cat-badge" data-i18n="cat.othercache.badge">System</span>
</label>
```

- [ ] **Step 2: Add `.btn-operation` class to Start Scan button**

Find the Start Scan button and add the class:
```html
<button class="btn btn-primary btn-block btn-operation" ...
```

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "feat: add 6 new scan categories to sidebar"
```

---

### Task 2.4: Add i18n for new scan categories

**Files:**
- Modify: `i18n/zh.json`
- Modify: `i18n/en.json`

- [ ] **Step 1: Add to zh.json**

Insert after the existing `"cat.browser.badge"` line:

```json
  "cat.thumbcache": "缩略图缓存",
  "cat.thumbcache.badge": "Explorer",
  "cat.prefetch": "预读取文件",
  "cat.prefetch.badge": "Prefetch",
  "cat.sysdumps": "系统转储与日志",
  "cat.sysdumps.badge": "Dumps",
  "cat.package": "包管理器缓存",
  "cat.package.badge": "npm/pip",
  "cat.devcache": "开发工具缓存",
  "cat.devcache.badge": "VSCode",
  "cat.othercache": "其他系统缓存",
  "cat.othercache.badge": "System",
```

- [ ] **Step 2: Add to en.json**

Insert after the existing `"cat.browser.badge"` line:

```json
  "cat.thumbcache": "Thumbnail Cache",
  "cat.thumbcache.badge": "Explorer",
  "cat.prefetch": "Prefetch",
  "cat.prefetch.badge": "Prefetch",
  "cat.sysdumps": "System Dumps & Logs",
  "cat.sysdumps.badge": "Dumps",
  "cat.package": "Package Cache",
  "cat.package.badge": "npm/pip",
  "cat.devcache": "Dev Cache",
  "cat.devcache.badge": "VSCode",
  "cat.othercache": "Other Cache",
  "cat.othercache.badge": "System",
```

- [ ] **Step 3: Commit**

```bash
git add i18n/zh.json i18n/en.json
git commit -m "feat: add i18n for 6 new scan categories"
```

---

## Phase 3: Recycle Bin

### Task 3.1: Add RecycleBin API endpoints to app.py

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add SHQueryRecycleBin constants and API call**

After the existing `# Sandbox mode` comment block, add:

```python
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
```

- [ ] **Step 2: Verify app.py parses**

Run: `python -c "import app; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add Recycle Bin query and empty API"
```

---

### Task 3.2: Add RecycleBin UI to sidebar

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: Add RecycleBin button after risk legend**

In the sidebar, after the risk legend `</div>` and before the sandbox `<hr>` separator, add:

```html
<!-- Recycle Bin -->
<hr style="border:none;border-top:1px solid #21262d;margin:14px 0;">
<div id="recycle-section">
  <div style="display:flex;align-items:center;gap:6px;font-size:0.82rem;color:#8b949e;margin-bottom:6px">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
    </svg>
    <span data-i18n="recycle.title">Recycle Bin</span>
    <span id="recycle-size" style="margin-left:auto;font-size:0.78rem;color:#d29922">-</span>
  </div>
  <button class="btn btn-ghost btn-sm btn-operation" onclick="emptyRecycleBin()" style="width:100%;font-size:0.82rem;" id="btn-empty-recycle">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
    <span data-i18n="recycle.empty">Empty Recycle Bin</span>
  </button>
</div>
```

- [ ] **Step 2: Add RecycleBin JavaScript functions**

In the `<script>` section, add:

```javascript
// ====================================================================
// Recycle Bin
// ====================================================================
function refreshRecycleStatus() {
    fetch('/api/recycle/status')
        .then(function(r) { return r.json(); })
        .then(function(d) {
            document.getElementById('recycle-size').textContent = d.size_fmt;
        });
}

function emptyRecycleBin() {
    if (isBusy) { alert(BUSY_MSG); return; }
    if (!confirm(_t('recycle.confirm'))) return;
    startBusyPolling();
    var btn = document.getElementById('btn-empty-recycle');
    btn.disabled = true;
    fetch('/api/recycle/empty', { method: 'POST' })
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.status === 'emptied') {
                refreshRecycleStatus();
            } else {
                alert(d.error || 'Failed');
            }
        })
        .catch(function() { alert('Failed to empty Recycle Bin'); })
        .finally(function() { btn.disabled = false; });
}
```

Add `refreshRecycleStatus();` to the `DOMContentLoaded` event listener.

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "feat: add Recycle Bin sidebar button and JS"
```

---

### Task 3.3: Add completion report hints

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: Add hints section to complete view**

In the complete report view (`id="view-complete"`), before the "Back to Home" button, add:

```html
<!-- Suggested follow-up actions -->
<div id="complete-hints" style="max-width:500px;margin:0 auto 20px;text-align:left;border:1px solid #21262d;border-radius:8px;padding:12px;background:#161b22">
  <div style="font-size:0.82rem;font-weight:600;color:#8b949e;margin-bottom:8px" data-i18n="complete.hints.title">💡 Suggested Follow-up</div>
  <div id="hint-recycle" style="display:flex;align-items:center;gap:8px;font-size:0.82rem;padding:6px 0;border-bottom:1px solid #21262d">
    <span>🗑️ <span data-i18n="recycle.title">Recycle Bin</span>: <span id="hint-recycle-size" class="hint-value">-</span></span>
    <button class="btn btn-ghost btn-sm" onclick="showView('results');" style="margin-left:auto;font-size:0.78rem" data-i18n="complete.hints.goto">Go</button>
  </div>
  <div id="hint-search" style="display:flex;align-items:center;gap:8px;font-size:0.82rem;padding:6px 0">
    <span>🔍 <span data-i18n="search.title">Search Index</span>: <span id="hint-search-size" class="hint-value">-</span></span>
    <button class="btn btn-ghost btn-sm" onclick="showView('results');" style="margin-left:auto;font-size:0.78rem" data-i18n="complete.hints.goto">Go</button>
  </div>
</div>
```

- [ ] **Step 2: Add hint refresh function**

In the `<script>` section, add:

```javascript
function refreshCompleteHints() {
    // Recycle Bin — real-time query
    fetch('/api/recycle/status')
        .then(function(r) { return r.json(); })
        .then(function(d) {
            document.getElementById('hint-recycle-size').textContent = d.size_fmt;
        });
    // Search Index — real-time query
    fetch('/api/search/status')
        .then(function(r) { return r.json(); })
        .then(function(d) {
            document.getElementById('hint-search-size').textContent = d.size_fmt;
        });
}
```

Call `refreshCompleteHints();` inside the existing `showComplete()` function, after the disk comparison render.

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "feat: add completion report hints for Recycle Bin and Search Index"
```

---

### Task 3.4: Add i18n for RecycleBin

**Files:**
- Modify: `i18n/zh.json`
- Modify: `i18n/en.json`

- [ ] **Step 1: Add to zh.json**

```json
  "recycle.title": "回收站",
  "recycle.empty": "清空回收站",
  "recycle.confirm": "确定要清空回收站吗？此操作不可撤销，文件将被永久删除。",
  "complete.hints.title": "💡 建议后续操作",
  "complete.hints.goto": "前往",
```

- [ ] **Step 2: Add to en.json**

```json
  "recycle.title": "Recycle Bin",
  "recycle.empty": "Empty Recycle Bin",
  "recycle.confirm": "Are you sure you want to empty the Recycle Bin? This operation cannot be undone.",
  "complete.hints.title": "💡 Suggested Follow-up",
  "complete.hints.goto": "Go",
```

- [ ] **Step 3: Commit**

```bash
git add i18n/zh.json i18n/en.json
git commit -m "feat: add i18n for Recycle Bin and completion hints"
```

---

## Phase 4: Windows Search Index

### Task 4.1: Add Search Index API endpoints to app.py

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add Search Index API after Recycle Bin section**

After the Recycle Bin API code block, add:

```python
# ---------------------------------------------------------------------------
# Windows Search Index API
# ---------------------------------------------------------------------------

SEARCH_INDEX_PATH = Path(
    "C:\\ProgramData\\Microsoft\\Search\\Data\\Applications\\Windows\\Windows.edb"
)
WSEARCH_SERVICE_NAME = "WSearch"


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
        import win32serviceutil
        status = win32serviceutil.QueryServiceStatus(WSEARCH_SERVICE_NAME)[1]
        # SERVICE_RUNNING = 4
        return status == 4
    except ImportError:
        # fallback: use sc query via subprocess
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
    return jsonify({
        "size": size,
        "size_fmt": _format_size(size),
        "service_running": running,
        "rebuilding": state == "rebuilding_index",
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
            app.logger.error("Search index rebuild failed: %s", exc)
        finally:
            release_operation()

    t = threading.Thread(target=_rebuild, daemon=True)
    t.start()
    return jsonify({"status": "rebuilding"})
```

- [ ] **Step 2: Verify app.py parses**

Run: `python -c "import app; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add Search Index rebuild API"
```

---

### Task 4.2: Add Search Index UI

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: Add Search Index button to sidebar**

In the sidebar, after the Recycle Bin section (`id="recycle-section"`) and before the sandbox `<hr>`, add:

```html
<!-- Search Index -->
<div id="search-section" style="margin-top:10px">
  <div style="display:flex;align-items:center;gap:6px;font-size:0.82rem;color:#8b949e;margin-bottom:6px">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
    </svg>
    <span data-i18n="search.title">Search Index</span>
    <span id="search-size" style="margin-left:auto;font-size:0.78rem;color:#d29922">-</span>
  </div>
  <button class="btn btn-ghost btn-sm btn-operation" onclick="rebuildSearchIndex()" style="width:100%;font-size:0.82rem;" id="btn-rebuild-index">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
    <span data-i18n="search.rebuild">Rebuild Index</span>
  </button>
  <div id="search-status" style="font-size:0.72rem;color:#8b949e;margin-top:4px;text-align:center;"></div>
</div>
```

- [ ] **Step 2: Add Search Index JavaScript**

After the RecycleBin JS functions, add:

```javascript
// ====================================================================
// Search Index
// ====================================================================
function refreshSearchStatus() {
    fetch('/api/search/status')
        .then(function(r) { return r.json(); })
        .then(function(d) {
            document.getElementById('search-size').textContent = d.size_fmt;
            var statusEl = document.getElementById('search-status');
            if (d.rebuilding) {
                statusEl.textContent = _t('search.rebuilding');
            } else if (d.service_running === false) {
                statusEl.textContent = _t('search.stopped');
            } else {
                statusEl.textContent = _t('search.ready');
            }
            var btn = document.getElementById('btn-rebuild-index');
            btn.disabled = d.rebuilding;
        });
}

function rebuildSearchIndex() {
    if (isBusy) { alert(BUSY_MSG); return; }
    if (!confirm(_t('search.confirm'))) return;
    startBusyPolling();
    var btn = document.getElementById('btn-rebuild-index');
    btn.disabled = true;
    fetch('/api/search/rebuild', { method: 'POST' })
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.status === 'rebuilding') {
                document.getElementById('search-status').textContent = _t('search.rebuilding');
            } else {
                alert(d.error || 'Failed');
                btn.disabled = false;
            }
        })
        .catch(function() { alert('Failed'); btn.disabled = false; });
}
```

Add `refreshSearchStatus();` to the `DOMContentLoaded` event listener alongside `refreshRecycleStatus()`.

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "feat: add Search Index rebuild sidebar button and JS"
```

---

### Task 4.3: Add i18n for Search Index

**Files:**
- Modify: `i18n/zh.json`
- Modify: `i18n/en.json`

- [ ] **Step 1: Add to zh.json**

```json
  "search.title": "搜索索引",
  "search.rebuild": "重建索引",
  "search.rebuilding": "正在重建中...",
  "search.stopped": "服务已停止",
  "search.ready": "正常",
  "search.confirm": "确定要重建搜索索引吗？\n\n重建期间 Windows 搜索将不可用，索引重建过程可能需要数小时，且 CPU 占用较高。\n\n此操作不可撤销！",
```

- [ ] **Step 2: Add to en.json**

```json
  "search.title": "Search Index",
  "search.rebuild": "Rebuild Index",
  "search.rebuilding": "Rebuilding...",
  "search.stopped": "Service stopped",
  "search.ready": "Ready",
  "search.confirm": "Are you sure you want to rebuild the Search Index?\n\nWindows Search will be unavailable during rebuilding. The process may take several hours with high CPU usage.\n\nThis operation cannot be undone!",
```

- [ ] **Step 3: Commit**

```bash
git add i18n/zh.json i18n/en.json
git commit -m "feat: add i18n for Search Index"
```

---

## Phase 5: Software Uninstall Module

### Task 5.1: Add software listing and uninstall API to app.py

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add software listing function**

After the Search Index API block, add:

```python
# ---------------------------------------------------------------------------
# Software Uninstall API
# ---------------------------------------------------------------------------

import winreg
import subprocess
import time


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
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    sub_name = winreg.EnumKey(key, i)
                    sub_key = winreg.OpenKey(key, sub_name)
                    try:
                        name, _ = winreg.QueryValueEx(sub_key, "DisplayName")
                    except OSError:
                        continue

                    # Dedup by display name
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

                    programs.append({
                        "name": name,
                        "version": _read_str(sub_key, "DisplayVersion"),
                        "publisher": _read_str(sub_key, "Publisher"),
                        "install_date": _read_str(sub_key, "InstallDate"),
                        "estimated_size": _read_int(sub_key, "EstimatedSize") * 1024,  # KB → bytes
                        "uninstall_string": _read_str(sub_key, "UninstallString"),
                        "source": "registry",
                    })
                    winreg.CloseKey(sub_key)
                except OSError:
                    continue
            winreg.CloseKey(key)
        except OSError:
            continue

    return programs


@app.route("/api/uninstall/list")
def api_uninstall_list():
    """Return a list of installed programs."""
    programs = _read_registered_programs()
    programs.sort(key=lambda p: p["name"].lower())

    # Format sizes
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

    def _get_uninstall_string(name):
        for p in _read_registered_programs():
            if p["name"] == name:
                return p["uninstall_string"]
        return ""

    def generate():
        try:
            total = len(names)
            for i, name in enumerate(names):
                # Emit progress
                yield {
                    "type": "uninstall_progress",
                    "current": name,
                    "completed": i,
                    "total": total,
                }

                ustr = _get_uninstall_string(name)
                if not ustr:
                    yield {
                        "type": "uninstall_result",
                        "name": name,
                        "success": False,
                        "reason": "No uninstall string found",
                    }
                    continue

                try:
                    # Run uninstall command with timeout
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
```

- [ ] **Step 2: Verify app.py parses**

Run: `python -c "import app; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add software uninstall listing and SSE uninstall API"
```

---

### Task 5.2: Add software management UI

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: Add software management button to sidebar**

In the sidebar, after Search Index section and before the sandbox `<hr>`, add:

```html
<!-- Software Management -->
<div id="software-section" style="margin-top:10px">
  <button class="btn btn-ghost btn-sm btn-operation" onclick="showSoftwareView()" style="width:100%;font-size:0.82rem;" id="btn-software">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
    </svg>
    <span data-i18n="software.title">Software Manager</span>
    <span id="software-count" style="margin-left:auto;font-size:0.78rem;color:#8b949e">-</span>
  </button>
</div>
```

- [ ] **Step 2: Add software management view**

After the existing `view-complete` div and before the closing `</main>`, add:

```html
<!-- ---------------------------------------------------------- -->
<!-- View 7: Software Manager                                   -->
<!-- ---------------------------------------------------------- -->
<div id="view-software" class="hidden">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
    <h2 style="font-size:1.1rem;font-weight:600;color:#c9d1d9">
      <span data-i18n="software.title">Software Manager</span>
      <span id="software-total" style="color:#8b949e;font-size:0.9rem;font-weight:400;margin-left:8px">0 programs</span>
    </h2>
    <button class="btn btn-ghost btn-sm" onclick="showView('empty')" data-i18n="btn.back_home">← Back</button>
  </div>

  <!-- Admin warning -->
  <div id="software-admin-warn" style="display:none;background:rgba(210,153,34,0.08);border:1px solid rgba(210,153,34,0.2);border-radius:6px;padding:8px 12px;font-size:0.82rem;color:#d29922;margin-bottom:12px">
    🔒 <span data-i18n="software.admin_warn">Some programs require admin privileges to uninstall</span>
  </div>

  <!-- Search/filter -->
  <div style="margin-bottom:12px">
    <input type="text" id="software-filter" oninput="filterSoftware()" placeholder="Filter..." style="width:100%;background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:8px 12px;color:#c9d1d9;font-size:0.88rem">
  </div>

  <!-- Actions -->
  <div class="action-buttons" style="border-top:none;padding-top:0;margin-bottom:12px">
    <button class="btn btn-ghost btn-sm" onclick="selectAllSoftware(true)" data-i18n="btn.select_all">Select All</button>
    <button class="btn btn-ghost btn-sm" onclick="selectAllSoftware(false)" data-i18n="btn.deselect_all">Deselect All</button>
    <button class="btn btn-danger btn-sm btn-operation" onclick="startUninstall()">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
      <span data-i18n="software.uninstall">Uninstall Selected</span>
    </button>
  </div>

  <!-- Loading -->
  <div id="software-loading" style="text-align:center;padding:32px;color:#8b949e" data-i18n="software.loading">Loading...</div>

  <!-- Program list container -->
  <div id="software-list" style="max-height:500px;overflow-y:auto;border:1px solid #21262d;border-radius:8px;"></div>

  <!-- Uninstall progress -->
  <div id="software-progress" class="hidden" style="margin-top:16px">
    <div class="progress-section">
      <p><span data-i18n="software.uninstalling">Uninstalling</span>: <span id="uninstall-current">-</span></p>
      <div class="progress-bar">
        <div id="uninstall-progress-fill" class="progress-fill red" style="width:0%"></div>
      </div>
    </div>
    <div class="live-feed">
      <div class="feed-header" data-i18n="software.uninstall_log">Uninstall Log</div>
      <div id="uninstall-feed" style="max-height:200px;overflow-y:auto;"></div>
    </div>
  </div>
</div>
```

- [ ] **Step 3: Add software management JavaScript**

Add to the `<script>` section:

```javascript
// ====================================================================
// Software Manager
// ====================================================================
var allPrograms = [];

function showSoftwareView() {
    showView('software');
    document.getElementById('software-loading').style.display = '';
    document.getElementById('software-list').innerHTML = '';
    document.getElementById('software-progress').classList.add('hidden');

    fetch('/api/uninstall/list')
        .then(function(r) { return r.json(); })
        .then(function(d) {
            allPrograms = d.programs || [];
            document.getElementById('software-loading').style.display = 'none';
            document.getElementById('software-total').textContent = allPrograms.length + ' ' + _t('results.items');
            document.getElementById('software-count').textContent = allPrograms.length;

            var adminWarn = document.getElementById('software-admin-warn');
            adminWarn.style.display = d.admin ? 'none' : '';

            renderSoftwareList(allPrograms);
        });
}

function renderSoftwareList(programs) {
    var html = '';
    programs.forEach(function(p) {
        html += '<div class="result-item" style="border-bottom:1px solid #21262d">'
            + '<input type="checkbox" class="software-cb" data-name="' + escapeHtml(p.name) + '" checked>'
            + '<div style="flex:1;min-width:0;margin-left:8px">'
            + '<div style="font-size:0.88rem;color:#c9d1d9;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + escapeHtml(p.name) + '</div>'
            + '<div style="font-size:0.75rem;color:#8b949e">'
            + (p.publisher ? escapeHtml(p.publisher) + ' · ' : '')
            + (p.version ? escapeHtml(p.version) + ' · ' : '')
            + (p.install_date || '')
            + '</div></div>'
            + '<span style="font-size:0.82rem;color:#8b949e;white-space:nowrap;padding-left:8px">' + (p.size_fmt || '') + '</span>'
            + '</div>';
    });
    document.getElementById('software-list').innerHTML = html || '<div style="padding:16px;text-align:center;color:#8b949e">' + _t('software.empty') + '</div>';
}

function filterSoftware() {
    var q = document.getElementById('software-filter').value.toLowerCase();
    var filtered = allPrograms.filter(function(p) { return p.name.toLowerCase().indexOf(q) !== -1; });
    renderSoftwareList(filtered);
}

function selectAllSoftware(select) {
    document.querySelectorAll('.software-cb').forEach(function(cb) { cb.checked = select; });
}

function startUninstall() {
    var selected = [];
    document.querySelectorAll('.software-cb:checked').forEach(function(cb) {
        selected.push(cb.getAttribute('data-name'));
    });
    if (selected.length === 0) {
        alert(_t('software.select_none'));
        return;
    }
    if (!confirm(_t('software.confirm') + ' (' + selected.length + ' ' + _t('results.items') + ')')) return;

    if (isBusy) { alert(BUSY_MSG); return; }
    startBusyPolling();

    document.getElementById('software-progress').classList.remove('hidden');
    document.getElementById('uninstall-feed').innerHTML = '';
    document.getElementById('uninstall-progress-fill').style.width = '0%';

    fetch('/api/uninstall/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ names: selected })
    })
    .then(function(resp) { return resp.body.getReader(); })
    .then(function(reader) {
        var decoder = new TextDecoder();
        var buffer = '';
        function read() {
            return reader.read().then(function(result) {
                if (result.done) return;
                buffer += decoder.decode(result.value, { stream: true });
                var lines = buffer.split('\n');
                buffer = lines.pop() || '';
                lines.forEach(function(line) {
                    if (line.indexOf('data: ') !== 0) return;
                    try {
                        var ev = JSON.parse(line.substring(6));
                        if (ev.type === 'uninstall_progress') {
                            var pct = Math.round((ev.completed / ev.total) * 100);
                            document.getElementById('uninstall-progress-fill').style.width = pct + '%';
                            document.getElementById('uninstall-current').textContent = ev.current;
                        }
                        if (ev.type === 'uninstall_result') {
                            var feed = document.getElementById('uninstall-feed');
                            var row = document.createElement('div');
                            row.className = 'feed-row';
                            var icon = ev.success ? '✅' : '❌';
                            row.innerHTML = '<span>' + icon + '</span>'
                                + '<span class="mono" style="flex:1;margin-left:6px">' + escapeHtml(ev.name) + '</span>'
                                + '<span style="color:' + (ev.success ? '#3fb950' : '#f85149') + ';font-size:0.8rem">'
                                + (ev.success ? _t('software.success') : _t('software.failed') + (ev.reason ? ': ' + escapeHtml(ev.reason) : ''))
                                + '</span>';
                            feed.appendChild(row);
                            feed.scrollTop = feed.scrollHeight;
                        }
                        if (ev.type === 'uninstall_complete') {
                            document.getElementById('uninstall-progress-fill').style.width = '100%';
                        }
                    } catch(e) {}
                });
                return read();
            });
        }
        return read();
    });
}
```

- [ ] **Step 4: Commit**

```bash
git add templates/index.html
git commit -m "feat: add software management view with uninstall flow"
```

---

### Task 5.3: Add i18n for software uninstall

**Files:**
- Modify: `i18n/zh.json`
- Modify: `i18n/en.json`

- [ ] **Step 1: Add to zh.json**

```json
  "software.title": "软件管理",
  "software.uninstall": "卸载选中",
  "software.loading": "正在加载已安装软件列表...",
  "software.empty": "未找到已安装软件",
  "software.admin_warn": "部分软件需要管理员权限才能卸载，非管理员运行可能失败",
  "software.select_none": "请至少选择一个要卸载的软件",
  "software.confirm": "确定要卸载以下软件吗？",
  "software.success": "已卸载",
  "software.failed": "失败",
  "software.uninstalling": "正在卸载",
  "software.uninstall_log": "卸载日志",
```

- [ ] **Step 2: Add to en.json**

```json
  "software.title": "Software Manager",
  "software.uninstall": "Uninstall Selected",
  "software.loading": "Loading installed programs...",
  "software.empty": "No installed programs found",
  "software.admin_warn": "Some programs require admin privileges to uninstall. Running without admin may cause failures.",
  "software.select_none": "Please select at least one program to uninstall",
  "software.confirm": "Are you sure you want to uninstall the following programs?",
  "software.success": "Uninstalled",
  "software.failed": "Failed",
  "software.uninstalling": "Uninstalling",
  "software.uninstall_log": "Uninstall Log",
```

- [ ] **Step 3: Commit**

```bash
git add i18n/zh.json i18n/en.json
git commit -m "feat: add i18n for software uninstall module"
```

---

### Task 5.4: Add necessary style rules

**Files:**
- Modify: `static/style.css`

- [ ] **Step 1: Add styles for new UI elements**

Append to the existing `style.css`:

```css
/* Admin hint badge */
.admin-hint { font-size: 0.72rem; color: #d29922; margin-left: 4px; vertical-align: middle; }

/* Software manager list */
#software-list .result-item { display: flex; align-items: center; padding: 8px 12px; }
#software-list .result-item:hover { background: #161b22; }

/* Completion hints */
.hint-value { font-weight: 600; color: #d29922; }

/* Recycle bin / Search index section */
#recycle-section, #search-section, #software-section { padding: 0 2px; }
```

- [ ] **Step 2: Commit**

```bash
git add static/style.css
git commit -m "style: add CSS for new scan expansion UI elements"
```

---

## Self-Review

### Spec Coverage Check

- **Phase 1 (global state machine + admin)** → Tasks 1.1, 1.2, 1.3 ✅
- **Phase 2 (7 scanner categories + risk patterns)** → Tasks 2.1, 2.2, 2.3, 2.4 ✅
  - ThumbCache ✅ | Prefetch ✅ | SysDumps ✅ | Browser+ ✅ | Package ✅ | DevCache ✅ | OtherCache ✅
- **Phase 3 (RecycleBin)** → Tasks 3.1, 3.2, 3.3, 3.4 ✅
  - SHQueryRecycleBin ✅ | SHEmptyRecycleBin ✅ | Completion report hints ✅
- **Phase 4 (Search Index)** → Tasks 4.1, 4.2, 4.3 ✅
  - Service control ✅ | DB deletion ✅ | Status monitoring ✅ | Admin check ✅
- **Phase 5 (Software Uninstall)** → Tasks 5.1, 5.2, 5.3, 5.4 ✅
  - Registry listing ✅ | Serial queue ✅ | SSE progress ✅ | Admin hints ✅

### Placeholder Scan
- All steps have complete code blocks ✅
- No "TBD", "TODO", "implement later" patterns ✅
- All commands specify exact run/verify commands ✅
- All commits have descriptive messages ✅

### Type/Name Consistency
- `acquire_operation`, `release_operation`, `get_operation_state` consistently used across tasks ✅
- `"scanning"`, `"emptying_recycle"`, `"rebuilding_index"`, `"uninstalling"` state names match spec ✅
- `is_admin()` function name consistent across app.py and index.html ✅
- Scanner method names match dispatcher keys in `scan()` ✅
