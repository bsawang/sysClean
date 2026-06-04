"""SysClean - Clean Executor.

Provides CleanExecutor for safely removing files and directories with
recycle-bin support, fallback deletion, and structured progress reporting.
"""

import ctypes
import ctypes.wintypes
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path


# Windows Shell API constants
FO_DELETE = 0x0003
FOF_ALLOWUNDO = 0x0040
FOF_NOCONFIRMATION = 0x0010
FOF_SILENT = 0x0004


class SHFILEOPSTRUCTW(ctypes.Structure):
    """Structure for SHFileOperationW."""

    _fields_ = [
        ("hwnd", ctypes.wintypes.HWND),
        ("wFunc", ctypes.c_uint),
        ("pFrom", ctypes.wintypes.LPCWSTR),
        ("pTo", ctypes.wintypes.LPCWSTR),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", ctypes.wintypes.BOOL),
        ("hNameMappings", ctypes.wintypes.LPVOID),
        ("lpszProgressTitle", ctypes.wintypes.LPCWSTR),
    ]


class CleanExecutor:
    """Executes cleanup operations with recycle-bin and fallback deletion.

    Attributes:
        log_dir: Directory path for log files.
        logger: Python logger instance.
    """

    def __init__(self, log_dir="logs"):
        self.log_dir = log_dir
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)
        self._setup_logging()

    def _setup_logging(self):
        """Configure file-based logging with UTF-8 encoding."""
        log_file = Path(self.log_dir) / f"sysclean-{datetime.now():%Y-%m-%d}.log"
        handler = logging.FileHandler(
            str(log_file), encoding="utf-8", mode="a"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )
        self.logger = logging.getLogger("SysClean")
        self.logger.setLevel(logging.INFO)
        # Replace or add handler to avoid duplicates across calls
        if self.logger.handlers:
            self.logger.handlers.clear()
        self.logger.addHandler(handler)

    @staticmethod
    def _is_file_locked(path):
        """Check if a file is in use by attempting to open it exclusively.

        Tries to open the file in read-write binary mode. If the file does not
        exist or is locked by another process, returns True.

        Args:
            path: Path to the file.

        Returns:
            True if the file is locked or missing, False if accessible.
        """
        try:
            with open(path, "r+b"):
                pass
            return False
        except (OSError, PermissionError, FileNotFoundError):
            return True

    @staticmethod
    def _move_to_recycle_bin(path):
        """Send a file or directory to the Recycle Bin via Windows Shell API.

        Uses SHFileOperationW with FOF_ALLOWUNDO to enable restore support.

        Args:
            path: Absolute path to the file or directory.

        Returns:
            True if the operation succeeded, False otherwise.
        """
        # SHFileOperationW requires double-null-terminated wide string
        frm = ctypes.c_wchar_p(path + "\0\0")
        op = SHFILEOPSTRUCTW(
            hwnd=None,
            wFunc=FO_DELETE,
            pFrom=frm,
            pTo=None,
            fFlags=FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT,
            fAnyOperationsAborted=False,
            hNameMappings=None,
            lpszProgressTitle=None,
        )
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        return result == 0

    @staticmethod
    def _walk_size(directory):
        """Walk a directory and return total size in bytes.

        Silently skips files/directories that cause permission errors.

        Args:
            directory: Path to the directory.

        Returns:
            Total size of all files in the directory in bytes.
        """
        total = 0
        try:
            for root, dirs, files in os.walk(directory):
                for f in files:
                    try:
                        fp = Path(root) / f
                        if fp.is_file():
                            total += fp.stat().st_size
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            pass
        return total

    def delete_item(self, item):
        """Delete a single scan item, prioritising the Recycle Bin.

        Calculates the item's size on disk *before* deletion for accurate
        logging. Tries Recycle Bin first, then falls back to ``os.remove``
        (files) or ``shutil.rmtree`` (directories).

        Args:
            item: A ``ScanItem`` or dict-like object with a ``path``
                  attribute/key.

        Returns:
            Tuple of ``(success: bool, freed_bytes: int)``.
        """
        # Normalise dict-like items to attribute access
        if isinstance(item, dict):
            path = item["path"]
        else:
            path = item.path

        path = str(path)

        # Calculate size BEFORE deletion
        if os.path.isfile(path):
            try:
                freed = os.path.getsize(path)
            except OSError:
                freed = 0
        elif os.path.isdir(path):
            freed = self._walk_size(path)
        else:
            self.logger.warning("Path does not exist: %s", path)
            return False, 0

        # Priority 1: Recycle Bin
        if self._move_to_recycle_bin(path):
            self.logger.info(
                "Recycled: %s (%s)", path, self._format_size(freed)
            )
            return True, freed

        # Priority 2 (fallback): direct deletion
        try:
            if os.path.isfile(path):
                os.remove(path)
                self.logger.info(
                    "Deleted file: %s (%s)", path, self._format_size(freed)
                )
            elif os.path.isdir(path):
                shutil.rmtree(path)
                self.logger.info(
                    "Deleted directory: %s (%s)",
                    path,
                    self._format_size(freed),
                )
            return True, freed
        except (OSError, PermissionError) as exc:
            self.logger.error("Failed to delete %s: %s", path, exc)
            return False, 0

    def clean_items(self, items):
        """Iterate over items to clean, yielding SSE-friendly progress dicts.

        Args:
            items: Iterable of ``ScanItem`` objects (or dicts with ``path``).

        Yields:
            Progress dicts suitable for server-sent events:

            - ``clean_progress`` after each item is processed.
            - ``clean_complete`` when all items have been processed.
        """
        # Materialise so total is known upfront
        item_list = list(items)
        total = len(item_list)
        completed = 0
        failed_count = 0
        total_freed = 0

        for item in item_list:
            success, freed = self.delete_item(item)
            completed += 1
            total_freed += freed
            if not success:
                failed_count += 1

            if isinstance(item, dict):
                path = item["path"]
            else:
                path = item.path

            yield {
                "type": "clean_progress",
                "completed": completed,
                "total": total,
                "path": path,
                "success": success,
                "freed_so_far": total_freed,
            }

        yield {
            "type": "clean_complete",
            "total_items": total,
            "completed": completed,
            "failed_count": failed_count,
            "total_freed": total_freed,
        }

    @staticmethod
    def _format_size(size):
        """Convert bytes to a human-readable string (B/KB/MB/GB/TB).

        Args:
            size: Size in bytes.

        Returns:
            Formatted string such as ``"1.50 MB"``.
        """
        units = ["B", "KB", "MB", "GB", "TB"]
        value = float(size)
        for unit in units:
            if value < 1024.0:
                return f"{value:.2f} {unit}"
            value /= 1024.0
        return f"{value:.2f} PB"
