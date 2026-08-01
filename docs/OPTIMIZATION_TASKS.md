# Llama.cpp 图形启动器 — 优化任务文档

> 本文档基于对项目源码的完整审查（`main.py` / `src/*.py` / `assets/ui_config.json`）生成，
> 列出了后续优化方向、优先级、工作量评估与实现建议，可作为后续开发排期的工作清单。

---

## 一、优化项总览

| 编号 | 优先级 | 类别 | 优化项 | 预估工作量 |
|------|--------|------|--------|-----------|
| T01 | 🔴 P0 | 功能缺陷 | 下载完成后自动解压到 Bin 目录 | 小 |
| T02 | 🔴 P0 | 功能缺陷 | 代理恢复"跟随系统代理" | 小 |
| T03 | 🔴 P0 | 功能缺陷 | 实现 Release 30 分钟缓存 | 小 |
| T04 | 🟠 P1 | 功能缺陷 | 下发 CUDA cudart 伴生包 | 中 |
| T05 | 🟠 P1 | 架构 | 拆分 main.py（1982 行） | 中 |
| T06 | 🟠 P1 | 架构 | 移除 `_pyside6` 历史后缀命名 | 小 |
| T07 | 🟠 P1 | 架构 | 信号 Lambda 链改为具名回调 | 小 |
| T08 | 🟠 P1 | 架构 | 移除 `CollapsibleSection._toggle` monkey-patch | 小 |
| T09 | 🟠 P1 | 健壮性 | 参数解析改用 shlex / 白名单校验 | 中 |
| T10 | 🟠 P1 | 健壮性 | 控制台输出 HTML 转义与性能 | 中 |
| T11 | 🟡 P2 | 测试 | 补 pytest 单元测试（纯逻辑模块） | 中 |
| T12 | 🟡 P2 | 工程化 | GitHub Actions CI | 中 |
| T13 | 🟡 P2 | 工程化 | PyInstaller 打包分发 | 中 |
| T14 | 🟢 P3 | 体验 | 切换语言时保留未保存输入 | 中 |
| T15 | 🟢 P3 | 体验 | 模型搜索 / 文件大小 / 量化类型展示 | 中 |
| T16 | 🟢 P3 | 体验 | 下载历史版本（Release tag 选择） | 较大 |
| T17 | 🟢 P3 | 健壮性 | VRAM 检测支持 AMD / Intel | 小 |
| T18 | 🟢 P3 | 工程化 | 应用版本检查 / 自动更新提示 | 中 |
| T19 | 🟢 P3 | 健壮性 | 配置异常恢复（不再静默吞异常） | 小 |
| T20 | 🟢 P3 | 清理 | 删除死代码（make_asset_pattern 等） | 小 |

---

## 二、P0 — 关键功能缺陷（优先修复）

### T01 下载完成后自动解压到 Bin 目录

**现状**：
`src/download.py::ReleaseDownloadThread._download_single()` 只把 `.zip` / `.tar.gz` 下载到 `bin_dir`，随后立即发送 `finished_signal`。整个代码库中 `zipfile` / `tarfile` 仅用于解压 aria2c 自身，**没有任何针对 llama.cpp 压缩包的解压逻辑**。

**影响**：
- README 声称"下载完成后自动解压到 Bin 目录并刷新检测"，实际不成立。
- 用户下载后 Bin 目录内是压缩包而非可执行文件，点击启动报"找不到可执行文件"。
- 核心功能链路断裂，属于最高优先级 Bug。

**建议方案**：
1. 在 `_download_single()` 成功下载后追加解压步骤：
   - `.zip` → `zipfile.ZipFile(...).extractall(bin_dir)`
   - `.tar.gz` → `tarfile.open(...).extractall(bin_dir)`
2. 解压成功后**删除压缩包原文件**，避免占用空间和干扰 `find_executables_in_dir()`。
3. 发送 `finished_signal` 前先验证解压产物中存在 `llama-cli` / `llama-server`，失败时发 `error_signal`。
4. 新增 `progress_signal` 阶段提示（下载 0-70% → 解压 70-100%）或设置界面提示文字。
5. 注意 zip-slip 安全：解压时校验成员路径，防止 `../../` 路径穿越写入 Bin 目录之外。

