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
import tarfile
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QThread, Signal

from .config import (
    BASE_DIR, ASSETS_DIR, BIN_DIR, _ARIA2C_EXE, _ARIA2C_ZIP, _ARIA2C_ZIP_URL,
    GITHUB_API_URL, MIRROR_BASE_URLS, PROXY_HOST, PROXY_PORT,
    RELEASE_CACHE_PATH, RELEASE_CACHE_TTL, _get_opener,
)
from .platform import CREATE_NO_WINDOW, set_opener
from .backends import get_backends_for_platform, make_asset_pattern, make_cudart_pattern


def filter_release_assets(assets_raw: list, backends: list, os_name: str) -> list:
    """从 GitHub Release 资产列表中过滤出可下载项（纯函数，可脱离 Qt 单测）。

    主包用 make_asset_pattern 精确锚定（llama-b\\d+-bin{suffix}），
    cudart 伴生包用 make_cudart_pattern —— 替代原 suffix 子串匹配：
    - 修复 cudart 包被误当主包的问题（官方命名 cudart-llama-bin-*.zip 含主包 suffix 子串）；
    - 排除 -llava 分片、分卷、无 -bin- 变体等非主包资产。
    返回项含 kind 字段（"main" / "cudart"），按去 cudart- 前缀后的名称排序（伴生包紧跟主包）。
    """
    ext_filter = ".zip" if os_name == "win32" else ".tar.gz"
    # 预编译后端匹配规则（cudart 优先，包名可能同时含主包后缀子串）
    backend_rules = []
    for b in backends:
        label = b.get("label", b.get("id", "?"))
        if b.get("cudart_suffix"):
            backend_rules.append(("cudart", make_cudart_pattern(b["cudart_suffix"]), label))
        if b.get("suffix"):
            backend_rules.append(("main", make_asset_pattern(b["suffix"], os_name), label))

    available = []
    for a in assets_raw:
        name = a.get("name", "")
        if ext_filter not in name:
            continue
        kind = None
        matched_label = ""
        for k, pat, label in backend_rules:
            if pat.match(name):
                kind = k
                matched_label = label
                break
        if kind:
            available.append({
                "name": name,
                "url": a.get("browser_download_url", ""),
                "size": round(a.get("size", 0) / 1048576, 1),
                "backend_label": matched_label,
                "kind": kind,
            })
    return sorted(available, key=lambda x: re.sub(r"^cudart-", "", x["name"]))


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
        self._asset_kind = "main"   # "main"（主包）| "cudart"（CUDA 运行时伴生包）
        self._cancel_flag = False

    def set_asset(self, name: str, url: str, size: int = 0, kind: str = "main"):
        """设置需要下载的单个 asset。kind: main / cudart。"""
        self._target_name = name
        self._target_url = url
        self._target_size = size
        self._asset_kind = kind

    def cancel(self):
        self._cancel_flag = True

    def run(self):
        if self._target_name and self._target_url:
            self._download_single()
        else:
            self._fetch_assets()

    def _fetch_assets(self):
        """获取可用 asset 列表（不包含 llava/cli 等单分片）。

        优先使用本地缓存（30 分钟内有效，见 RELEASE_CACHE_TTL），
        命中时不再请求 GitHub API，避免触发未认证限流。
        """
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

        # ── 缓存命中：直接返回（30 分钟内 + tag + 平台一致） ──
        cache = self._load_release_cache()
        if cache:
            tag = cache.get("tag", "unknown")
            available = cache.get("assets", [])
            self.raw_signal.emit(f"使用缓存 Release: {tag}（{RELEASE_CACHE_TTL // 60} 分钟内有效）")
            self.assets_signal.emit(sorted(available, key=lambda x: x["name"]))
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

            available = filter_release_assets(assets_raw, backends, os_name)
            if self._cancel_flag:
                return
            self._save_release_cache(tag, available)
            self.assets_signal.emit(available)
        except Exception as e:
            self.error_signal.emit(f"获取 Release 失败: {e}")

    # ── Release 缓存 ──

    def _platform_key(self) -> str:
        """缓存平台标识，避免跨平台误用缓存。"""
        import platform as _platform
        return f"{sys.platform}/{_platform.machine().lower()}"

    # 缓存结构版本号：过滤逻辑/字段变化时递增，旧版本缓存一律失效
    CACHE_SCHEMA_VERSION = 2

    def _load_release_cache(self) -> Optional[dict]:
        """读取 Release 缓存；过期 / 平台不符 / 版本不符 / 损坏时返回 None。"""
        try:
            if not os.path.isfile(RELEASE_CACHE_PATH):
                return None
            with open(RELEASE_CACHE_PATH, "r", encoding="utf-8") as f:
                cache = json.load(f)
            if not isinstance(cache, dict) or not cache.get("assets"):
                return None
            if cache.get("v") != self.CACHE_SCHEMA_VERSION:
                return None
                return None
            fetched_at = datetime.fromisoformat(str(cache.get("fetched_at", "")))
            if (datetime.now() - fetched_at).total_seconds() > RELEASE_CACHE_TTL:
                return None
            if cache.get("platform") != self._platform_key():
                return None
            return cache
        except Exception:
            return None

    def _save_release_cache(self, tag: str, available: list) -> None:
        """写入 Release 缓存：版本 / fetched_at / tag / 平台 / 过滤后的可用列表。"""
        try:
            cache = {
                "v": self.CACHE_SCHEMA_VERSION,
                "fetched_at": datetime.now().isoformat(timespec="seconds"),
                "tag": tag,
                "platform": self._platform_key(),
                "assets": available,
            }
            with open(RELEASE_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.raw_signal.emit(f"Release 缓存写入失败: {e}")

    def _download_single(self):
        """使用 aria2c 下载单个文件，失败时尝试 urllib 回退；下载成功后自动解压。"""
        os.makedirs(self._bin_dir, exist_ok=True)
        dest = os.path.join(self._bin_dir, self._target_name)

        # 尝试 aria2c（不存在时自动下载）
        if os.path.isfile(_ARIA2C_EXE):
            try:
                self._download_with_aria2c(dest)
            except Exception as e:
                self.raw_signal.emit(f"aria2c 下载失败: {e}")
        else:
            self.raw_signal.emit("aria2c 不存在，尝试自动下载...")
            try:
                self._ensure_aria2c()
                self._download_with_aria2c(dest)
            except Exception as e:
                self.raw_signal.emit(f"aria2c 下载失败: {e}")

        # aria2c 下载成功 → 解压收尾
        if os.path.isfile(dest) and os.path.getsize(dest) > 1024:
            self._finish_download(dest)
            return

        # 回退到 urllib
        self.raw_signal.emit("aria2c 不可用，使用 urllib 回退下载...")
        for attempt in range(1, self._retry_count + 1):
            if self._cancel_flag:
                return
            try:
                self._download_with_urllib(dest)
                if os.path.isfile(dest):
                    self._finish_download(dest)
                    return
            except Exception as e:
                self.raw_signal.emit(f"urllib 尝试 {attempt}/{self._retry_count} 失败: {e}")
                time.sleep(2)

        self.error_signal.emit(f"所有下载方式均失败: {self._target_name}")

    # ── 下载收尾：解压 + 验证 ──

    def _finish_download(self, dest: str):
        """下载完成后的收尾流程：解压压缩包 → 验证产物 → 清理压缩包。

        解压或验证失败时发送 error_signal，成功才发送 finished_signal。
        产物验证基于本次解压出的文件列表，不受 bin 目录旧文件影响；
        cudart 伴生包按 CUDA 运行时 DLL（cudart64_* / cublas*）验证，主包按 llama-* 验证。
        """
        try:
            extracted = self._extract_archive(dest)
        except Exception as e:
            self.error_signal.emit(f"解压失败: {e}")
            return

        if self._asset_kind == "cudart":
            # 伴生包：验证 CUDA 运行时 DLL
            found = sorted(n for n in extracted
                           if n.lower().startswith(("cudart64_", "cublas")))
            if not found:
                self.error_signal.emit(
                    f"解压完成但未找到 CUDA 运行时 DLL，请检查目录: {self._bin_dir}")
                return
            self.raw_signal.emit(f"CUDA 运行时解压完成，已检测到: {', '.join(found)}")
        else:
            # 主包：验证 llama 可执行文件（兼容包内嵌套目录）
            found = sorted(n for n in extracted if n.lower().startswith("llama-"))
            if not found:
                self.error_signal.emit(
                    f"解压完成但未找到 llama 可执行文件，请检查目录: {self._bin_dir}")
                return
            self.raw_signal.emit(f"解压完成，已检测到: {', '.join(found)}")
        self.finished_signal.emit(dest)

    def _extract_archive(self, dest: str) -> list:
        """解压 .zip / .tar.gz 到 bin 目录，成功后删除压缩包原文件。

        带 zip-slip 路径穿越防护：成员路径归一化后必须位于 bin 目录内。
        返回本次解压出的文件 basename 列表（供产物验证）。
        """
        if not os.path.isfile(dest):
            return []
        extracted = []
        name = self._target_name.lower()
        if name.endswith(".zip"):
            self.status_signal.emit(f"正在解压: {self._target_name}")
            with zipfile.ZipFile(dest, "r") as zf:
                for member in zf.infolist():
                    if self._cancel_flag:
                        return []
                    extracted += self._safe_extract_zip_member(zf, member)
        elif name.endswith(".tar.gz") or name.endswith(".tgz"):
            self.status_signal.emit(f"正在解压: {self._target_name}")
            with tarfile.open(dest, "r:gz") as tf:
                for member in tf.getmembers():
                    if self._cancel_flag:
                        return []
                    extracted += self._safe_extract_tar_member(tf, member)
        else:
            # 非压缩包（正常流程不会出现），视为解压失败
            raise ValueError(f"未知文件格式: {self._target_name}")

        # 解压成功，删除压缩包，避免占用空间
        try:
            os.remove(dest)
            self.raw_signal.emit(f"已删除压缩包: {self._target_name}")
        except Exception:
            pass
        return extracted

    def _check_zip_slip(self, member_path: str) -> str:
        """校验压缩成员路径，拒绝 ../ 等路径穿越（zip-slip），返回安全目标路径。"""
        target = os.path.normpath(os.path.join(self._bin_dir, member_path))
        if not (target.startswith(self._bin_dir + os.sep) or target == self._bin_dir):
            raise ValueError(f"非法解压路径: {member_path}")
        return target

    def _safe_extract_zip_member(self, zf: zipfile.ZipFile, member: zipfile.ZipInfo) -> list:
        """安全解压单个 zip 成员（流式复制，避免 zip-slip 与符号链接逃逸）。

        返回解压出的文件 basename 列表（目录成员返回空）。
        """
        target = self._check_zip_slip(member.filename)
        if member.is_dir():
            os.makedirs(target, exist_ok=True)
            return []
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with zf.open(member) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
        return [os.path.basename(target)]

    def _safe_extract_tar_member(self, tf: tarfile.TarFile, member: tarfile.TarInfo) -> list:
        """安全解压单个 tar 成员；跳过符号/硬链接，保留可执行权限。

        返回解压出的文件 basename 列表（目录/链接成员返回空）。
        """
        target = self._check_zip_slip(member.name)
        if member.isdir():
            os.makedirs(target, exist_ok=True)
            return []
        if not member.isfile():
            return []  # 跳过 symlink / hardlink / 设备文件
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with tf.extractfile(member) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
        # Linux 下保留可执行权限（tar 包内 mode 含可执行位）
        try:
            os.chmod(target, member.mode)
        except Exception:
            pass
        return [os.path.basename(target)]

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
