"""
后端注册表：定义不同平台+架构可用的下载后端，
提供 CUDA 驱动版本→版本号映射、文件后缀匹配、默认后端选择。
"""
import re

# ── 单个后端描述 ──
# id:        唯一标识，如 "cuda-12.4"
# label:     显示名，如 "NVIDIA CUDA 12.4"
# suffix:    文件后缀，如 "-win-cuda-12.4-x64.zip"
# cudart:    伴生 CUDA 运行时后缀（如 "-cuda-12.4-x64"），None 表示无
# auto_detect: 检测优先级（0=无, 1=fallback, 5=推荐, 9=精确匹配）

BackendInfo = dict  # type alias

# ── CUDA 驱动版本 → CUDA 工具包版本映射 ──
# 来源: https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html
CUDA_VERSION_MAP: list[tuple[str, str]] = [
    ("555",  "13.1"),   # R555+ → CUDA 13.1
    ("545",  "12.6"),
    ("535",  "12.5"),
    ("530",  "12.4"),   # R530+ → CUDA 12.4
    ("520",  "12.2"),
    ("515",  "11.8"),
    ("510",  "11.7"),
    ("495",  "11.5"),
    ("470",  "11.4"),
    ("465",  "11.3"),
    ("460",  "11.2"),
    ("455",  "11.1"),
    ("450",  "11.0"),
]


def detect_cuda_version(driver_ver: str) -> str:
    """根据 NVIDIA 驱动版本字符串返回推荐 CUDA 版本号。"""
    major = driver_ver.split(".")[0] if "." in driver_ver else driver_ver
    for prefix, cuda_ver in CUDA_VERSION_MAP:
        if major >= prefix:
            return cuda_ver
    return "12.4"


# ═══════════════════════════════════════════════
#  平台 → 可用后端列表
# ═══════════════════════════════════════════════

# Windows x64
WIN_X64_BACKENDS: list[BackendInfo] = [
    {"id": "cuda-12.4",  "label": "NVIDIA CUDA 12.4",  "suffix": "-win-cuda-12.4-x64",   "cudart_suffix": "-win-cuda-12.4-x64",   "detect_prio": 9},
    {"id": "cuda-13.1",  "label": "NVIDIA CUDA 13.1",  "suffix": "-win-cuda-13.1-x64",   "cudart_suffix": "-win-cuda-13.1-x64",   "detect_prio": 9},
    {"id": "hip-radeon", "label": "AMD Radeon HIP",    "suffix": "-win-hip-radeon-x64",  "cudart_suffix": None,                "detect_prio": 5},
    {"id": "vulkan",     "label": "Vulkan (通用)",     "suffix": "-win-vulkan-x64",      "cudart_suffix": None,                "detect_prio": 3},
    {"id": "sycl",       "label": "Intel SYCL",        "suffix": "-win-sycl-x64",        "cudart_suffix": None,                "detect_prio": 1},
    {"id": "cpu",        "label": "CPU 通用",          "suffix": "-win-cpu-x64",         "cudart_suffix": None,                "detect_prio": 0},
]

# Windows ARM64
WIN_ARM64_BACKENDS: list[BackendInfo] = [
    {"id": "cpu-arm64",      "label": "CPU (ARM64)",            "suffix": "-win-cpu-arm64",              "cudart_suffix": None, "detect_prio": 5},
    {"id": "opencl-adreno",  "label": "OpenCL Adreno (ARM64)",  "suffix": "-win-opencl-adreno-arm64",    "cudart_suffix": None, "detect_prio": 3},
]