**验证**：
- Windows 下载 `-win-cuda-12.4-x64.zip` 后 `bin/` 内出现 `llama-cli.exe` / `llama-server.exe`。
- Linux 下载 `-ubuntu-vulkan-x64.tar.gz` 后出现可执行文件且带可执行权限（`chmod`）。

---

### T02 代理恢复"跟随系统代理"

**现状**：
`src/config.py::_get_opener()`:
```python
def _get_opener() -> urllib.request.OpenerDirector:
    if PROXY_HOST and PROXY_PORT:
        ...
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))
```
`ProxyHandler({})` 传入空 dict 表示**禁用全部代理**，并非"跟随系统代理"。

**影响**：
- 国内用户访问 GitHub API / Release 下载时无法使用系统代理，大概率超时或失败，体验极差。
- README 常见问题"下载速度慢？"给出的"设置 PROXY_HOST/PROXY_PORT 即可"方案需要改代码，不是配置化。

**建议方案**：
```python
def _get_opener() -> urllib.request.OpenerDirector:
    if PROXY_HOST and PROXY_PORT:
        proxy = urllib.request.ProxyHandler({
            "http":  f"http://{PROXY_HOST}:{PROXY_PORT}",
            "https": f"https://{PROXY_HOST}:{PROXY_PORT}",
        })
        return urllib.request.build_opener(proxy)
    # 跟随系统代理（urllib 默认行为）
    return urllib.request.build_opener()   # 不传 ProxyHandler 即自动读 getproxies()
```
如仍需显式控制，可用 `urllib.request.getproxies()` 传入。

**验证**：
- 系统开启代理时，不设置 `PROXY_HOST` 也能下载成功（抓包确认走了代理）。
- 无代理环境下行为不变。

---

### T03 实现 Release 30 分钟缓存

**现状**：
`RELEASE_CACHE_PATH = assets/release_cache.json` 已在 `config.py` 定义且 README 宣称"首次 30 分钟内使用缓存"，但 `_fetch_assets()` 每次都直接请求 `https://api.github.com/repos/ggml-org/llama.cpp/releases/latest`，**从未读写缓存文件**。

**影响**：
- GitHub API 未认证限流 60 次/小时，多次点击"获取可用文件"会触发 `403 API rate limit exceeded`。
- 每次打开都等待网络往返，启动感知卡顿。

**建议方案**：
1. 新增 `_load_release_cache()` / `_save_release_cache()` 方法，缓存结构：
   ```json
   {
     "fetched_at": "2026-08-01T12:00:00+08:00",
     "tag": "b5678",
     "assets": [ ... ]
   }
   ```
2. `_fetch_assets()` 开头先检查缓存：`now - fetched_at < 30 分钟` 且 tag 匹配则直接 emit `assets_signal`。
3. 缓存失效或不存在时才请求 API；请求成功后写回缓存。
4. 在设置页按钮 tooltip 中显示"缓存于 xx:xx，点击强制刷新"。

**验证**：
- 连续两次点击"获取可用文件"，第二次不再产生网络请求（可断网验证）。
- 修改 `assets/release_cache.json` 的 `fetched_at` 为 1 小时前，确认触发重新拉取。

---

## 三、P1 — 功能补全与架构优化

### T04 下发 CUDA cudart 伴生包

**现状**：
`src/backends.py` 中 CUDA 12.4 / 13.1 后端定义了 `cudart_suffix`（如 `-win-cuda-12.4-x64`），`make_cudart_pattern()` 也能生成匹配正则，但 `_fetch_assets()` 的匹配逻辑只判断 `b["suffix"] in name` 来识别主压缩包，**cudart 伴生包从未被识别为可下载项**。

**影响**：
- 部分 CUDA 构建发布为"主包 + cudart 伴生包"结构，缺少 cudart 会导致 `cudart64_*.dll` 缺失、启动即报错。
- 用户无法从界面获取这批运行时文件，只能手动下载。

**建议方案**：
1. `_fetch_assets()` 中当 asset 匹配 `cudart_suffix` 时，将其标注为伴生 item（如 `label: "NVIDIA CUDA 12.4 (cudart 运行时)"`）。
2. 下载流程支持"先下载主包 → 解压 → 再下载 cudart → 合并解压到同一 bin"的顺序执行。
3. 或将 cudart 作为主包下载完成后的自动补充下载（二进制存在但启动失败时提示）。

