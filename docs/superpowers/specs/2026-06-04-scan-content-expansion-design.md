# SysClean 扫描内容扩展设计

**日期：** 2026-06-04
**状态：** 已批准

---

## 概述

在现有 4 个扫描分类（temp、cache、installer、browser）基础上，扩展扫描覆盖面，新增 7 个扫描类别以及 3 个独立操作模块（回收站清空、Search 索引重建、不常用软件卸载）。所有新增扫描类别均遵循现有的风险等级体系（SAFE / CAUTION / DANGER）。

---

## 一、新增扫描类别

### 1. ThumbCache — 缩略图缓存

| 字段 | 值 |
|------|-----|
| 分类名称 | `thumbcache` |
| 侧边栏标签 | 缩略图缓存 / Thumbnail Cache |
| 风险等级 | ✅ SAFE |

**扫描路径：**
- `%USERPROFILE%\AppData\Local\Microsoft\Windows\Explorer\thumbcache_*.db`
- `%USERPROFILE%\AppData\Local\Microsoft\Windows\Explorer\iconcache_*.db`
- `%USERPROFILE%\AppData\Local\Microsoft\Windows\Explorer\*.db`

**说明：** Windows 自动生成的图片/视频缩略图预览缓存数据库。删除后系统会自动重建。典型占用 200 MB ~ 2 GB。

**实现方式：** `_walk_size` 扫描 `Explorer` 目录，匹配 `.db` 文件。

**风险模式：** `"*\\Explorer\\thumbcache_*.db"`, `"*\\Explorer\\iconcache_*.db"` → SAFE

---

### 2. Prefetch — 预读取文件

| 字段 | 值 |
|------|-----|
| 分类名称 | `prefetch` |
| 侧边栏标签 | 预读取文件 / Prefetch |
| 风险等级 | ✅ SAFE |

**扫描路径：**
- `C:\Windows\Prefetch\*.pf`
- `C:\Windows\Prefetch\*.db`

**说明：** Windows 记录应用启动信息的优化缓存，清理不影响功能，下次启动自动重建。

**实现方式：** `_walk_size` 扫描 `Prefetch` 目录。

---

### 3. SysDumps — 崩溃转储 + WER + 日志

| 字段 | 值 |
|------|-----|
| 分类名称 | `sysdumps` |
| 侧边栏标签 | 系统转储与日志 / System Dumps & Logs |
| 风险等级 | 混合（SAFE + CAUTION） |

**扫描路径：**

