"""
共享配置模块：路径、QSS 加载、多语言、UI 参数 schema、默认配置。
"""
import os
import sys
import json
import urllib.request
from typing import Any

# ├─ 路径常量
BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR   = os.path.join(BASE_DIR, "assets")
BIN_DIR      = os.path.join(BASE_DIR, "bin")
LOCALES_DIR  = os.path.join(BASE_DIR, "locales")
QSS_DIR      = os.path.join(ASSETS_DIR, "qss")
CONFIG_PATH  = os.path.join(BASE_DIR, "launcher_config.json")
UI_CFG_PATH  = os.path.join(ASSETS_DIR, "ui_config.json")

# ── aria2c 相关常量 ──
_ARIA2C_EXE = os.path.join(ASSETS_DIR, "aria2c.exe")
_ARIA2C_ZIP = os.path.join(ASSETS_DIR, "aria2.zip")
_ARIA2C_ZIP_URL = "https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-64bit-build1.zip"

# ── Release 缓存 ──
RELEASE_CACHE_PATH = os.path.join(ASSETS_DIR, "release_cache.json")
RELEASE_CACHE_TTL = 30 * 60  # Release 缓存有效期（秒）

# ── 平台常量 ──
CREATE_NEW_CONSOLE = 0x00000010  # Windows: 在新控制台窗口中创建进程

# ── UI 常量 ──
MAX_COMBO_ITEMS = 8          # ComboBox 最大显示项数
DEFAULT_ITEM_HEIGHT = 26     # ComboBox 项高度（像素）
REF_WIDTH_FOR_SCALE = 640    # 自适应缩放参考宽度

# 可执行文件名匹配（不分大小写，自动去除 .exe 后缀以兼容 Linux/macOS）
_EXE_SUFFIX = ".exe" if sys.platform == "win32" else ""
_COMMON_BASE_NAMES = [
    "llama-cli",
    "llama-server",
    "llama-llava-cli",
    "llama-minicpmv-cli",
    "llama-gemma3-cli",
    "llama-qwen2vl-cli",
    "llama-mtmd-cli",
]
COMMON_EXES = [f"{n}{_EXE_SUFFIX}" for n in _COMMON_BASE_NAMES]

# 关键可执行文件（用于快速检测）
_KEY_EXE_NAMES = ["llama-cli", "llama-server"]


def find_executables_in_dir(bin_dir: str, search_subdirs: bool = False) -> list[str]:
    """在指定目录中查找 llama 可执行文件。

    Args:
        bin_dir: 要搜索的目录路径
        search_subdirs: 是否递归搜索子目录

    Returns:
        找到的可执行文件名列表（相对于 bin_dir 的路径）
    """
    found = []
    if not bin_dir or not os.path.isdir(bin_dir):
        return found

    # 构建要查找的文件名列表（带后缀和不带后缀）
    target_names = set()
    for name in _KEY_EXE_NAMES:
        target_names.add(f"{name}{_EXE_SUFFIX}")
        target_names.add(name)  # 也尝试无后缀版本（跨平台回退）
    target_names_lower = {n.lower() for n in target_names}

    if search_subdirs:
        for root, _, files in os.walk(bin_dir):
            for f in files:
                if f.lower() in target_names_lower:
                    rel_path = os.path.relpath(os.path.join(root, f), bin_dir)
                    found.append(rel_path)
    else:
        for name in target_names:
            p = os.path.join(bin_dir, name)
            if os.path.isfile(p):
                found.append(name)

    return found


def has_executables(bin_dir: str) -> bool:
    """快速检测目录中是否有关键 llama 可执行文件。"""
    return len(find_executables_in_dir(bin_dir)) > 0

# GitHub Release API
GITHUB_API_URL = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
# 镜像源（国内加速）
MIRROR_BASE_URLS = [
    "https://github.com/ggml-org/llama.cpp/releases/latest/download/",
]

# 代理设置（默认跟随系统代理）
PROXY_HOST = ""
PROXY_PORT = ""


# ── 平台相关常量（按需导入） ──
def _get_opener() -> urllib.request.OpenerDirector:
    """构建支持系统代理的 URL opener。

    未显式配置 PROXY_HOST / PROXY_PORT 时返回默认 opener，
    urllib 会自动读取系统代理（getproxies()），即"跟随系统代理"。
    注意：传入 ProxyHandler({}) 会禁用全部代理，不要这么做。
    """
    if PROXY_HOST and PROXY_PORT:
        proxy = urllib.request.ProxyHandler({
            "http":  f"http://{PROXY_HOST}:{PROXY_PORT}",
            "https": f"https://{PROXY_HOST}:{PROXY_PORT}",
        })
        return urllib.request.build_opener(proxy)
    return urllib.request.build_opener()  # 跟随系统代理（urllib 默认行为）


def get_release_cache_info() -> tuple:
    """读取 Release 缓存文件的 (tag, fetched_at) 摘要，无有效缓存时返回 None。

    仅供 UI 展示缓存状态（如按钮 tooltip），新鲜度判定在下载线程内完成。
    """
    try:
        with open(RELEASE_CACHE_PATH, "r", encoding="utf-8") as f:
            cache = json.load(f)
        tag = cache.get("tag", "")
        fetched_at = cache.get("fetched_at", "")
        if tag and fetched_at:
            return (tag, fetched_at)
    except Exception:
        pass
    return None


def _open_folder(path: str) -> None:
    """用系统文件管理器打开目录。"""
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        import subprocess
        subprocess.run(["open", path])
    else:
        import subprocess
        subprocess.run(["xdg-open", path])