---

### T05 拆分 main.py（1982 行）

**现状**：
`LlamaProLauncher` 单一类承载 20+ 职责：UI 构建、配置读写、下载编排、进程管理、预设管理、字体缩放、窗口几何恢复、命令构建、参数校验、多语言切换等。`build_command_args()` / `_validate_arg()` / `_split_args()` 等纯逻辑方法深埋其中。

**建议拆分**：

| 新模块 | 职责 | 从 main.py 迁出的方法 |
|--------|------|----------------------|
| `src/config_store.py` | 配置读写 + 类型强制 + 预设 CRUD | `load_settings` / `save_settings` / `save_current_preset` / `delete_current_preset` / `_load_widget_from_state` / `_reset_widget_to_default` |
| `src/command_builder.py` | 纯逻辑命令构建与校验 | `build_command_args` / `find_executable` / `_validate_arg` / `_validate_port` / `_validate_number` / `_split_args` |
| `src/ui_builder.py` | 主界面 / 参数页 / 设置页构建 | `build_ui` / `_build_params_tab` / `_build_settings_tab` / `_build_ui_sections` / `_mk_section` |
| `src/theme.py`（可选） | 主题 / 缩放 / 字体 | `_scale_stylesheet` / `_inject_custom_font_into_sheet` / `_apply_full_stylesheet` / `_apply_font_scale` / `_load_custom_font` |

`command_builder.py` 应设计为**无 Qt 依赖的纯 Python 类/函数**（用 `dataclass` 传参），这样可脱离 GUI 做单元测试。

---

### T06 移除 `_pyside6` 历史后缀命名

**现状**：`launcher.py` / `download.py` / `widgets.py`（已重命名，原 `launcher_pyside6.py` / `download_pyside6.py` / `widgets_pyside6.py`）暗示存在其他 GUI 框架替代实现，实际不存在。

**建议**：重命名为 `launcher.py` / `download.py` / `widgets.py`，同步更新 `main.py` 的 import。注意同步更新上层引用。

---

### T07 信号 Lambda 链改为具名回调

**现状**：
```python
self._dl_thread.finished_signal.connect(lambda path: (
    setattr(self, '_dl_thread', None),
    self.btn_fetch.setText(...),
    self.progress_bar.setVisible(False),
    ...
))
```
多个副作用塞进 lambda 元组。优点行短，缺点：
- 异常栈看不到行号归属；
- 可读性差，维护成本高；
- 无法直接复用。

**建议**：改为具名方法 `_on_download_finished(path)` / `_on_download_error(err)` / `_on_download_progress(cur, total)`，lambda 只做轻量参数转发。

---

### T08 移除 `CollapsibleSection._toggle` monkey-patch

**现状**：
`main.py::_mk_section` 用 lambda 覆盖实例的 `_toggle` 方法实现持久化：
```python
sec._toggle = (lambda s=sec, k=key: (...)[-1])
```
这是对类设计的绕过。

**建议**：在 `CollapsibleSection` 类内原生支持：
- 构造参数 `on_toggled: Callable[[str, bool], None]`
- `_toggle()` 内部调用 `self._on_toggled(self._key, self._collapsed)`
- 删除 main.py 中的 monkey-patch。

---

### T09 参数解析改用 shlex / 白名单校验

**现状**：
`_split_args()` 为手写解析器，支持单/双引号基本拆分，但对：
- `--key=value`（等号分隔）
- 反斜杠转义
- 嵌套引号
- Windows 与 Linux 语义差异