| 路径 | 风险 | 说明 |
|------|------|------|
| `%LOCALAPPDATA%\CrashDumps\` | ✅ SAFE | 应用崩溃转储 |
| `%LOCALAPPDATA%\Microsoft\Windows\WER\` | ✅ SAFE | 用户级错误报告 |
| `C:\ProgramData\Microsoft\Windows\WER\` | ✅ SAFE | 系统级错误报告 |
| `C:\Windows\Minidump\*.dmp` | ⚠️ CAUTION | 系统迷你转储 |
| `C:\Windows\memory.dmp` | ⚠️ CAUTION | 完整内存转储 |
| `C:\Windows\Logs\` | ✅ SAFE | 系统日志 |
| `C:\Windows\System32\LogFiles\` | ✅ SAFE | IIS/HTTP 日志 |

**说明：** memory.dmp 可能非常大（等于物理内存大小），自动归类为 CAUTION。

**权限说明：** 以下路径的扫描结果**受权限限制可能不完整**：
- `C:\Windows\Logs\` — 部分子目录需管理员权限
- `C:\Windows\System32\LogFiles\` — 部分子目录需管理员权限
- `C:\Windows\Minidump\` — 通常不可读，仅管理员可读
- `C:\Windows\memory.dmp` — 需要 `SE_BACKUP_NAME` 特权，普通用户无法读取
- `C:\ProgramData\Microsoft\Windows\WER\` — 部分子目录需管理员权限

扫描器对无权限目录静默跳过，用户看到的结果为当前权限下的子集。**如需完整扫描结果，建议以管理员身份运行。** UI 上在 SysDumps 分类旁增加 ⚠️ 图标提示"部分结果受权限限制"。

---

### 4. Browser+ — 多浏览器缓存扩展

| 字段 | 值 |
|------|-----|
| 分类名称 | `browser` （扩展现有分类） |
| 侧边栏标签 | 浏览器缓存 / Browser Cache（保持单一项） |
| 风险等级 | ✅ SAFE |

**扩展路径（在现有 Chrome 路径基础上新增）：**

| 浏览器 | 路径 |
|--------|------|
| Edge | `%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Cache\` |
| Edge | `%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Code Cache\` |
| Firefox | `%LOCALAPPDATA%\Mozilla\Firefox\Profiles\*\cache2\` |
| Firefox | `%LOCALAPPDATA%\Mozilla\Firefox\Profiles\*\thumbnails\` |

**说明：** 扩展现有 `browser` 分类，侧边栏保持一项，结果视图中展开显示不同浏览器。

**Firefox 多 Profile 处理：** Firefox 可能包含多个 profile（默认 release、beta、dev 等），扫描器需要遍历 `Profiles\` 下所有子目录，对每个 profile 分别扫描 `cache2` 和 `thumbnails`。结果在 UI 中合并显示。

---

### 5. Package — 包管理器缓存

| 字段 | 值 |
|------|-----|
| 分类名称 | `package` |
| 侧边栏标签 | 包管理器缓存 / Package Cache |
| 风险等级 | 混合（SAFE + CAUTION） |

**扫描路径：**

| 包管理器 | 路径 | 风险 |
|---------|------|------|
| npm | `%APPDATA%\npm-cache\` | ✅ SAFE |
| yarn | `%USERPROFILE%\.yarn\cache\` | ✅ SAFE |
| pnpm | `%LOCALAPPDATA%\pnpm\store\` | ✅ SAFE |
| pip | `%LOCALAPPDATA%\pip\cache\` | ✅ SAFE |
| NuGet | `%USERPROFILE%\.nuget\packages\` | ⚠️ CAUTION |
| Go | `%USERPROFILE%\go\pkg\mod\` | ✅ SAFE |
| Cargo | `%USERPROFILE%\.cargo\registry\` | ✅ SAFE |

**NuGet 标记 CAUTION 原因：** .NET 项目在离线环境依赖本地包缓存，清理后需重新下载。

---

### 6. DevCache — VSCode 开发工具缓存

| 字段 | 值 |
|------|-----|
| 分类名称 | `devcache` |
| 侧边栏标签 | 开发工具缓存 / Dev Cache |
| 风险等级 | ✅ SAFE |

**扫描路径：**
- `%APPDATA%\Code\Cache\`
- `%APPDATA%\Code\CachedData\`
- `%APPDATA%\Code\User\workspaceStorage\`

**说明：** 仅清理 VSCode 缓存数据，不影响扩展和设置。下次启动自动重建。注意：清理 `workspaceStorage` 会丢失工作区布局（打开的标签页、窗口位置等），**界面状态会重置**但不影响代码文件。

**风险补充：** `workspaceStorage` 清理后 VSCode 会恢复到默认布局，用户需重新打开需要的文件。功能上无损，体验上需要注意。

---

### 7. OtherCache — 其他系统缓存

| 字段 | 值 |
|------|-----|
| 分类名称 | `othercache` |
| 侧边栏标签 | 其他系统缓存 / Other Cache |
| 风险等级 | ✅ SAFE |

**扫描路径：**
- `%LOCALAPPDATA%\Microsoft\Windows\INetCache\` — Internet 临时文件
- `%LOCALAPPDATA%\Microsoft\Windows\Caches\` — 系统通用缓存
- `%LOCALAPPDATA%\FontCache\` — 字体缓存
- `%LOCALAPPDATA%\Microsoft\Windows\Store\Cache\` — Microsoft Store 缓存
- `%USERPROFILE%\.java\deployment\cache\` — Java 部署缓存

---

### 8. RecycleBin — 回收站（特殊独立操作）

| 字段 | 值 |
|------|-----|
| 类型 | 独立操作按钮（非扫描分类） |
| 风险等级 | ⚠️ CAUTION |

**设计要点：**
- 不作为扫描分类，在侧边栏放置独立的 **"清空回收站"** 按钮
- 通过 `SHQueryRecycleBin` API 获取回收站大小和文件数
- 通过 `SHEmptyRecycleBin` API 执行清空操作
- 清理完成后更新侧边栏回收站大小显示
- 在清理完成报告中添加提示文字，引导用户主动清理回收站
- 与扫描/清理/卸载共用操作互斥锁，防止并发冲突

---

### 9. Windows Search 索引 — 重建索引（特殊独立操作）

| 字段 | 值 |
|------|-----|
| 类型 | 独立操作按钮（非扫描分类） |
| 侧边栏标签 | Windows Search 索引 / Search Index |
| 风险等级 | ⚠️ CAUTION |

**说明：** Windows Search 为加速文件搜索而建立的全文索引数据库，存储在 `C:\ProgramData\Microsoft\Search\Data\Applications\Windows\Windows.edb`。该文件被 `SearchIndexer.exe` 独占锁定，无法直接删除。

**操作流程：**

```
用户点击 [重建索引]
        ↓
