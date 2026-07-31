"""
平台自动调度：根据 sys.platform 导入 Windows/Linux 特定函数。
"""
import sys

if sys.platform == "win32":
    from .platform_win import (
        CREATE_NO_WINDOW,
        set_opener,
        _open_folder,
        _generate_bat_content,
        _save_script,
    )
else:
    from .platform_linux import (
        _open_folder,
        _generate_sh_content,
        _save_script,
    )
    # Linux 无 CREATE_NO_WINDOW
    CREATE_NO_WINDOW = 0
    def set_opener(opener):
        pass


# 统一导出
open_folder = _open_folder
save_script = _save_script