# Linux x64
LINUX_X64_BACKENDS: list[BackendInfo] = [
    {"id": "cuda-12.4",  "label": "NVIDIA CUDA 12.4",    "suffix": "-ubuntu-cuda-12.4-x64",     "cudart_suffix": None, "detect_prio": 9},
    {"id": "cuda-13.1",  "label": "NVIDIA CUDA 13.1",    "suffix": "-ubuntu-cuda-13.1-x64",     "cudart_suffix": None, "detect_prio": 9},
    {"id": "rocm-7.2",   "label": "AMD ROCm 7.2",        "suffix": "-ubuntu-rocm-7.2-x64",      "cudart_suffix": None, "detect_prio": 5},
    {"id": "vulkan",     "label": "Vulkan (通用)",       "suffix": "-ubuntu-vulkan-x64",        "cudart_suffix": None, "detect_prio": 3},
    {"id": "sycl-fp16",  "label": "Intel SYCL FP16",     "suffix": "-ubuntu-sycl-fp16-x64",     "cudart_suffix": None, "detect_prio": 1},
    {"id": "sycl-fp32",  "label": "Intel SYCL FP32",     "suffix": "-ubuntu-sycl-fp32-x64",     "cudart_suffix": None, "detect_prio": 1},
    {"id": "openvino",   "label": "Intel OpenVINO",      "suffix": "-ubuntu-openvino-2026.0-x64","cudart_suffix": None, "detect_prio": 1},
    {"id": "cpu",        "label": "CPU 通用 (Ubuntu)",   "suffix": "-ubuntu-x64",               "cudart_suffix": None, "detect_prio": 0},
]

# Linux ARM64
LINUX_ARM64_BACKENDS: list[BackendInfo] = [
    {"id": "cpu-arm64",    "label": "CPU (Ubuntu ARM64)", "suffix": "-ubuntu-arm64",         "cudart_suffix": None, "detect_prio": 5},
    {"id": "vulkan-arm64", "label": "Vulkan (ARM64)",     "suffix": "-ubuntu-vulkan-arm64",  "cudart_suffix": None, "detect_prio": 3},
    {"id": "310p-arm64",   "label": "310p openEuler",     "suffix": "-310p-openEuler-aarch64","cudart_suffix": None, "detect_prio": 1},
]

# macOS
MACOS_ARM64_BACKENDS: list[BackendInfo] = [
    {"id": "macos-arm64",  "label": "macOS ARM64",      "suffix": "-macos-arm64",      "cudart_suffix": None, "detect_prio": 9},
    {"id": "kleidiai",     "label": "macOS ARM64 KleidiAI", "suffix": "-macos-arm64-kleidiai", "cudart_suffix": None, "detect_prio": 8},
]
MACOS_X64_BACKENDS: list[BackendInfo] = [
    {"id": "macos-x64", "label": "macOS x64", "suffix": "-macos-x64", "cudart_suffix": None, "detect_prio": 9},
]


# ── 获取当前系统所有可用后端列表 ──

def get_backends_for_platform(os_name: str, arch: str) -> list[BackendInfo]:
    """根据操作系统和架构返回所有可能的后端列表。"""
    if os_name == "win32":
        if "arm64" in arch.lower() or "aarch64" in arch.lower():
            return WIN_ARM64_BACKENDS
        return WIN_X64_BACKENDS
    elif os_name in ("linux", "linux2"):
        if "arm64" in arch.lower() or "aarch64" in arch.lower():
            return LINUX_ARM64_BACKENDS
        return LINUX_X64_BACKENDS
    elif os_name == "darwin":
        if "arm64" in arch.lower() or "aarch64" in arch.lower():
            return MACOS_ARM64_BACKENDS
        return MACOS_X64_BACKENDS
    return WIN_X64_BACKENDS  # fallback


# ── 构建匹配 Release 文件名的 regex ──

def make_asset_pattern(suffix: str, platform: str = "") -> re.Pattern:
    """根据后端 suffix 构建匹配压缩包文件名的正则。
    platform 参数限定扩展名：Windows 只匹配 .zip，Linux/macOS 只匹配 .tar.gz。"""
    escaped = re.escape(suffix)
    if platform == "win32":
        ext = "zip"
    elif platform in ("linux", "linux2", "darwin"):
        ext = r"tar\.gz"
    else:
        ext = r"zip|tar\.gz"  # fallback
    return re.compile(rf"llama-b\d+-bin{escaped}\.{ext}$", re.I)


def make_cudart_pattern(suffix: str) -> re.Pattern:
    """根据后端 cudart_suffix 构建匹配 cudart 文件的 regex。"""
    if not suffix:
        return re.compile(r"(?!)")  # 永不匹配
    escaped = re.escape(suffix)
    return re.compile(rf"cudart-llama-bin{escaped}\.zip$", re.I)