处理不完善。且 `_validate_arg()` 用黑名单（`; | & $ ` { } < >`），容易被绕过或误伤合法参数。

**建议方案**：
1. **校验方向**：改为白名单正则，仅允许 `[A-Za-z0-9_\-=:/.\\{}%+,]` 等安全字符集；路径参数额外允许盘符冒号。
2. **解析方向**：
   - Windows 下用 `subprocess.list2cmdline` 反向语义配合 `shlex`；
   - 或使用成熟的轻量库 `cmdline`（跨平台）；
   - 至少补充转义规则测试用例集。
3. `command_builder.py` 拆分后此为纯函数，可覆盖全面单测。

---

### T10 控制台输出 HTML 转义与性能

**现状**：`ConsoleWidget.append_output()` 使用 `self.output.append(f'<span style="color:{hex_color}">{text}</span>')`：
- 进程输出若含 `</span>`、`<b>` 等 HTML 会被 Qt 富文本解析，导致渲染错乱甚至样式注入；
- `append` + 每次 `scrollbar.setValue(max)` 在高频输出（如 token 流）下性能差。

**建议方案**：
1. 使用 `QTextCursor.insertHtml()` 前先 `html.escape(text)` 转义输出内容，仅保留颜色 span 结构。
2. 或改用纯文本模式 `QTextEdit.setAcceptRichText(False)` + `QTextCharFormat` 设置颜色。
3. 高频刷新优化：合并短时间内的多次输出（如 50ms 批量追加一次），避免逐行 setValue 滚动。

---

## 四、P2 — 测试与工程化

### T11 补 pytest 单元测试（纯逻辑模块）

**现状**：项目零测试。

**建议首批测试目标**（全部不依赖 Qt，可纯 pytest）：

| 模块 | 测试要点 |
|------|---------|
| `src/config.py` | `find_executables_in_dir`（含子目录/后缀/大小写）；`_load_locale` 缺失文件返回空 dict；`_apply_locale_to_globals` 合并优先级（locale 覆盖 ui_config） |
| `src/backends.py` | `detect_cuda_version("555.xx") == "13.1"`、边界 `"470"`、未知 `"300"` fallback；`get_backends_for_platform` 各平台/架构矩阵 |
| `src/command_builder.py`（拆分后） | `build_command_args` 全类型控件参数映射；`_validate_arg` 黑/白名单用例；`_split_args` 引号/转义/等号用例 |
| `src/platform_win.py` / `src/platform_linux.py` | `_generate_bat_content` / `_generate_sh_content` 特殊字符转义快照测试 |
| 下载过滤逻辑（抽成纯函数） | 给定 mock asset 列表 + backends，验证只返回匹配主包 / cudart 项 |

**建议**：`pytest` + `pytest-qt`（若需要 Qt 信号测试），`tests/` 目录按 `test_config.py`、`test_backends.py` 组织。

### T12 GitHub Actions CI

**建议流水线**：
1. **matrix**：`ubuntu-latest` / `windows-latest` / `macos-latest` × Python 3.8/3.10/3.12。
2. 步骤：`pip install -r requirements.txt pytest` → `pytest` → （可选）`ruff` / `mypy` 静态检查。
3. Release 时触发：构建 PyInstaller 产物并附件上传到 GitHub Release。

### T13 PyInstaller 打包分发

**建议**：
- 新增 `packaging/hello-llama.spec`（PyInstaller spec）；
- Windows 目标：单目录（OneDir）便于 QSS/locales/assets 外置，或 `--onefile` 配合 `--add-data` 打包资源；
- 图标、版本信息（`--version-file`）；
- 排除不需要的 Qt 模块（QtWebEngine 等）减小体积；
- GitHub Actions 中跨平台构建，产物作为 Release assets 发布。

---

## 五、P3 — 体验与健壮性优化

### T14 切换语言时保留未保存输入

**现状**：`_rebuild_ui()` 销毁中央控件重建，动态参数控件从 schema 默认值重建，**用户已调整但未保存的参数会丢失**。

**建议**：
1. 语言切换仅遍历已存在控件更新文字（`setText`/`setToolTip`），不重建控件树；工作量较大但体验最好。
2. 或重建前收集当前控件取值（`dynamic_vars` / `custom_widgets`），重建后回填。
3. 至少保留折叠面板展开状态（已实现）和滚动位置。

### T15 模型搜索 / 文件大小 / 量化类型展示

**建议**：
- 参数页模型下拉框上方加 `QLineEdit` 模型搜索框（子串/正则实时过滤）；
- `refresh_models()` 时顺带读取 `os.path.getsize`，显示 `(GB)`；
- 从文件名推断量化类型（`q4_K_M`、`q8_0`、`f16` 等）后缀标签，辅助选择；
- 或在模型项 tooltip 中展示大小与量化信息。

### T16 下载历史版本（Release tag 选择）

**现状**：只请求 `releases/latest`。

**建议**：
- 设置页下载区域加"版本"下拉框：默认 latest，可选最近 N 个 release（请求 `/releases?per_page=10`）；
- 选中后刷新可用文件列表；
- 注意 `_fetch_assets()` 目前用 `GITHUB_API_URL` 写死 latest，需改为可传入 tag 的 URL 模板。

### T17 VRAM 检测支持 AMD / Intel

**现状**：`VramCheckThread` 仅调用 `nvidia-smi`，AMD 用户点击"显存检测"得到跳过/失败。

**建议**：
- NVIDIA：现有 `nvidia-smi --query-gpu=memory.total,memory.free`；
- AMD ROCm：`rocm-smi --showmeminfo vram`；
- Intel：`xpu-smi discovery`（或 `intel_gpu_top`）；
- 依次探测可用工具，返回首个成功结果；全部失败时提示"未检测到支持的 GPU 工具"。

### T18 应用版本检查 / 自动更新提示

**建议**：
- `main.py` 顶部定义 `__version__`；
- 启动后异步请求 GitHub API 最新 tag，与本地版本比对；
- 有新版时状态栏/对话框提示"发现新版本 bXXXX，可前往设置页更新"；
- 与 T03 缓存共享请求结果，避免重复网络调用。

### T19 配置异常恢复（不再静默吞异常）

**现状**：`load_settings` / `save_settings` / `_restore_window_geometry` 等 `except Exception: pass`，配置 JSON 损坏时静默重置且无提示。

**建议**：
- 捕获异常时在状态栏/控制台输出警告"配置文件已损坏，已使用默认配置"；
- 损坏时自动备份 `launcher_config.json.bak` 再重置；
- 设置页增加"重置所有设置"按钮。

### T20 删除死代码

**现状**：
- `backends.py::make_asset_pattern()` / `make_cudart_pattern()` 从未被调用（实际匹配用 `suffix in name`）；
- `config.py::MIRROR_BASE_URLS` 仅含 GitHub 官方地址，README 却又说可自行添加镜像——保持现状但文档需注明是代码级修改。

**建议**：删除未使用函数；或若 T04 实现 cudart 下载则接入 `make_cudart_pattern` 复用正则逻辑。

---

## 六、建议推进顺序（里程碑）

### Milestone 1：修复核心下载链路（P0，1-2 天）
1. T01 下载后自动解压（含 zip-slip 防护）
2. T02 恢复系统代理跟随
3. T03 实现 Release 30 分钟缓存
4. 更新 README（解压/缓存描述与实现对齐）

### Milestone 2：架构与健壮性（P1，3-5 天）
5. T05 拆分 main.py → 抽出 `command_builder.py` / `config_store.py`
6. T09 参数解析改 shlex + 白名单校验
7. T04 cudart 伴生包下发
8. T07 / T08 信号与折叠面板重构

### Milestone 3：测试与工程化（P2，3-5 天）
9. T11 pytest 补齐（优先 command_builder / backends / config）
10. T12 GitHub Actions CI
11. T13 PyInstaller 打包

### Milestone 4：体验优化（P3，按需）
12. T15 模型搜索与信息展示
13. T14 语言切换保留输入
14. T17 VRAM 多品牌
15. T16 / T18 版本选择与更新检查

---

## 七、Open Questions（需要决策）

| 问题 | 选项 | 建议 |
|------|------|------|
| 是否保持 Python 3.8 最低版本？ | 是 / 提高到 3.10 | 若引入 `dataclass` + `match` 语法建议 3.10；否则维持 3.8 覆盖更广 |
| 打包是否纳入本仓库维护？ | 是 / 单独仓库 | 建议本仓库，方便与源码同步 |
| 是否接受引入第三方依赖（shlex 替代品 / 打包库）？ | 仅 PySide6 / 可扩展 | 测试与打包依赖可放 `requirements-dev.txt`，与运行时分离 |
| CUDA cudart 交付策略 | 自动随主包下载 / 可选勾选 | 建议主包完成后自动检测并补下，减少用户操作 |