弹出详细警告（搜索不可用、高CPU、重建耗时）
        ↓
用户确认
        ↓
停止 WSearch 服务 (ControlService)
    ↓
删除 Windows.edb + 日志文件
    ↓
重启 WSearch 服务
    ↓
自动开始重建（后台）
    ↓
更新侧边栏状态与大小
```

**设计要点：**

| 方面 | 说明 |
|------|------|
| 容量显示 | 使用 `os.path.getsize()` 读取 `Windows.edb` 大小，显示在侧边栏按钮旁 |
| 状态监控 | 通过 `ServiceController` 查询 WSearch 服务状态（运行中/已停止/重建中） |
| 操作前后 | 清理前记录当前索引大小；清理后更新为 "重建中..."；定期轮询恢复后显示新大小 |
| 与全局锁关系 | 操作时占用全局锁（状态 `REBUILDING_INDEX`），禁止并发操作 |
| 不可撤销 | 清理前在确认弹窗中明确强调：此操作不可撤销，且重建期间搜索不可用 |
| 服务恢复 | 确保服务重启成功，失败时记录错误日志 |

**侧边栏示意：**
```
┌─────────────────────┐
│ 🗑️ 回收站  占用 2.3GB │
│ [清空回收站]         │
│                     │
│ 🔍 搜索索引  占用 1.8GB │  ← 独立按钮
│ [重建索引]           │
└─────────────────────┘
```

**在完成报告中的提示：**
清理完成后，在完成报告底部增加提示区域，同时显示回收站和搜索索引的状态。注意：回收站大小和搜索索引大小需**实时查询**（每次显示时重新请求 API），而非使用缓存数据：
```
┌────────────────────────────────┐
│ 💡 建议后续操作：                │
│                                │
│ 🗑️ 回收站当前占用 2.3 GB        │
│    [前往清空]                   │
│                                │
│ 🔍 搜索索引当前占用 1.8 GB       │
│    [前往重建]                   │
└────────────────────────────────┘
```

---

## 二、软件卸载模块（独立功能）

### 概述

独立的软件管理视图，与文件清理流程完全解耦。用户可在侧边栏点击"软件管理"进入专用视图。

### 数据来源

1. **注册表 64 位：** `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\`
2. **注册表 32 位：** `HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\`
3. **用户级别：** `HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\`
4. **MSIX/AppX：** 通过 Python 调用 PowerShell `Get-AppxPackage`

### 展示字段

| 字段 | 说明 |
|------|------|
| 名称 | 含版本号 |
| 发布者 | 如 Microsoft、Google 等 |
| 安装日期 | 用于判断是否常用 |
| 估算大小 | 注册表 `EstimatedSize` 字段 |
| 来源 | 注册表 / MSIX / AppX |

### 卸载流程

- **串行队列卸载** — 批量卸载时逐个串行执行
- 使用 `msiexec` 运行卸载程序或执行 `UninstallString`
- MSIX/AppX 调用 PowerShell `Remove-AppxPackage`
- 通过 SSE 推送实时进度（当前正在卸载、已完成列表、队列等待）
- 单个失败不影响队列继续
- 用户可随时取消队列
- 每个卸载有超时保护（防止卸载程序卡死）

### 并发控制 — 全局操作状态机

所有耗时操作共享一个全局状态锁，确保任何时刻只有一个操作在执行：

#### 状态定义

```
IDLE                → 无操作进行中，可启动任何操作
SCANNING            → 扫描中
CLEANING            → 文件清理中  
UNINSTALLING        → 软件卸载中
EMPTYING_RECYCLE    → 清空回收站中
REBUILDING_INDEX    → 重建 Search 索引中
```

#### 转换规则

```
IDLE ──→ 任何操作（通过 acquire）
任何状态 ──→ IDLE（操作完成/失败/取消）