# ── QSS 样式表加载 ──
def _load_qss(name: str) -> str:
    """从 assets/qss/ 目录读取样式表。"""
    p = os.path.join(QSS_DIR, name)
    try:
        with open(p, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


STYLESHEET       = _load_qss("dark_style.qss")
LIGHT_STYLESHEET = _load_qss("light_style.qss")


# ── UI 配置加载 ──
def _load_ui_config() -> dict:
    """从 assets/ui_config.json 加载所有可自定义的显示元素配置。"""
    try:
        with open(UI_CFG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


_UI_CFG: dict = {}

# ── 模块级全局字符串（方便所有文件引用） ──
BTN:         dict = {}
WIN_TITLES:  dict = {}
PH:          dict = {}
UI_LABELS:   dict = {}
MSG:         dict = {}
CONSOLE_COLORS: dict = {}
THEME_COLORS:   dict = {}
EXE_SEARCH:     dict = {}
SPINBOX_ARROW_COLORS: dict = {}
PARAM_LABELS:   dict = {}

# 动态 UI 参数 schema
DYNAMIC_UI_SCHEMA: list = []
# 预定义 UI 段落（运行模式、思考控制、额外参数）
UI_SECTIONS: list = []


def _list_locales() -> list[str]:
    """扫描 locales/ 目录，返回语言代码列表（zh/en/ja 固定顺序，其余按字母序）。"""
    codes = []
    if os.path.isdir(LOCALES_DIR):
        for f in os.listdir(LOCALES_DIR):
            if f.endswith(".json"):
                code = f[:-5]
                codes.append(code)
    codes = sorted(codes)
    _PRIORITY = {"zh": 0, "en": 1, "ja": 2}
    codes.sort(key=lambda c: _PRIORITY.get(c, 99))
    return codes


def _list_locales_with_names() -> list[tuple[str, str]]:
    """返回 [(语言代码, 语言显示名)]，显示名取自各语言包的 locale_name 键。"""
    result = []
    for code in _list_locales():
        loc = _load_locale(code)
        result.append((code, loc.get("locale_name", code)))
    return result


def _load_locale(lang: str) -> dict[str, Any]:
    """加载语言文件，返回 dict（失败时返回空 dict）。"""
    p = os.path.join(LOCALES_DIR, f"{lang}.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _apply_locale_to_globals(lang: str) -> None:
    """将语言文件中的字符串注入模块级变量，同时合并 ui_config 作为后备。
    使用 .clear() + .update() 原地更新，确保已导入模块的引用也同步更新。"""
    global BTN, WIN_TITLES, PH, UI_LABELS, MSG, CONSOLE_COLORS, THEME_COLORS
    global EXE_SEARCH, SPINBOX_ARROW_COLORS, PARAM_LABELS, DYNAMIC_UI_SCHEMA, UI_SECTIONS, _UI_CFG

    _UI_CFG = _load_ui_config()
    loc = _load_locale(lang)

    def _m(section: str):
        # 优先取语言文件，其次 ui_config
        d = {}
        if _UI_CFG and section in _UI_CFG:
            d.update(_UI_CFG[section])
        if section in loc:
            d.update(loc[section])
        return d

    # 按钮文字与提示 —— 展平 dict 为纯字符串（兼容 ui_config 的嵌套 dict 格式）
    btns = _m("按钮文字与提示")
    raw_btns = btns.get("buttons", {})
    BTN.clear()
    for k, v in raw_btns.items():
        BTN[k] = v.get("text", v) if isinstance(v, dict) else v
    # 叠加 locale 中的顶级字符串
    for k, v in btns.items():
        if not k.startswith("_") and k != "buttons" and isinstance(v, str):
            BTN[k] = v

    WIN_TITLES.clear(); WIN_TITLES.update(_m("窗口标题"))
    PH.clear();         PH.update(_m("占位文本"))
    UI_LABELS.clear();  UI_LABELS.update(_m("界面标签"))
    MSG.clear();        MSG.update(_m("消息文本"))
    CONSOLE_COLORS.clear(); CONSOLE_COLORS.update(_m("控制台颜色"))
    THEME_COLORS.clear();   THEME_COLORS.update(_m("主题颜色"))
    EXE_SEARCH.clear();     EXE_SEARCH.update(_m("可执行文件搜索"))
    SPINBOX_ARROW_COLORS.clear(); SPINBOX_ARROW_COLORS.update(_m("SpinBox 箭头颜色"))
    PARAM_LABELS.clear(); PARAM_LABELS.update(_m("参数标签"))

    schema_cfg = _m("参数定义")
    DYNAMIC_UI_SCHEMA.clear()
    DYNAMIC_UI_SCHEMA.extend(schema_cfg.get("schema", []))
    UI_SECTIONS.clear()
    UI_SECTIONS.extend(schema_cfg.get("ui_sections", []))


# ── 默认配置 ──
DEFAULT_CONFIG: dict = {
    "theme":              "dark",
    "lang":               "zh",
    "bin_dir":            BIN_DIR,
    "model_dir":          os.path.join(BASE_DIR, "models"),
    "mmproj":             "",
    "model_draft":        "",
    "last_port":          "8080",
    "is_server_mode":     False,
    "console_mode":       False,
    "global_args":        "",
    "custom_args":        "",
    "think_mode":         "normal",
    "think_budget":       "0",
    "ui_scale":           1.0,
    "font_path":          "",
    "last_model":         "",
    "presets":            {},
    "collapsed_sections": {},
    "only_cpu":           False,
    "auto_scale":         True,
    "mmproj_enable":      False,
    "retry_count":        3,
    "dl_timeout":         300,
}
