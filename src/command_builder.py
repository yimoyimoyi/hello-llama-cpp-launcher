"""
命令构建与参数校验 —— 无 Qt 依赖的纯函数模块。

职责：根据收集到的配置（LaunchConfig）与 UI 参数 schema 构建 llama.cpp 启动命令，
并对用户输入参数做白名单校验与 MSVCRT 语义拆分。可脱离 GUI 直接单元测试。

错误处理约定：build_command_args() 返回 (args, errors)。
- fatal 错误（no_model/no_exe/model_missing/invalid_*）：立即中断，args 为 None；
- warning 错误（warn_*）：不中断，args 照常返回。
调用方（UI 层）根据 code 映射到本地化消息并弹出对话框。
"""
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

from .config import COMMON_EXES


@dataclass
class LaunchConfig:
    """UI 侧收集的启动配置（Qt 取值在调用方完成，本模块不感知控件）。"""
    model_rel_path: str = ""        # 相对模型目录的路径；"" 表示未选择
    model_display: str = ""         # 下拉框显示名（错误提示用）
    is_server: bool = False
    exe_path: str = ""              # find_executable 的结果
    model_dir: str = ""
    dynamic_values: dict = field(default_factory=dict)  # pid → int/float/str/bool
    think_mode: str = "normal"
    port: str = ""
    think_budget: str = ""
    mmproj: str = ""
    mmproj_enabled: bool = False
    model_draft: str = ""
    draft_enabled: bool = False
    global_args: str = ""
    custom_args: str = ""


@dataclass
class BuildError:
    """结构化构建错误/警告，code 由 UI 层映射为本地化消息。"""
    code: str      # no_model / no_exe / model_missing / invalid_param / invalid_port
                   # / invalid_budget / invalid_global_args / invalid_custom_args
                   # / warn_mmproj / warn_model_draft
    detail: str = ""   # 具体参数名 / token / 路径


# ═══════════════════════════════════════════════
#  可执行文件查找
# ═══════════════════════════════════════════════

def find_executable(bin_dir: str, base_dir: str, is_server: bool = False) -> tuple:
    """三段查找 llama 可执行文件。

    1. bin_dir 内精确匹配目标（llama-server / llama-cli）
    2. bin_dir 内遍历 COMMON_EXES
    3. base_dir 递归兜底（命中时返回所在目录，供调用方回写 bin_dir 配置）

    Returns:
        (exe_path, found_root_dir) —— found_root 非 None 表示第三段兜底命中
    """
    _exe_suffix = ".exe" if sys.platform == "win32" else ""
    target = f"llama-server{_exe_suffix}" if is_server else f"llama-cli{_exe_suffix}"
    target_lower = target.lower()
    bin_dir = os.path.abspath(bin_dir)
    if os.path.isdir(bin_dir):
        p = os.path.join(bin_dir, target)
        if os.path.isfile(p):
            return p, None
        for exe in COMMON_EXES:
            p = os.path.join(bin_dir, exe)
            if os.path.isfile(p):
                return p, None
    all_lower = [x.lower() for x in COMMON_EXES]
    for root, _, files in os.walk(base_dir):
        for f in files:
            fl = f.lower()
            if fl == target_lower or fl in all_lower:
                return os.path.join(root, f), root
    return None, None


# ═══════════════════════════════════════════════
#  参数校验（T09：白名单 + 控制字符拒收）
# ═══════════════════════════════════════════════

# 白名单字符集：\w（字母数字下划线）+ 参数常用标点 + 引号 + 空格。
# 放行 {}（prompt 模板/grammar）、<> 与 |（ChatML 特殊 token <|im_start|> 等）、
# ()（模型文件名常见）、%（路径/占位）、:（盘符）、\ /（路径）、= - .（参数与取值）。
# 拒绝 ; & $ ` （bat/sh 落盘注入面）与控制字符。
SAFE_PRINTABLE = re.compile(r"^[\w\-=:/.\\{}%+,@#()\[\]!?~'\"<>| ]+$")


def validate_arg(arg: str) -> bool:
    """校验单个参数 token 是否安全（白名单 + 无控制字符）。"""
    if any(ord(c) < 32 for c in arg):
        return False
    return bool(SAFE_PRINTABLE.match(arg))


def validate_port(port_str: str) -> bool:
    try:
        port = int(port_str)
        return 1 <= port <= 65535
    except (ValueError, TypeError):
        return False


def validate_number(value: str, allow_negative: bool = False) -> bool:
    try:
        num = float(value)
        return allow_negative or num >= 0
    except (ValueError, TypeError):
        return False


# ═══════════════════════════════════════════════
#  参数拆分（T09：MSVCRT / CommandLineToArgvW 语义）
# ═══════════════════════════════════════════════

