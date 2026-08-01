"""
PySide6 启动线程：在后台运行 llama.cpp 进程并捕获输出。
"""
import os
import sys
import subprocess
import threading

from PySide6.QtCore import QThread, Signal, QTimer

from .platform import CREATE_NO_WINDOW


class LaunchThread(QThread):
    output_signal   = Signal(str)
    finished_signal = Signal(int)
    error_signal    = Signal(str)

    def __init__(self, args: list, cwd: str):
        super().__init__()
        self.args       = args
        self.cwd        = cwd
        self._proc      = None
        self._stop_flag = threading.Event()
        self._kill_scheduled = False

    def run(self):
        try:
            popen_kwargs = {
                "cwd": self.cwd,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "stdin": subprocess.PIPE,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "bufsize": 1,
            }
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = CREATE_NO_WINDOW
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                popen_kwargs["startupinfo"] = startupinfo

            self._proc = subprocess.Popen(self.args, **popen_kwargs)

            for line in iter(self._proc.stdout.readline, ""):
                if self._stop_flag.is_set():
                    break
                line = line.rstrip("\n\r")
                if line:
                    self.output_signal.emit(line)

            self._proc.stdout.close()
            rc = self._proc.wait()
            # Windows 退出码可能是无符号 32bit（如 0xC0000005=3221225477），
            # PySide6 Signal(int) 要求有符号 32bit int，需要转换
            if rc > 0x7FFFFFFF:
                rc = rc - 0x100000000
            self.finished_signal.emit(rc)
        except Exception as e:
            if not self._stop_flag.is_set():
                self.error_signal.emit(str(e))

    def stop(self):
        """非阻塞终止：设标志位 + terminate，延迟强杀。"""
        self._stop_flag.set()
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass
            # 使用 QTimer 在主线程延迟强杀
            if not self._kill_scheduled:
                self._kill_scheduled = True
                QTimer.singleShot(3000, self._force_kill_if_needed)

    def _force_kill_if_needed(self):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.kill()
            except Exception:
                pass
        self._kill_scheduled = False

    def send_input(self, text: str):
        if self._proc and self._proc.stdin:
            try:
                self._proc.stdin.write(text + "\n")
                self._proc.stdin.flush()
            except Exception:
                pass
