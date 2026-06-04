"""SysClean - Scanning Engine.

Provides ScanItem, RiskLevel, classify_risk, and ScannerEngine for
discovering cleanable files and directories on a Windows system.
"""

import dataclasses
import enum
import fnmatch
import os
from pathlib import Path


class RiskLevel(enum.Enum):
    SAFE = "safe"
    CAUTION = "caution"
    DANGER = "danger"


@dataclasses.dataclass
class ScanItem:
    """One cleanable item found during scanning."""

    id: str
    category: str
    path: str
    size: int
    risk: RiskLevel
    risk_desc: str
    item_count: int = 0


# ---------------------------------------------------------------------------
# Risk classification patterns (checked in order: danger, caution, safe)
# ---------------------------------------------------------------------------

_DANGER_PATTERNS = [
    "*\\Windows\\System32\\*",
    "*\\Windows\\WinSxS\\*",
]

_CAUTION_PATTERNS = [
    "*\\.vscode\\extensions\\*",
    "*\\JianyingPro\\User Data\\*",
    "*\\JianyingPro\\Apps\\*",
    "*\\StreetFighterV\\*",
    "*\\Program Files\\WindowsApps\\*",
]

_SAFE_PATTERNS = [
    "*\\Temp\\*",
    "*\\Windows\\Temp\\*",
    "*\\AppData\\Local\\Temp\\*",
    "*\\MSI*.log",
    "*\\DXCache\\*",
    "*\\GLCache\\*",
    "*\\*updater\\installer.exe",
    "*\\*updater\\pending\\*",
    "*\\npm-cache\\*",
    "*\\pip\\cache\\*",
    "*\\pip\\http\\*",
    "*\\Google\\Chrome\\*Cache\\*",
    "*\\Code Cache\\*",
    "*\\app_shell_cache*\\*",
]


def classify_risk(path, size=0):
    """Classify the risk level of a file or directory path.

    Uses fnmatch to match the path against known safe, caution, and danger
    patterns. Falls back to size-based classification when no pattern matches.

    Args:
        path: The file or directory path string.
        size: Size in bytes (used for fallback classification).

    Returns:
        RiskLevel enum value.
    """
    # Check danger patterns first (most restrictive)
    for pattern in _DANGER_PATTERNS:
        if fnmatch.fnmatch(path, pattern):
            return RiskLevel.DANGER

    # Check caution patterns
    for pattern in _CAUTION_PATTERNS:
        if fnmatch.fnmatch(path, pattern):
            return RiskLevel.CAUTION

    # Check safe patterns
    for pattern in _SAFE_PATTERNS:
        if fnmatch.fnmatch(path, pattern):
            return RiskLevel.SAFE

    # Default: size-based classification
    if size > 500 * 1024 * 1024:  # 500 MB
        return RiskLevel.CAUTION

    return RiskLevel.SAFE


# ---------------------------------------------------------------------------
# ScannerEngine
# ---------------------------------------------------------------------------