非 IDLE → 其他操作：拒绝（返回 409 Conflict）
```

#### 具体场景覆盖

| 场景 | 当前防护 | 问题 | 解决方案 |
|------|---------|------|---------|
| 扫描中又启动扫描 | `scan_in_progress` ✅ | 已有 | 扩展为通用锁 |
| 清理中又启动清理 | 无 ❌ | 两个 SSE 流同时写文件 | 全局锁拒绝 |
| 扫描中启动清理 | 无 ❌ | 扫描结果被修改 | 全局锁拒绝 |
| 清理中启动扫描 | 无 ❌ | 扫描读到不完整状态 | 全局锁拒绝 |
| 卸载中启动扫描/清理 | 无 ❌ | 文件系统状态变化 | 全局锁拒绝 |
| 清空回收站时启动其他 | 无 ❌ | 回收站状态不一致 | 全局锁拒绝 |
| 重建索引时启动其他 | 无 ❌ | 服务状态突变 | 全局锁拒绝 |

#### 后端实现

```python
# 全局操作状态
import threading
_operation_lock = threading.Lock()
_operation_state: Optional[str] = None  # None | "scanning" | "cleaning" | "uninstalling" | "emptying_recycle" | "rebuilding_index"

def acquire_operation(op_name: str) -> bool:
    """尝试获取操作锁。成功返回 True，失败返回 False。"""
    global _operation_state
    with _operation_lock:
        if _operation_state is not None:
            return False
        _operation_state = op_name
        return True

def release_operation():
    """释放操作锁。"""
    global _operation_state
    with _operation_lock:
        _operation_state = None

# 在各 API 端点中使用
@app.route("/api/scan/start", methods=["POST"])
def api_scan_start():
    if not acquire_operation("scanning"):
        return jsonify({"error": "另一个操作正在进行中"}), 409
    try:
        # ... 启动扫描线程 ...
    except:
        release_operation()

# 注意：扫描在后台线程完成，release 时机在扫描结束后
def _run_scan():
    try:
        scan_results = list(scan_engine.scan(categories))
    finally:
        with scan_lock:
            scan_in_progress = False
        release_operation()
```

#### 前端防护

前端通过定时轮询和后端状态双重保障：

```javascript
// 全局操作状态
let isBusy = false;
let busyPollInterval = null;
const BUSY_MESSAGE = '当前有操作进行中，请等待完成';

function startBusyPolling() {
    // 操作进行中时每 2 秒轮询一次状态
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
        .then(r => r.json())
        .then(d => {
            isBusy = d.operation !== null;
            updateButtons();
            if (!isBusy) stopBusyPolling();
        });
}

function updateButtons() {
    // 禁用所有操作按钮
    document.querySelectorAll('.btn-operation').forEach(btn => {
        btn.disabled = isBusy;
    });
}

// 所有操作按钮的 click 处理中先检查 isBusy，启动操作后开始轮询
function startScan()      { if (isBusy) { alert(BUSY_MESSAGE); return; } startBusyPolling(); /* ... */ }
function confirmClean()   { if (isBusy) { alert(BUSY_MESSAGE); return; } startBusyPolling(); /* ... */ }
function startUninstall() { if (isBusy) { alert(BUSY_MESSAGE); return; } startBusyPolling(); /* ... */ }
function emptyRecycle()   { if (isBusy) { alert(BUSY_MESSAGE); return; } startBusyPolling(); /* ... */ }
function rebuildIndex()   { if (isBusy) { alert(BUSY_MESSAGE); return; } startBusyPolling(); /* ... */ }
```

#### 后端状态查询端点

```python
@app.route("/api/operation/status")
def api_operation_status():
    """返回当前是否有操作进行中及其类型。"""
    global _operation_state
    with _operation_lock:
        return jsonify({
            "busy": _operation_state is not None,
            "operation": _operation_state,
        })
```

#### 清理内部并发说明

清理操作内部已是**串行**处理（`clean_items()` 逐个文件遍历），因此同一清理流程内不会并发写文件。卸载也是**串行队列**（逐个程序卸载）。这两个操作本身不需要内部并发控制，只需要外部全局锁防止跨操作冲突。

### 管理员权限策略

部分操作需要管理员权限才能正常工作：

| 操作 | 需要管理员 | 原因 |
|------|:--------:|------|
| 扫描 SysDumps 完整结果 | ✅ | `C:\Windows\Logs\`、`Minidump`、`memory.dmp` 仅管理员可读 |
| 重建 Search 索引 | ✅ | 停止/启动 `WSearch` Windows 服务需要管理员权限 |
| 卸载部分软件 | ⚠️ 部分 | 多数 MSI 程序需要管理员权限才能卸载 |
| 清空回收站 | ❌ | `SHEmptyRecycleBin` 普通用户也可调用 |
| 其他扫描类别 | ❌ | 均在用户目录内，无需管理员 |

**实现方式：**

```python
import ctypes