def split_args(s: str) -> list:
    """按 Windows CommandLineToArgvW 规则拆分参数（subprocess.list2cmdline 的真逆）。

    - 空格/制表符在引号外为分隔符，引号内原样保留；
    - 双引号切换引号状态并被移除；单引号视为普通字符（cmd 语义）；
    - 反斜杠按 MSVCRT 规则：仅当后随引号时参与转义（奇数个 `\\` 转义引号，
      偶数个为字面量），其余情况全部字面量 —— Windows 路径 `C:\\models\\x` 不被吞；
    - `--key=value` 等号非分隔符；未闭合引号取到串尾。
    """
    r = []
    cur = []
    in_q = False
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == '"':
            in_q = not in_q
            i += 1
        elif c == "\\":
            # 统计连续反斜杠
            j = i
            while j < n and s[j] == "\\":
                j += 1
            back = j - i
            if j < n and s[j] == '"':
                # 后随引号：偶数个为字面量，奇数个额外转义一个引号（不切换状态）
                cur.append("\\" * (back // 2))
                if back % 2 == 1:
                    cur.append('"')
                i = j + 1
            else:
                cur.append("\\" * back)
                i = j
        elif (c == " " or c == "\t") and not in_q:
            if cur:
                r.append("".join(cur))
                cur = []
            i += 1
        else:
            cur.append(c)
            i += 1
    if cur:
        r.append("".join(cur))
    return r


# ═══════════════════════════════════════════════
#  命令构建
# ═══════════════════════════════════════════════

def _param_value_str(val, ptype: str) -> Optional[str]:
    """将收集到的控件值转成命令行字符串；应跳过（空/零）时返回 None。

    与原 UI 行为保持一致：string/combo 空跳过；int/float 为 0 跳过。
    """
    if ptype in ("int", "float"):
        if val in (None, 0):
            return None
        return str(val)
    if val is None:
        return None
    val = str(val).strip()
    return val or None


def build_command_args(cfg: LaunchConfig, schema: list) -> tuple:
    """根据 LaunchConfig 与参数 schema 构建启动命令。

    Args:
        cfg: UI 侧收集的配置
        schema: DYNAMIC_UI_SCHEMA（list，元素含 "params": [{id,arg,type,...}]）

    Returns:
        (args, errors)：fatal 错误出现时 args 为 None；warn_* 不中断。
    """
    args = [cfg.exe_path, "-m", os.path.abspath(os.path.normpath(
        os.path.join(cfg.model_dir, cfg.model_rel_path)))]

    current_spec_type = str(cfg.dynamic_values.get("spec_type", "")).strip()

    for group in schema:
        for param in group["params"]:
            pid = param["id"]
            ptype = param.get("type", "string")

            # spec_type 门控：投机解码相关参数仅在对应模式下传参
            if pid == "spec_draft_n_max" and not current_spec_type.startswith("draft-"):
                continue
            if pid.startswith("spec_ngram_") and not current_spec_type.startswith("ngram-"):
                continue

            val = cfg.dynamic_values.get(pid)
            if ptype in ("check", "bool"):
                if not val:
                    continue
                if ptype == "check":
                    args.extend([param["arg"], param.get("checked_val", "on")])
                else:
                    bv = param.get("bool_val")
                    if bv:
                        args.extend([param["arg"], bv])
                    else:
                        args.append(param["arg"])
                continue

            # combo 特殊值：spec_type="none" 表示不启用投机解码
            if pid == "spec_type" and str(val or "").strip() == "none":
                continue

            sval = _param_value_str(val, ptype)
            if sval is None:
                continue
            # 仅文本型参数（string/combo）需要白名单校验（数值型已由 SpinBox range 约束）
            if ptype in ("string", "combo") and not validate_arg(sval):
                return None, [BuildError("invalid_param", pid)]
            args.extend([param["arg"], sval])

    if cfg.is_server:
        if not validate_port(cfg.port):
            return None, [BuildError("invalid_port")]
        args += ["--port", cfg.port]
    else:
        args += ["--color", "on", "-cnv"]

    mode = cfg.think_mode
    budget = cfg.think_budget.strip()
    if budget and not validate_number(budget, allow_negative=False):
        return None, [BuildError("invalid_budget")]
    if mode == "normal":
        args += ["--reasoning", "on"]
        if budget and budget != "0":
            args += ["--reasoning-budget", budget]
    elif mode == "hide":
        args += ["--reasoning-format", "none", "--reasoning-budget", "0", "-rea", "off"]
    elif mode == "stop":
        args += ["--reasoning-format", "none", "-r", "</think>",
                 "--reasoning-budget", budget or "0"]

    warnings = []
    if cfg.mmproj and cfg.mmproj_enabled:
        if os.path.exists(cfg.mmproj):
            args += ["--mmproj", os.path.normpath(cfg.mmproj)]
        else:
            warnings.append(BuildError("warn_mmproj", cfg.mmproj))

    if cfg.model_draft and cfg.draft_enabled and current_spec_type.startswith("draft-"):
        if os.path.exists(cfg.model_draft):
            args += ["--model-draft", os.path.normpath(cfg.model_draft)]
        else:
            warnings.append(BuildError("warn_model_draft", cfg.model_draft))

    for raw, err_code in ((cfg.global_args, "invalid_global_args"),
                          (cfg.custom_args, "invalid_custom_args")):
        if not raw.strip():
            continue
        parts = split_args(raw.strip())
        for part in parts:
            if not validate_arg(part):
                return None, [BuildError(err_code, part[:50])]
        args += parts

    return args, warnings