class ScannerEngine:
    """Scans the system for cleanable files and directories.

    Each scanner method is a generator that yields ScanItem objects.
    """

    def __init__(self):
        self.user_home = Path(os.environ.get("USERPROFILE", "C:\\Users\\default"))
        self.counter = 0

    def _next_id(self, prefix):
        self.counter += 1
        return f"{prefix}-{self.counter:04d}"

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _walk_size(directory):
        """Walk a directory and return (total_size, file_count).

        Silently skips files/directories that cause permission errors.
        """
        total_size = 0
        file_count = 0
        if not directory.exists():
            return 0, 0
        try:
            for root, dirs, files in os.walk(directory):
                for f in files:
                    try:
                        fp = Path(root) / f
                        if fp.is_file():
                            total_size += fp.stat().st_size
                            file_count += 1
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            pass
        return total_size, file_count

    # -----------------------------------------------------------------------
    # Scanners
    # -----------------------------------------------------------------------

    def scan_temp(self):
        """Scan temporary directories: C:\\Windows\\Temp and user %TEMP%."""
        paths = [
            ("C:\\Windows\\Temp", "Windows system temporary files"),
            (
                str(self.user_home / "AppData" / "Local" / "Temp"),
                "User temporary files",
            ),
        ]
        for path_str, desc in paths:
            p = Path(path_str)
            if not p.exists():
                continue
            size, count = self._walk_size(p)
            if size > 0 or count > 0:
                yield ScanItem(
                    id=self._next_id("TEMP"),
                    category="temp",
                    path=path_str,
                    size=size,
                    risk=classify_risk(path_str, size),
                    risk_desc=desc,
                    item_count=count,
                )

    def scan_cache(self):
        """Scan GPU shader cache directories (DXCache, GLCache)."""
        local = self.user_home / "AppData" / "Local"
        candidates = [
            (local / "NVIDIA" / "DXCache", "NVIDIA DirectX shader cache"),
            (local / "AMD" / "GLCache", "AMD OpenGL shader cache"),
            (local / "NVIDIA" / "GLCache", "NVIDIA OpenGL shader cache"),
            (local / "AMD" / "DXCache", "AMD DirectX shader cache"),
        ]
        for path_, desc in candidates:
            if not path_.exists():
                continue
            size, count = self._walk_size(path_)
            if size > 0 or count > 0:
                yield ScanItem(
                    id=self._next_id("CACHE"),
                    category="cache",
                    path=str(path_),
                    size=size,
                    risk=classify_risk(str(path_), size),
                    risk_desc=desc,
                    item_count=count,
                )

    def scan_installer(self):
        """Scan for orphaned installer/updater files.

        Searches for:
        - *\\*updater\\installer.exe     (installer executables)
        - *\\*updater\\pending\\*        (pending update directories)
        """
        roots = [
            "C:\\Program Files",
            "C:\\Program Files (x86)",
            str(self.user_home / "AppData" / "Local"),
            str(self.user_home / "AppData" / "LocalLow"),
        ]
        for root in roots:
            rp = Path(root)
            if not rp.exists():
                continue
            try:
                # Walk with a depth limit (5 levels should cover updater
                # nesting like: root/app-version/updater/installer.exe).
                for level, (root_dir, dirs, files) in enumerate(
                    os.walk(rp)
                ):
                    if level > 4:
                        dirs.clear()  # stop descending further
                        continue

                    root_path = Path(root_dir)

                    # Does this directory end with "updater"?
                    if root_path.name.lower().endswith("updater"):
                        installer = root_path / "installer.exe"
                        if installer.exists():
                            try:
                                exe_size = installer.stat().st_size
                            except OSError:
                                exe_size = 0
                            yield ScanItem(
                                id=self._next_id("INST"),
                                category="installer",
                                path=str(installer),
                                size=exe_size,
                                risk=classify_risk(
                                    str(installer), exe_size
                                ),
                                risk_desc="Orphaned installer executable",
                                item_count=1,
                            )

                        pending = root_path / "pending"
                        if pending.exists():
                            psize, pcount = self._walk_size(pending)
                            if psize > 0 or pcount > 0:
                                yield ScanItem(
                                    id=self._next_id("INST"),
                                    category="installer",
                                    path=str(pending),
                                    size=psize,
                                    risk=classify_risk(
                                        str(pending), psize
                                    ),
                                    risk_desc=(
                                        "Pending updater files"
                                    ),
                                    item_count=pcount,
                                )
            except (OSError, PermissionError):
                continue

    def scan_browser(self):
        """Scan browser cache directories (Chrome Cache, Code Cache)."""
        local = self.user_home / "AppData" / "Local"
        chrome_cache = (
            local
            / "Google"
            / "Chrome"
            / "User Data"
            / "Default"
            / "Cache"
        )
        chrome_code_cache = (
            local
            / "Google"
            / "Chrome"
            / "User Data"
            / "Default"
            / "Code Cache"
        )

        browser_paths = [
            (chrome_cache, "Chrome browser cache"),
            (chrome_code_cache, "Chrome Code Cache"),
        ]
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

    # -----------------------------------------------------------------------
    # Dispatcher
    # -----------------------------------------------------------------------

    def scan(self, categories):
        """Scan specified categories.

        Args:
            categories: Iterable of category names to scan.
                        Supported: ``temp``, ``cache``, ``installer``,
                        ``browser``.

        Yields:
            ScanItem objects from each matching scanner method.
        """
        dispatchers = {
            "temp": self.scan_temp,
            "cache": self.scan_cache,
            "installer": self.scan_installer,
            "browser": self.scan_browser,
        }
        for cat in categories:
            dispatcher = dispatchers.get(cat)
            if dispatcher:
                yield from dispatcher()
