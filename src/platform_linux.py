"""
Linux 平台特定函数：设备检测、.sh 脚本生成。
"""
import os
import sys
import subprocess


def _open_folder(path: str):
    """Linux 用 xdg-open 打开目录。"""
    subprocess.run(["xdg-open", path])


def _generate_sh_content(cmd_parts: list) -> str:
    """将命令列表转为 .sh 脚本内容。"""
    escaped = []
    for a in cmd_parts:
        if any(c in a for c in (' ', '"', '$', '\\', '&', '|', '<', '>')):
            escaped.append(f'"{a}"')
        else:
            escaped.append(a)
    return "#!/bin/bash\n" + " ".join(escaped) + "\n"


def _save_script(cmd_parts: list, parent_dir: str) -> str:
    """在 parent_dir 下保存 .sh 文件（含可执行权限），返回路径。"""
    sh_path = os.path.join(parent_dir, "launch.sh")
    with open(sh_path, "w", encoding="utf-8") as f:
        f.write(_generate_sh_content(cmd_parts))
    try:
        os.chmod(sh_path, 0o755)
    except Exception:
        pass
    return sh_path
