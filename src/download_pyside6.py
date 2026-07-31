"""
PySide6 下载模块：Release 下载线程 + 显存检测线程。
"""
import os
import sys
import re
import json
import time
import zipfile
import shutil
import urllib.request
import subprocess
from typing import Optional

from PySide6.QtCore import QThread, Signal

from .config import (
    BASE_DIR, ASSETS_DIR, BIN_DIR, _ARIA2C_EXE, _ARIA2C_ZIP, _ARIA2C_ZIP_URL,
    GITHUB_API_URL, MIRROR_BASE_URLS, PROXY_HOST, PROXY_PORT, _get_opener,
)
from .platform import CREATE_NO_WINDOW, set_opener
from .backends import get_backends_for_platform


class ReleaseDownloadThread(QThread):
    """后台下载线程，支持 asset 列表获取 + 单个文件下载。"""

    assets_signal     = Signal(list)      # 获取到的可用文件列表
    raw_signal        = Signal(str)       # 原始日志行
    status_signal     = Signal(str)       # 状态文本
    progress_signal   = Signal(int, int)  # 当前, 总数
    finished_signal   = Signal(str)       # 下载完成路径
    error_signal      = Signal(str)       # 错误信息

    def __init__(self, bin_dir: str, backend_id: str = "",
                 retry_count: int = 3, timeout: int = 300,
                 parent=None):
        super().__init__(parent)
        self._bin_dir = bin_dir
        self._backend_id = backend_id
        self._retry_count = retry_count
        self._timeout = timeout
        self._target_name = ""
        self._target_url = ""
        self._target_size = 0
        self._cancel_flag = False

    def set_asset(self, name: str, url: str, size: int = 0):
        """设置需要下载的单个 asset。"""
        self._target_name = name
        self._target_url = url
        self._target_size = size

    def cancel(self):
        self._cancel_flag = True

    def run(self):
        if self._target_name and self._target_url:
            self._download_single()
        else:
            self._fetch_assets()

    def _fetch_assets(self):
        """从 GitHub Release API 获取可用 asset 列表（不包含 llava/cli 等单分片）。"""
        import platform as _platform
        from .backends import get_backends_for_platform
        os_name = sys.platform
        arch = _platform.machine().lower()
        try:
            backends = get_backends_for_platform(os_name, arch)
        except Exception:
            backends = []

        if not backends:
            self.error_signal.emit("未找到当前平台的下载配置")
            return

        try:
            url = GITHUB_API_URL
            self.raw_signal.emit(f"正在获取 Release 信息: {url}")
            self.status_signal.emit("获取 Release 信息...")

            opener = _get_opener()
            req = opener.open(url, timeout=self._timeout)
            data = json.loads(req.read().decode("utf-8"))

            tag = data.get("tag_name", "unknown")
            assets_raw = data.get("assets", [])
            self.raw_signal.emit(f"Release: {tag}, 共 {len(assets_raw)} 个文件")

            ext_filter = ".zip" if os_name == "win32" else ".tar.gz"
            available = []
            for a in assets_raw:
                if self._cancel_flag:
                    return
                name = a.get("name", "")
                size_mb = round(a.get("size", 0) / 1048576, 1)
                dl_url = a.get("browser_download_url", "")
                if ext_filter not in name:
                    continue

                matched = False
                matched_label = ""
                for b in backends:
                    # 后端条目用 suffix 字段标识文件特征（如 "-win-cuda-12.4-x64"）
                    if b.get("suffix") and b["suffix"] in name:
                        matched = True
                        matched_label = b.get("label", b.get("id", "?"))
                        break

                if matched:
                    available.append({
                        "name": name,
                        "url": dl_url,
                        "size": size_mb,
                        "backend_label": matched_label,
                    })

            self.assets_signal.emit(sorted(available, key=lambda x: x["name"]))
        except Exception as e:
            self.error_signal.emit(f"获取 Release 失败: {e}")

    def _download_single(self):
        """使用 aria2c 下载单个文件，失败时尝试 urllib 回退。"""
        os.makedirs(self._bin_dir, exist_ok=True)
        dest = os.path.join(self._bin_dir, self._target_name)

        # 尝试 aria2c
        if os.path.isfile(_ARIA2C_EXE):
            try:
                self._download_with_aria2c(dest)
                if os.path.isfile(dest) and os.path.getsize(dest) > 1024:
                    self.finished_signal.emit(dest)
                    return
            except Exception as e:
                self.raw_signal.emit(f"aria2c 下载失败: {e}")
        else:
            self.raw_signal.emit("aria2c 不存在，尝试自动下载...")
            try:
                self._ensure_aria2c()
                self._download_with_aria2c(dest)
                if os.path.isfile(dest) and os.path.getsize(dest) > 1024:
                    self.finished_signal.emit(dest)
                    return
            except Exception as e:
                self.raw_signal.emit(f"aria2c 下载失败: {e}")

        # 回退到 urllib
        self.raw_signal.emit("aria2c 不可用，使用 urllib 回退下载...")
        for attempt in range(1, self._retry_count + 1):
            if self._cancel_flag:
                return
            try:
                self._download_with_urllib(dest)
                if os.path.isfile(dest):
                    self.finished_signal.emit(dest)
                    return
            except Exception as e:
                self.raw_signal.emit(f"urllib 尝试 {attempt}/{self._retry_count} 失败: {e}")
                time.sleep(2)

        self.error_signal.emit(f"所有下载方式均失败: {self._target_name}")

    def _ensure_aria2c(self):
        """从 GitHub 下载 aria2c 到 assets/。"""
        zip_path = _ARIA2C_ZIP
        if not os.path.isfile(zip_path):
            self.raw_signal.emit(f"下载 aria2c: {_ARIA2C_ZIP_URL}")
            urllib.request.urlretrieve(_ARIA2C_ZIP_URL, zip_path)

        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                if name.endswith("aria2c.exe"):
                    with zf.open(name) as src, open(_ARIA2C_EXE, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    os.chmod(_ARIA2C_EXE, 0o755)
                    self.raw_signal.emit(f"aria2c 已解压: {_ARIA2C_EXE}")
                    return
        raise RuntimeError("aria2c.exe 未在 zip 中找到")

    def _download_with_aria2c(self, dest: str):
        """使用 aria2c 下载（支持多源分片加速）。"""
        if self._cancel_flag:
            return
        urls = [self._target_url] + MIRROR_BASE_URLS
        all_src = [u for u in urls if u]
        src_arg = ",".join(all_src)

        cmd = [
            _ARIA2C_EXE,
            "-x", "8", "-s", "8", "-k", "1M",
            "--continue=true",
            "--allow-overwrite=true",
            "--auto-file-renaming=false",
            "--summary-interval=0",
            "--console-log-level=notice",
            "--download-result=hide",
            "-d", os.path.dirname(dest),
            "-o", os.path.basename(dest),
            src_arg,
        ]
        if PROXY_HOST and PROXY_PORT:
            cmd += ["--all-proxy", f"http://{PROXY_HOST}:{PROXY_PORT}"]

        self.raw_signal.emit(f"aria2c 启动: {os.path.basename(dest)}")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            bufsize=1,
        )

        total_size = self._target_size * 1048576 if self._target_size > 0 else 0
        prog_re = re.compile(r"(\d+)%")
        for line in iter(proc.stdout.readline, ""):
            if self._cancel_flag:
                proc.terminate()
                return
            m = prog_re.search(line)
            if m:
                pct = int(m.group(1))
                if total_size > 0:
                    self.progress_signal.emit(int(total_size * pct / 100), total_size)
                self.raw_signal.emit(f"  {pct}%  {os.path.basename(dest)}")
        proc.wait()

    def _download_with_urllib(self, dest: str):
        """使用 urllib 单线程下载（回退方案）。"""
        import urllib.request as ureq
        self.raw_signal.emit(f"urllib 下载: {self._target_name}")

        opener = _get_opener()
        req = opener.open(self._target_url, timeout=self._timeout)
        total = int(req.headers.get("Content-Length", 0))
        downloaded = 0

        with open(dest, "wb") as f:
            while True:
                if self._cancel_flag:
                    f.close()
                    os.remove(dest)
                    return
                chunk = req.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    self.progress_signal.emit(downloaded, total)
                self.raw_signal.emit(f"  {downloaded // 1048576} MiB / {total // 1048576} MiB")

        self.raw_signal.emit(f"urllib 下载完成: {os.path.basename(dest)}")


class VramCheckThread(QThread):
    """后台检测显存信息。"""

    result_signal = Signal(int, int)  # total_mb, free_mb

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total,memory.free",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10,
            )
            line = result.stdout.strip().split("\n")[0]
            parts = line.split(",")
            total = int(parts[0].strip())
            free = int(parts[1].strip())
            self.result_signal.emit(total, free)
        except Exception:
            self.result_signal.emit(0, 0)