def is_admin() -> bool:
    """检查当前进程是否以管理员权限运行。"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False
```

**UI 处理策略：**
- app 启动时检测是否管理员权限
- 非管理员运行时，侧边栏对应按钮显示小图标或文字提示：
  - SysDumps 分类旁：`⚠️ 部分结果受权限限制`
  - Search Index 按钮旁：`🔒 需要管理员权限`
  - 软件卸载列表中受影响的项目：`🔒 需管理员权限`
- 用户点击需要管理员权限的操作时，弹出提示建议以管理员身份运行

---

## 三、新增风险匹配模式

### SAFE 模式扩展

```python
_SAFE_PATTERNS += [
    "*\\Explorer\\thumbcache_*.db",
    "*\\Explorer\\iconcache_*.db",
    "*\\Windows\\Prefetch\\*",
    "*\\CrashDumps\\*",
    "*\\WER\\*",
    "*\\Logs\\*",
    "*\\LogFiles\\*",
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
]
```

### CAUTION 模式扩展

```python
_CAUTION_PATTERNS += [
    "*\\$Recycle.Bin\\*",
    "*\\.nuget\\packages\\*",
    "*\\Minidump\\*",
]
```

---

## 四、涉及修改的文件

| 文件 | 修改内容 |
|------|---------|
| `scanner.py` | 新增 `scan_thumbcache`、`scan_prefetch`、`scan_sysdumps`、`scan_package`、`scan_devcache`、`scan_othercache` 方法；扩展 `scan()` 分发器；扩展风险模式列表 |
| `cleaner.py` | 无修改（清理逻辑不变） |
| `app.py` | 新增软件卸载 API 端点；新增回收站管理 API（`SHQueryRecycleBin`/`SHEmptyRecycleBin`）；新增 Search 索引重建 API（服务控制）；新增全局操作状态机（`acquire_operation`/`release_operation`/`/api/operation/status`）；新增管理员权限检测；替换 `scan_in_progress` 为通用互斥锁；扩展扫描分类列表 |
| `templates/index.html` | 侧边栏新增 7 个扫描分类项；新增"软件管理"独立视图；新增"清空回收站"按钮；新增"重建 Search 索引"按钮；新增管理员权限提示；修改完成报告增加回收站/Search 索引提示；前端全局 `isBusy` 控制 |
| `i18n/zh.json` | 新增所有类别的中文字符串 |
| `i18n/en.json` | 新增所有类别的英文字符串 |
| `static/style.css` | 可能需少量样式调整 |

---

## 五、实施优先级

1. **Phase 1** — 全局操作状态机（操作互斥锁 + `/api/operation/status`） + 管理员权限检测
2. **Phase 2** — 新增 7 个扫描类别（ThumbCache, Prefetch, SysDumps, Browser+, Package, DevCache, OtherCache）+ 风险模式扩展
3. **Phase 3** — 回收站独立按钮（`SHQueryRecycleBin` + `SHEmptyRecycleBin`） + 完成报告回收站提示
4. **Phase 4** — Windows Search 索引重建（服务控制 + 数据库清理 + 状态监控）
5. **Phase 5** — 软件卸载模块（注册表读取 + 串行卸载 + SSE 进度）

---

## 六、验收标准

- [ ] 7 个新增扫描类别均可正常扫描并返回结果
- [ ] Edge/Firefox 缓存与 Chrome 缓存整合显示，Firefox 多 profile 正确合并
- [ ] 侧边栏回收站按钮正确显示大小并可清空
- [ ] 清理完成报告实时查询回收站和 Search 索引状态并提示用户
- [ ] Windows Search 索引重建：停服务 → 删数据库 → 启服务 → 状态监控完整
- [ ] 软件卸载模块正确列出已安装程序，串行卸载进度正确
- [ ] 全局操作状态机防止并发冲突（扫描/清理/卸载/回收站/重建索引全部互斥）
- [ ] 前端按钮在操作进行中时正确禁用，`/api/operation/status` 正确返回
- [ ] 管理员权限检测：非管理员运行时 SysDumps 显示权限提示，Search 索引显示 🔒
- [ ] 清理 + 卸载内部串行处理，无并发风险
- [ ] 中英文界面完整覆盖
