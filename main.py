"""
llama.cpp 启动器 —— PySide6 QWidget 主 UI 入口。
将 UI 与下载、字符拼写、bat/sh 生成、平台检测解耦。
标签页: 参数 | 设置 | 控制台 (参数可折叠)
"""
import sys
import os
import re
import json
import webbrowser
import subprocess
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout,
    QHBoxLayout, QGridLayout, QLabel, QPushButton, QLineEdit,
    QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox,
    QScrollArea, QFrame, QFileDialog, QMessageBox, QSizePolicy,
    QRadioButton, QProgressBar,
)
from PySide6.QtCore import Qt, QTimer, QByteArray, QPointF
from PySide6.QtGui import QFont, QFontDatabase, QColor, QPixmap, QPainter, QPolygonF

# ── 从 src 包导入解耦模块 ──
from src.config import (
    BASE_DIR, BIN_DIR, CONFIG_PATH,
    COMMON_EXES,
    STYLESHEET, LIGHT_STYLESHEET,
    BTN, WIN_TITLES, PH, UI_LABELS, MSG,
    DYNAMIC_UI_SCHEMA, UI_SECTIONS, DEFAULT_CONFIG,
    PARAM_LABELS,
    _open_folder,
    _list_locales, _list_locales_with_names, _apply_locale_to_globals,
    find_executables_in_dir, has_executables,
    CREATE_NEW_CONSOLE, REF_WIDTH_FOR_SCALE,
)
from src.platform import (
    open_folder, save_script,
)
from src.launcher_pyside6 import LaunchThread
from src.download_pyside6 import ReleaseDownloadThread, VramCheckThread
from src.widgets_pyside6 import (
    CollapsibleSection, AdaptiveComboBox, ConsoleWidget, CommandPreviewDialog,
    NoWheelSpinBox, NoWheelDoubleSpinBox,
)

_LEFT  = Qt.AlignmentFlag.AlignLeft
_RIGHT = Qt.AlignmentFlag.AlignRight

# ═══════════════════════════════════════════════
#  LlamaProLauncher —— 主窗口
# ═══════════════════════════════════════════════

class LlamaProLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hello Llama.cpp Launcher")
        self.setMinimumSize(420, 300)

        self.config_path = CONFIG_PATH
        self.config      = dict(DEFAULT_CONFIG)
        self.load_settings()

        # 多语言初始化
        lang = self.config.get("lang", "zh")
        _apply_locale_to_globals(lang)
        self.setWindowTitle(WIN_TITLES.get("main_window", "Hello Llama.cpp Launcher"))

        # 字体
        self._custom_font_family: Optional[str] = None
        self._font_scale  = 1.0
        self._resize_timer: Optional[QTimer] = None
        self._resize_throttle_timer: Optional[QTimer] = None
        self._sheet_cache: dict = {}          # (theme, combined_scale, font_family) → full_sheet

        # 模型路径映射
        self.full_paths: dict = {}

        # 控制台
        self.console: Optional[ConsoleWidget] = None

        # 启动线程
        self.launch_thread: Optional[LaunchThread] = None
        self._server_ready_opened = False

        # 显存检测线程
        self._vram_thread: Optional[VramCheckThread] = None

        # 下载线程
        self._dl_thread: Optional[ReleaseDownloadThread] = None

        # 动态控件 & 折叠面板
        self.dynamic_vars: dict = {}
        self.custom_widgets: dict = {}
        self._sections: list = []

        # 思考模式
        self._think_mode = self.config.get("think_mode", "normal")

        # 构建 UI
        self.build_ui()

        # 应用主题
        self.apply_theme()

        # 加载字体
        self._load_custom_font()

        # 恢复窗口几何
        self._restore_window_geometry()

        # 自动检测可执行文件
        QTimer.singleShot(100, self.detect_executables)
        # 自动刷新模型列表
        QTimer.singleShot(200, self.refresh_models)

    # ── 配置存取 ──────────────────────────────────

    def load_settings(self) -> None:
        _NUMERIC_FIELDS = {"ui_scale", "retry_count", "dl_timeout"}
        _BOOL_FIELDS = {"only_cpu", "auto_scale", "mmproj_enable",
                        "model_draft_enable", "auto_open_browser",
                        "is_server_mode", "console_mode"}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # 强制数值字段类型（兼容旧版本配置的字符串存储）
            for k in _NUMERIC_FIELDS:
                if k in saved and isinstance(saved[k], str):
                    saved[k] = float(saved[k]) if "." in saved[k] else int(saved[k])
            # 强制布尔字段类型（避免 "false" 被 bool() 判为 True）
            for k in _BOOL_FIELDS:
                if k in saved and isinstance(saved[k], str):
                    saved[k] = saved[k].strip().lower() in ("true", "1", "yes", "on")
            self.config.update(saved)
        except Exception:
            pass

    def save_settings(self) -> None:
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # ── 样式表缩放与字体注入 ──────────────────────────

    def _scale_stylesheet(self, sheet: str, scale: float) -> str:
        def _repl_px(m):
            return f"{float(m.group(1)) * scale:.1f}px"
        def _repl_pt(m):
            return f"{float(m.group(1)) * scale:.1f}pt"
        sheet = re.sub(r"(\d+(?:\.\d+)?)px", _repl_px, sheet)
        sheet = re.sub(r"(\d+(?:\.\d+)?)pt", _repl_pt, sheet)
        return sheet

    def _inject_custom_font_into_sheet(self, sheet: str) -> str:
        if self._custom_font_family:
            return f"* {{ font-family: \"{self._custom_font_family}\"; }}\n" + sheet
        return sheet

    def apply_theme(self, theme: Optional[str] = None) -> None:
        if theme is None:
            theme = str(self.config.get("theme", "dark"))
        else:
            self.config["theme"] = theme
        # Fusion palette 随主题切换（QSS 未覆盖的控件：右键菜单/对话框等）
        app = QApplication.instance()
        if app:
            if theme == "light":
                _apply_light_palette(app)
            else:
                _apply_dark_palette(app)
        self._apply_full_stylesheet(theme)
        if self.console:
            self.console.set_theme(theme)
        AdaptiveComboBox.set_theme(theme)
        self.save_settings()

    def _on_section_toggled(self, key: str, collapsed: bool) -> None:
        self.config.setdefault("collapsed_sections", {})[key] = collapsed
        self.save_settings()

    def _arrow_icons_css(self, theme: str) -> str:
        if getattr(self, '_arrow_css_theme', '') == theme:
            return self._arrow_css_cached
        cache_dir = os.path.join(BASE_DIR, ".cache")
        os.makedirs(cache_dir, exist_ok=True)
        c = QColor("#222222" if theme == "light" else "#e0e0f0")
        W, H = 20, 16
        up_pm, down_pm = QPixmap(W, H), QPixmap(W, H)
        for pm, up in ((up_pm, True), (down_pm, False)):
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.setBrush(c)
            p.setPen(Qt.PenStyle.NoPen)
            if up:
                p.drawPolygon(QPolygonF([QPointF(10, 2), QPointF(2, 13), QPointF(18, 13)]))
            else:
                p.drawPolygon(QPolygonF([QPointF(10, 13), QPointF(2, 2), QPointF(18, 2)]))
            p.end()
        u = os.path.join(cache_dir, "spin_up.png").replace("\\", "/")
        d = os.path.join(cache_dir, "spin_down.png").replace("\\", "/")
        up_pm.save(u); down_pm.save(d)

        cb_w, cb_h = 24, 24
        cb_pm = QPixmap(cb_w, cb_h)
        cb_pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(cb_pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setBrush(c)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF([QPointF(6, 8), QPointF(18, 8), QPointF(12, 16)]))
        p.end()
        cb_path = os.path.join(cache_dir, f"combo_down_{theme}.png").replace("\\", "/")
        cb_pm.save(cb_path)

        css = f'QSpinBox::up-arrow,QDoubleSpinBox::up-arrow{{image:url("{u}");width:10px;height:8px}}' \
              f'QSpinBox::down-arrow,QDoubleSpinBox::down-arrow{{image:url("{d}");width:10px;height:8px}}' \
              f'QComboBox::down-arrow{{border:none;image:url("{cb_path}");width:12px;height:12px;margin-right:4px}}'
        self._arrow_css_theme = theme
        self._arrow_css_cached = css
        return css

    def _apply_full_stylesheet(self, theme: str):
        is_light = (theme == "light")
        combined = self._font_scale * float(self.config.get("ui_scale", 1.0))
        cache_key = (theme, round(combined, 3), self._custom_font_family or "")
        cached = self._sheet_cache.get(cache_key)
        if cached is not None:
            full_sheet = cached
        else:
            base_sheet = LIGHT_STYLESHEET if is_light else STYLESHEET
            base_sheet = self._inject_custom_font_into_sheet(base_sheet)
            scaled = self._scale_stylesheet(base_sheet, combined)
            arrow_css = self._arrow_icons_css(theme)
            full_sheet = scaled + "\n" + arrow_css
            self._sheet_cache[cache_key] = full_sheet

        # 相同样式表跳过重复应用，避免拖窗时全树 repolish 卡顿
        if getattr(self, '_last_applied_sheet', None) is full_sheet:
            return
        self._last_applied_sheet = full_sheet

        app = QApplication.instance()
        if app:
            self.setUpdatesEnabled(False)
            app.setStyleSheet(full_sheet)
            self.setUpdatesEnabled(True)

    # ── 多语言 ──────────────────────────────────

    def _on_language_changed(self, idx: int):
        code = self._lang_combo.itemData(idx)
        if code:
            self.config["lang"] = code
            self.save_settings()
            _apply_locale_to_globals(code)
            self._rebuild_ui()

    def _rebuild_ui(self):
        self.setWindowTitle(WIN_TITLES.get("main_window", "Hello Llama.cpp Launcher"))
        central = self.centralWidget()
        if central:
            central.deleteLater()
        self._sections.clear()
        self.dynamic_vars.clear()
        self.custom_widgets.clear()
        self.build_ui()
        self.apply_theme()
        self._load_custom_font()
        self.detect_executables()
        self.refresh_models()

    def _on_ui_scale_changed(self, value: float):
        self.config["ui_scale"] = value
        theme = self.config.get("theme", "dark")
        self.apply_theme(theme)

    # ── 辅助方法 ──────────────────────────────────

    def get_combo(self):
        return self._model_combo

    # ═══════════════════════════════════════════════
    #  主界面构建 (build_ui)
    # ═══════════════════════════════════════════════

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 6, 8, 4)
        root_layout.setSpacing(4)

        # ── 标签页 ──
        self.tabs = QTabWidget()
        root_layout.addWidget(self.tabs)

        # 标签页 1: 参数
        params_tab = QWidget()
        self.tabs.addTab(params_tab, WIN_TITLES.get("params_tab", "📊 参数"))
        self._build_params_tab(params_tab)

        # 标签页 2: 设置
        settings_tab = QWidget()
        self.tabs.addTab(settings_tab, WIN_TITLES.get("settings_tab", "⚙ 设置"))
        self._build_settings_tab(settings_tab)

        # 标签页 3: 控制台
        self.console = ConsoleWidget()
        self.console.input_signal.connect(self._on_console_input)
        self.tabs.addTab(self.console, WIN_TITLES.get("console_tab", "📟 控制台"))

        # ── 底部操作栏 ──
        bottom_bar = QFrame()
        bottom_bar.setObjectName("actionFrame")
        bb_layout = QHBoxLayout(bottom_bar)
        bb_layout.setContentsMargins(6, 4, 6, 4)
        bb_layout.setSpacing(6)

        self.btn_launch = QPushButton(BTN.get("launch", "▶ 启动"))
        self.btn_launch.setObjectName("btnLaunch")
        self.btn_launch.clicked.connect(self.launch)
        bb_layout.addWidget(self.btn_launch)

        self.btn_stop = QPushButton(BTN.get("stop", "⏹ 停止"))
        self.btn_stop.setObjectName("btnStop")
        self.btn_stop.clicked.connect(self.stop_launch)
        self.btn_stop.setEnabled(False)
        bb_layout.addWidget(self.btn_stop)

        self.btn_preview = QPushButton(BTN.get("preview", "📋 预览"))
        self.btn_preview.clicked.connect(self.show_command_preview)
        bb_layout.addWidget(self.btn_preview)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(120)
        self.progress_bar.setMaximumHeight(14)
        bb_layout.addWidget(self.progress_bar)

        bb_layout.addStretch()

        self.status_label = QLabel(UI_LABELS.get("status_ready", "就绪"))
        self.status_label.setObjectName("statusLabel")
        bb_layout.addWidget(self.status_label)

        root_layout.addWidget(bottom_bar)

        # ── 最下层状态栏 ──
        status_bar = QFrame()
        status_bar.setObjectName("statusBar")
        sb_layout = QHBoxLayout(status_bar)
        sb_layout.setContentsMargins(8, 2, 8, 2)
        sb_layout.setSpacing(8)
        self.vram_label = QLabel(MSG.get("vram_unknown_label", "VRAM: --- / --- MiB"))
        sb_layout.addWidget(self.vram_label)
        self.log_label = QLabel("")
        sb_layout.addWidget(self.log_label, 1)
        root_layout.addWidget(status_bar)

    # ═══════════════════════════════════════════════
    #  标签页 1: 参数 (模型选择 + 动态参数，可折叠)
    # ═══════════════════════════════════════════════

    def _build_params_tab(self, tab: QWidget):
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        tab_layout.addWidget(scroll_area)

        container = QWidget()
        container.setObjectName("paramsContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        def _mk_section(key: str, title: str, widget: QWidget) -> CollapsibleSection:
            collapsed = self.config.get("collapsed_sections", {}).get(key, False)
            sec = CollapsibleSection(title, widget, section_key=key, collapsed=collapsed)
            sec._toggle = (lambda s=sec, k=key: (
                s.set_collapsed(not s._collapsed),
                self._on_section_toggled(k, s._collapsed),
            )[-1])
            self._sections.append(sec)
            return sec

        # ── 模型选择 ──
        model_w = QWidget()
        mw = QVBoxLayout(model_w)
        mw.setContentsMargins(6, 2, 6, 2)
        mw.setSpacing(4)

        model_sel = QWidget()
        ms = QHBoxLayout(model_sel)
        ms.setContentsMargins(0, 0, 0, 0)
        ms.setSpacing(3)
        lbl = QLabel(UI_LABELS.get("label_model_select", "选择模型:"))
        lbl.setFont(QFont('Segoe UI', 9, QFont.Weight.Bold))
        ms.addWidget(lbl)

        del_btn = QPushButton(BTN.get("delete_preset", "🗑 删除预设"))
        del_btn.setToolTip(BTN.get("delete_preset_tooltip", "删除当前选中模型的已保存预设"))
        del_btn.clicked.connect(self.delete_current_preset)
        ms.addWidget(del_btn, alignment=_RIGHT)
        mw.addWidget(model_sel)

        self._model_combo = AdaptiveComboBox()
        self._model_combo.currentIndexChanged.connect(self.on_model_change)
        mw.addWidget(self._model_combo)

        preset_btns = QWidget()
        pb = QHBoxLayout(preset_btns)
        pb.setContentsMargins(0, 0, 0, 0)
        pb.setSpacing(3)
        refresh_btn = QPushButton(BTN.get("refresh", "🔄 刷新模型"))
        refresh_btn.clicked.connect(self.refresh_models)
        pb.addWidget(refresh_btn)
        save_btn = QPushButton(BTN.get("save_preset", "💾 保存预设"))
        save_btn.clicked.connect(self.save_current_preset)
        pb.addWidget(save_btn)
        pb.addStretch()
        mw.addWidget(preset_btns)

        layout.addWidget(_mk_section("model", UI_LABELS.get("model_section", "模型选择"), model_w))

        # ── 动态参数（紧凑 4 列 grid）──
        def _make_widget(ptype: str, param: dict):
            if ptype == "string":
                w = QLineEdit(str(param.get("default", "")))
            elif ptype == "int":
                w = NoWheelSpinBox()
                w.setRange(param.get("min", 0), param.get("max", 999999))
                w.setSingleStep(param.get("step", 1))
                w.setValue(int(param.get("default", 0)))
            elif ptype == "float":
                w = NoWheelDoubleSpinBox()
                w.setRange(param.get("min", 0.0), param.get("max", 100.0))
                w.setSingleStep(param.get("step", 0.1))
                w.setDecimals(3)
                w.setValue(float(param.get("default", 0.0)))
            elif ptype == "bool":
                w = QCheckBox(UI_LABELS.get("checkbox_enable", "启用"))
                w.setChecked(bool(param.get("default", False)))
            elif ptype == "check":
                w = QCheckBox(UI_LABELS.get("checkbox_enable", "启用"))
                w.setChecked(bool(param.get("default", True)))
            elif ptype == "combo":
                w = AdaptiveComboBox()
                opts = param.get("options", [])
                w.addItems(opts)
                default_val = str(param.get("default", ""))
                if default_val in opts:
                    w.setCurrentText(default_val)
                elif opts:
                    w.setCurrentIndex(0)
            else:
                w = QLineEdit(str(param.get("default", "")))
            return w

        if DYNAMIC_UI_SCHEMA:
            self._spec_draft_rows: list[tuple[QLabel, QWidget]] = []  # (label, widget)
            self._spec_ngram_rows: list[tuple[QLabel, QWidget]] = []  # (label, widget)
            spec_type_widget = None

            for group in DYNAMIC_UI_SCHEMA:
                is_spec_group = "spec_type" in {p["id"] for p in group["params"]}
                params_w = QWidget()
                gl = QGridLayout(params_w)
                gl.setSpacing(4)
                gl.setContentsMargins(6, 2, 6, 2)
                gl.setColumnStretch(0, 0)
                gl.setColumnStretch(1, 1)
                gl.setColumnStretch(2, 0)
                gl.setColumnStretch(3, 1)
                gl.setColumnMinimumWidth(0, 90)
                gl.setColumnMinimumWidth(2, 90)
                row, col, max_col = 0, 0, 4

                for param in group["params"]:
                    pid   = param["id"]
                    ptype = param.get("type", "string")
                    wide  = param.get("width", 0)
                    tt    = param.get("tooltip", "")
                    w     = _make_widget(ptype, param)
                    self.dynamic_vars[pid] = w
                    lbl_text = PARAM_LABELS.get(pid, param.get("label", pid))
                    lbl = QLabel(lbl_text)
                    if tt:
                        lbl.setToolTip(tt); w.setToolTip(tt)

                    gl.addWidget(lbl, row, col, _LEFT)
                    gl.addWidget(w,   row, col + 1)

                    # 记录投机解码参数行用于条件显隐
                    if is_spec_group and pid != "spec_type":
                        if pid.startswith("spec_draft_"):
                            self._spec_draft_rows.append((lbl, w))
                        elif pid.startswith("spec_ngram_"):
                            self._spec_ngram_rows.append((lbl, w))
                    elif pid == "spec_type":
                        spec_type_widget = w

                    col += 2
                    if col >= max_col:
                        col = 0; row += 1

                raw_title = group.get("group_name", group.get("title", "参数"))
                title = PARAM_LABELS.get(raw_title, raw_title.strip())
                # 折叠键用原始标题（不随语言变化），保证切换语言后折叠状态保留
                layout.addWidget(_mk_section(f"params_{raw_title.strip()}", title, params_w))

            # 关联投机解码类型切换 → 显隐子参数
            if spec_type_widget:
                spec_type_widget.currentTextChanged.connect(self._on_spec_type_changed)
                # 初始调用一次以应用初始状态
                self._on_spec_type_changed(spec_type_widget.currentText())

        # ── UI 段落（从 ui_config.json 的 ui_sections 定义） ──
        self._build_ui_sections(layout, _mk_section)

        layout.addStretch()
        scroll_area.setWidget(container)
        def _on_params_scroll(v):
            for sec in self._sections:
                sec._content.update()
        scroll_area.verticalScrollBar().valueChanged.connect(_on_params_scroll)

    def _build_ui_sections(self, layout, _mk_section):
        """从 UI_SECTIONS 构建参数页段落。支持: checkbox/label/text/radio/file，
        new_row 控制换行，file 自动拉伸输入框并压缩按钮。"""
        if not UI_SECTIONS:
            print("[警告] ui_config.json 未定义 ui_sections，参数页附加段落被跳过")
            return
        from PySide6.QtWidgets import QButtonGroup
        for section in UI_SECTIONS:
            key = section.get("group_name", "").strip()
            raw_key = section.get("group_name", key)
            # 优先用带空格的原始键查翻译（locale 键格式一致），失败回退 strip 后键
            title = PARAM_LABELS.get(raw_key, PARAM_LABELS.get(key, key)) or "参数"
            sec_key = f"ui_{key}"

            sec_w = QWidget()
            sv = QVBoxLayout(sec_w)
            sv.setContentsMargins(6, 2, 6, 2)
            sv.setSpacing(4)

            # 当前行容器（QHBoxLayout），由 new_row 控制换行
            current_row = None
            current_row_layout = None

            btn_groups = {}

            def _start_new_row():
                nonlocal current_row, current_row_layout
                r = QWidget()
                rl = QHBoxLayout(r)
                rl.setContentsMargins(0, 0, 0, 0)
                rl.setSpacing(6)
                current_row = r
                current_row_layout = rl
                sv.addWidget(r)

            def _add_to_row(widget, stretch=0):
                if current_row_layout is None:
                    _start_new_row()
                current_row_layout.addWidget(widget, stretch)

            for ctrl in section.get("controls", []):
                ct = ctrl.get("type", "text")
                cid = ctrl.get("id", "")
                # 控件文本接线多语言：优先查 UI_LABELS（键=控件 id），回退 ui_config 值
                label = UI_LABELS.get(cid, ctrl.get("label", ""))
                default = ctrl.get("default", "")
                width = ctrl.get("width", 0)
                placeholder = PH.get(f"{cid}_placeholder", ctrl.get("placeholder", ""))
                rgroup = ctrl.get("group", "")
                rvalue = ctrl.get("value", "")
                new_row = ctrl.get("new_row", True)  # 默认换行

                if ct == "checkbox":
                    ck = ctrl.get("config_key", cid)
                    w = QCheckBox(label)
                    w.setChecked(bool(self.config.get(ck, default)))
                    if cid == "is_server_mode":
                        w.toggled.connect(self.on_server_mode_toggle)
                    elif cid in ("mmproj_cb", "draft_cb"):
                        fd = "mmproj" if "mmproj" in cid else "model_draft"
                        w.toggled.connect(lambda v, k=ck, field=fd: (
                            self.config.update({k: v}),
                            self.custom_widgets.get(field, QLineEdit()).setEnabled(v),
                            self.save_settings(),
                        ))
                    else:
                        w.toggled.connect(lambda v, k=ck: (
                            self.config.update({k: v}) or self.save_settings()))
                    self.custom_widgets[cid] = w
                    if new_row:
                        _start_new_row()
                    _add_to_row(w)

                elif ct == "label":
                    txt = ctrl.get("text", label)
                    w = QLabel(txt)
                    if cid == "mode_label":
                        self.mode_label = w
                        if new_row:
                            _start_new_row()
                        _add_to_row(w, stretch=1)
                    else:
                        if new_row:
                            _start_new_row()
                        _add_to_row(w)

                elif ct == "text":
                    cfg_key = ctrl.get("config_key", cid)
                    w = QLineEdit(str(self.config.get(cfg_key, default)))
                    if placeholder:
                        w.setPlaceholderText(placeholder)
                    if width:
                        w.setMaximumWidth(width)
                    save_key = ctrl.get("config_key", cid)
                    w.textChanged.connect(lambda text, k=save_key: self.config.update({k: text}) or self.save_settings())
                    self.custom_widgets[cid] = w
                    if new_row:
                        _start_new_row()
                    if label:
                        lbl_w = QLabel(label)
                        _add_to_row(lbl_w)
                    _add_to_row(w, stretch=1)

                elif ct == "radio":
                    if rgroup not in btn_groups:
                        btn_groups[rgroup] = QButtonGroup(sec_w)
                    bg = btn_groups[rgroup]
                    w = QRadioButton(label)
                    bg.addButton(w)
                    current_val = self.config.get(rgroup, "normal")
                    w.setChecked(current_val == rvalue)
                    w.toggled.connect(lambda checked, val=rvalue, rg=rgroup: (
                        checked and self.config.update({rg: val}) and
                        (self.set_think_mode(val) if rg == "think_mode" else None) and
                        self.save_settings()
                    ))
                    if rgroup == "think_mode":
                        setattr(self, f"radio_{rvalue}", w)
                    if new_row:
                        _start_new_row()
                    _add_to_row(w)

                elif ct == "file":
                    # 文件行：固定 label + 拉伸输入框 + 紧凑按钮
                    enable_id = ctrl.get("enable_by", "")
                    if new_row:
                        _start_new_row()
                    if label:
                        lbl_w = QLabel(label)
                        _add_to_row(lbl_w)
                    # 输入框 + 按钮容器
                    w = QLineEdit(str(self.config.get(cid, "")))
                    w.setPlaceholderText(f"选择{label.replace(':', '')}...")
                    # 关联启用复选框
                    if enable_id:
                        cb = self.custom_widgets.get(enable_id)
                        if cb and isinstance(cb, QCheckBox):
                            w.setEnabled(cb.isChecked())
                            cb.toggled.connect(lambda checked, fw=w: fw.setEnabled(checked))
                    btn = QPushButton(BTN.get("select_file", "选择"))
                    btn.setFixedWidth(64)  # 紧凑按钮
                    btn.clicked.connect(lambda checked, fid=cid: self._on_file_browse(fid))
                    w.textChanged.connect(lambda text, k=cid: self.config.update({k: text}) or self.save_settings())
                    self.custom_widgets[cid] = w
                    _add_to_row(w, stretch=1)
                    _add_to_row(btn)

            # 存储 radio_groups 引用
            if btn_groups:
                if not hasattr(self, '_radio_groups'):
                    self._radio_groups = {}
                self._radio_groups.update(btn_groups)

            layout.addWidget(_mk_section(sec_key, title, sec_w))

    def _on_file_browse(self, cid: str):
        """文件类型控件的浏览按钮事件。"""
        cfg_key = "mmproj" if "mmproj" in cid else "model_draft" if "draft" in cid else cid
        title_map = {"mmproj": WIN_TITLES.get("select_mmproj_title", "选择 MMProj 文件"),
                     "model_draft": WIN_TITLES.get("select_draft_title", "选择 Draft 模型文件")}
        filt_map = {"mmproj": "MMProj (*.mmproj *.gguf);;All (*.*)", "model_draft": "GGUF (*.gguf);;All (*.*)"}
        title = title_map.get(cfg_key, "选择文件")
        filt = filt_map.get(cfg_key, "All (*.*)")
        p, _ = QFileDialog.getOpenFileName(self, title,
                                           self.custom_widgets.get("model_dir", QLineEdit()).text(), filt)
        if p:
            w = self.custom_widgets.get(cid)
            if w:
                w.setText(os.path.normpath(p))
            self.config[cfg_key] = os.path.normpath(p)
            self.save_settings()

    # ═══════════════════════════════════════════════
    #  标签页 2: 设置
    # ═══════════════════════════════════════════════

    def _build_settings_tab(self, tab: QWidget):
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        tab_layout.addWidget(scroll_area)

        container = QWidget()
        container.setObjectName("settingsContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        def _section(title: str) -> QWidget:
            w = QWidget()
            vl = QVBoxLayout(w)
            vl.setContentsMargins(0, 0, 0, 0)
            vl.setSpacing(2)
            hdr = QLabel(title)
            hdr.setObjectName("settingsSection")
            vl.addWidget(hdr)
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            vl.addWidget(sep)
            body = QWidget()
            vl.addWidget(body)
            w._body = body
            return w

        # ═══ 路径 ═══
        sec_path = _section(UI_LABELS.get("section_path", "📂 核心路径"))
        pg = QGridLayout(sec_path._body); pg.setSpacing(3); pg.setContentsMargins(0,2,0,0)
        pg.setColumnStretch(0, 0); pg.setColumnStretch(1, 1); pg.setColumnStretch(2, 0)

        pg.addWidget(QLabel(UI_LABELS.get("label_bin_dir", "Bin:")), 0, 0)
        self.custom_widgets["bin_dir"] = QLineEdit(self.config.get("bin_dir", ""))
        pg.addWidget(self.custom_widgets["bin_dir"], 0, 1)
        btn_bin = QPushButton(BTN.get("browse", "浏览")); btn_bin.clicked.connect(self.select_bin_dir)
        pg.addWidget(btn_bin, 0, 2)

        pg.addWidget(QLabel(UI_LABELS.get("label_model_dir", "模型:")), 1, 0)
        self.custom_widgets["model_dir"] = QLineEdit(self.config.get("model_dir", ""))
        pg.addWidget(self.custom_widgets["model_dir"], 1, 1)
        btn_model = QPushButton(BTN.get("browse", "浏览")); btn_model.clicked.connect(self.select_model_dir)
        pg.addWidget(btn_model, 1, 2)

        pg.addWidget(QLabel(UI_LABELS.get("label_detected_exe", "EXE:")), 2, 0)
        self.exe_label = QLabel(UI_LABELS.get("label_exe_not_found", "(未检测)"))
        self.exe_label.setObjectName("exeLabel")
        pg.addWidget(self.exe_label, 2, 1)
        btn_detect_exe = QPushButton(BTN.get("redetect", "重检")); btn_detect_exe.clicked.connect(self.detect_executables)
        pg.addWidget(btn_detect_exe, 2, 2)
        layout.addWidget(sec_path)

        # ═══ 外观 ═══
        sec_appear = _section(UI_LABELS.get("section_appearance", "🎨 外观"))
        ag = QGridLayout(sec_appear._body); ag.setSpacing(3); ag.setContentsMargins(0,2,0,0)
        ag.setColumnStretch(0, 0); ag.setColumnStretch(1, 1); ag.setColumnStretch(2, 0); ag.setColumnStretch(3, 1)

        ag.addWidget(QLabel(UI_LABELS.get("label_language", "语言:")), 0, 0)
        self._lang_combo = AdaptiveComboBox()
        for code, name in _list_locales_with_names():
            self._lang_combo.addItem(name, userData=code)
        cur_lang = self.config.get("lang", "zh")
        for i in range(self._lang_combo.count()):
            if self._lang_combo.itemData(i) == cur_lang:
                self._lang_combo.setCurrentIndex(i); break
        self._lang_combo.currentIndexChanged.connect(self._on_language_changed)
        ag.addWidget(self._lang_combo, 0, 1)
        ag.addWidget(QLabel(UI_LABELS.get("label_theme", "主题:")), 0, 2)
        self._theme_combo = AdaptiveComboBox()
        self._theme_combo.addItems(["dark", "light"])
        self._theme_combo.setCurrentText(str(self.config.get("theme", "dark")))
        self._theme_combo.currentTextChanged.connect(self.apply_theme)
        ag.addWidget(self._theme_combo, 0, 3)
        layout.addWidget(sec_appear)

        # ═══ 字体 ═══
        sec_font = _section(UI_LABELS.get("section_font", "🔤 字体"))
        fg = QGridLayout(sec_font._body); fg.setSpacing(3); fg.setContentsMargins(0,2,0,0)
        fg.setColumnStretch(0, 0); fg.setColumnStretch(1, 1); fg.setColumnStretch(2, 0)
        fg.addWidget(QLabel(UI_LABELS.get("label_font_file", "自定义:")), 0, 0)
        self.custom_widgets["font_path"] = QLineEdit(self.config.get("font_path", ""))
        self.custom_widgets["font_path"].setPlaceholderText(UI_LABELS.get("label_font_file_tip", "留空=系统默认"))
        fg.addWidget(self.custom_widgets["font_path"], 0, 1)
        btn_font = QPushButton(BTN.get("select_mmproj", "选择")); btn_font.clicked.connect(self._select_font_file)
        fg.addWidget(btn_font, 0, 2)
        layout.addWidget(sec_font)

        # ═══ 缩放 ═══
        sec_scale = _section(UI_LABELS.get("section_scale", "📐 缩放"))
        sg = QHBoxLayout(sec_scale._body); sg.setContentsMargins(0,2,0,0); sg.setSpacing(5)
        self.scale_label = QLabel(UI_LABELS.get("scale_label", "缩放:"))
        sg.addWidget(self.scale_label)
        self.scale_spin = NoWheelDoubleSpinBox()
        self.scale_spin.setRange(0.50, 2.00)
        self.scale_spin.setSingleStep(0.05)
        self.scale_spin.setDecimals(2)
        self.scale_spin.setValue(float(self.config.get("ui_scale", 1.0)))
        self.scale_spin.setFixedWidth(70)
        self.scale_spin.valueChanged.connect(self._on_ui_scale_changed)
        sg.addWidget(self.scale_spin)
        auto_scale_cb = QCheckBox(UI_LABELS.get("label_auto_scale", "自适应"))
        auto_scale_cb.setChecked(self.config.get("auto_scale", True))
        auto_scale_cb.toggled.connect(lambda v: (
            self.config.update({"auto_scale": v}),
            self.save_settings(),
            (self._apply_font_scale() if v else self._reset_font_scale()),
        ))
        sg.addWidget(auto_scale_cb)
        sg.addStretch()
        layout.addWidget(sec_scale)

        # ═══ 下载 ═══
        sec_dl = _section(UI_LABELS.get("section_download", "⬇ 下载与更新"))
        dg = QGridLayout(sec_dl._body); dg.setSpacing(3); dg.setContentsMargins(0,2,0,0)
        dg.setColumnStretch(0, 0); dg.setColumnStretch(1, 0); dg.setColumnStretch(2, 0); dg.setColumnStretch(3, 1)

        self.btn_fetch = QPushButton(BTN.get("fetch_files", "📡 获取可用文件"))
        self.btn_fetch.clicked.connect(lambda: self._start_download(is_update=False))
        dg.addWidget(self.btn_fetch, 0, 0, 1, 2)
        self.btn_detect = QPushButton(BTN.get("vram_detect", "🔍 VRAM"))
        self.btn_detect.clicked.connect(self.show_auto_ngl)
        dg.addWidget(self.btn_detect, 0, 2)

        retry_row = QWidget(); rrl = QHBoxLayout(retry_row); rrl.setContentsMargins(0,0,0,0); rrl.setSpacing(3)
        rrl.addWidget(QLabel(UI_LABELS.get("label_retry", "重试:")))
        retry_spin = NoWheelSpinBox(); retry_spin.setRange(1,10); retry_spin.setValue(self.config.get("retry_count",3))
        retry_spin.setMaximumWidth(50)
        retry_spin.valueChanged.connect(lambda v: self.config.update({"retry_count": v}) or self.save_settings())
        rrl.addWidget(retry_spin)
        rrl.addWidget(QLabel(UI_LABELS.get("label_timeout", "超时(s):")))
        timeout_spin = NoWheelSpinBox(); timeout_spin.setRange(30,3600); timeout_spin.setValue(self.config.get("dl_timeout",300))
        timeout_spin.setMaximumWidth(65)
        timeout_spin.valueChanged.connect(lambda v: self.config.update({"dl_timeout": v}) or self.save_settings())
        rrl.addWidget(timeout_spin)
        rrl.addStretch()
        dg.addWidget(retry_row, 3, 0, 1, 4)

        self._dl_list_widget = QWidget()
        self._dl_list_layout = QVBoxLayout(self._dl_list_widget)
        self._dl_list_layout.setContentsMargins(0, 4, 0, 0)
        self._dl_list_layout.setSpacing(2)
        self._dl_list_widget.setVisible(False)
        dg.addWidget(self._dl_list_widget, 4, 0, 1, 4)

        layout.addWidget(sec_dl)

        layout.addStretch()
        scroll_area.setWidget(container)
        scroll_area.verticalScrollBar().valueChanged.connect(
            lambda v: container.update())

    # ═══════════════════════════════════════════════
    #  Helper Methods
    # ═══════════════════════════════════════════════

    def _on_spec_type_changed(self, spec_type: str):
        """投机解码类型切换 → 显隐对应的子参数行。"""
        is_draft = spec_type.startswith("draft-")
        is_ngram = spec_type.startswith("ngram-")
        for lbl, w in getattr(self, '_spec_draft_rows', []):
            lbl.setVisible(is_draft); w.setVisible(is_draft)
        for lbl, w in getattr(self, '_spec_ngram_rows', []):
            lbl.setVisible(is_ngram); w.setVisible(is_ngram)
        # 调整所在 CollapsibleSection 的内容刷新
        for sec in self._sections:
            if hasattr(sec, '_content') and sec._content:
                sec._content.update()

    def set_think_mode(self, mode: str):
        self._think_mode = mode

    def on_server_mode_toggle(self, checked: bool):
        mode_text = UI_LABELS.get("mode_server", "Server") if checked else UI_LABELS.get("mode_cli", "CLI")
        if hasattr(self, 'mode_label'):
            self.mode_label.setText(MSG.get("mode_label", "  |  模式: {mode}").replace("{mode}", mode_text))
        self.status_label.setText(MSG.get("mode_switched", "已切换至 {mode} 模式").replace("{mode}", mode_text))
        # 勾选状态立即落盘，避免切换语言重建 UI 后回滚
        self.config["is_server_mode"] = checked
        self.save_settings()

    def select_bin_dir(self):
        p = QFileDialog.getExistingDirectory(self, WIN_TITLES.get("select_bin", "选择 Bin 目录"),
                                               self.custom_widgets["bin_dir"].text())
        if p:
            self.custom_widgets["bin_dir"].setText(os.path.normpath(p))
            self.config["bin_dir"] = os.path.normpath(p)
            self.save_settings()
            self.detect_executables()

    def select_model_dir(self):
        p = QFileDialog.getExistingDirectory(self, WIN_TITLES.get("select_model", "选择模型目录"),
                                               self.custom_widgets["model_dir"].text())
        if p:
            self.custom_widgets["model_dir"].setText(os.path.normpath(p))
            self.config["model_dir"] = os.path.normpath(p)
            self.save_settings()
            self.refresh_models()

    def detect_executables(self):
        bin_dir = os.path.abspath(self.custom_widgets["bin_dir"].text())
        found = find_executables_in_dir(bin_dir)
        if not found:
            found = find_executables_in_dir(BASE_DIR, search_subdirs=True)
        if found:
            self.exe_label.setText(" | ".join(found))
        else:
            self.exe_label.setText(MSG.get("exe_not_found_alert", "⚠ 未找到 (请设置 Bin 目录)"))
        self._update_download_buttons()

    # ═══════════════════════════════════════════════
    #  下载
    # ═══════════════════════════════════════════════

    def _has_bin_files(self) -> bool:
        bin_dir = self.custom_widgets["bin_dir"].text()
        if not bin_dir or not os.path.isdir(bin_dir):
            bin_dir = BIN_DIR
        return has_executables(bin_dir)

    def _update_download_buttons(self):
        has_bin = self._has_bin_files()
        self.btn_fetch.setEnabled(True)
        if has_bin:
            self.btn_fetch.setToolTip(MSG.get("download_hint_has_bin", "已检测到可执行文件，可获取更新列表。"))
        else:
            self.btn_fetch.setToolTip(MSG.get("download_hint_no_bin", "获取当前平台可下载的 llama.cpp 二进制文件列表"))

    def _start_download(self, is_update: bool = False):
        if self._dl_thread and self._dl_thread.isRunning():
            self._dl_thread.cancel()
            self.btn_fetch.setText(BTN.get("fetch_files", "📡 获取可用文件"))
            self.status_label.setText(MSG.get("download_cancelled", "下载已取消"))
            return

        bin_dir = self.custom_widgets["bin_dir"].text()
        retry = self.config.get("retry_count", 3)
        timeout = self.config.get("dl_timeout", 300)

        if is_update and sys.platform == "win32":
            target_dir = os.path.abspath(bin_dir) if bin_dir and os.path.isdir(bin_dir) else os.path.abspath(BIN_DIR)
            os.makedirs(target_dir, exist_ok=True)
            import shutil
            for item in os.listdir(target_dir):
                item_path = os.path.join(target_dir, item)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.unlink(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                except Exception:
                    pass
            self.status_label.setText(MSG.get("update_cleared", "🗑 已清理旧 bin 文件，开始更新..."))

        self._dl_thread = ReleaseDownloadThread(
            bin_dir, backend_id="",
            retry_count=retry, timeout=timeout,
        )

        def _on_assets(available: list):
            while self._dl_list_layout.count():
                item = self._dl_list_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            for a in available:
                label = f"[{a['backend_label']}] {a['name']}  ({a['size']}MB)"
                btn = QPushButton(label)
                btn.setStyleSheet("QPushButton{text-align:left;padding:2px 6px;font-size:7.5pt;}")
                def _make_callback(asset):
                    return lambda: self._start_asset_download(asset)
                btn.clicked.connect(_make_callback(a))
                self._dl_list_layout.addWidget(btn)
            self._dl_list_widget.setVisible(True)
            self._dl_thread = None
            self.btn_fetch.setText(BTN.get("fetch_files", "📡 获取可用文件"))
            self.btn_fetch.setEnabled(True)
            self.console and self.console.append_output(
                f"📋 获取到 {len(available)} 个可用文件，在设置页点击下载", "green")
        self._dl_thread.assets_signal.connect(_on_assets)
        self._wire_dl_signals()

    def _start_asset_download(self, asset: dict):
        bin_dir = self.custom_widgets["bin_dir"].text()
        retry = self.config.get("retry_count", 3)
        timeout = self.config.get("dl_timeout", 300)
        self.status_label.setText(f"⬇ 下载: {asset['name']}")
        self._dl_thread = ReleaseDownloadThread(
            bin_dir, backend_id="",
            retry_count=retry, timeout=timeout,
        )
        self._dl_thread.set_asset(asset["name"], asset["url"], asset.get("size", 0))
        self._wire_dl_signals()

    def _wire_dl_signals(self):
        self._dl_thread.raw_signal.connect(lambda msg: (
            self.console and self.console.append_output(msg, "gray"),
        ))
        self._dl_thread.status_signal.connect(lambda msg: (
            self.status_label.setText(msg),
        ))
        self._dl_thread.progress_signal.connect(lambda cur, total: (
            self.progress_bar.setVisible(True),
            self.progress_bar.setMaximum(total),
            self.progress_bar.setValue(cur),
        ))
        self._dl_thread.finished_signal.connect(lambda path: (
            setattr(self, '_dl_thread', None),
            self.btn_fetch.setText(BTN.get("fetch_files", "📡 获取可用文件")),
            self.progress_bar.setVisible(False),
            self.status_label.setText(MSG.get("download_done", "✅ 下载完成")),
            self.detect_executables(),
            self._update_download_buttons(),
        ))
        self._dl_thread.error_signal.connect(lambda err: (
            setattr(self, '_dl_thread', None),
            self.btn_fetch.setText(BTN.get("fetch_files", "📡 获取可用文件")),
            self.progress_bar.setVisible(False),
            self.status_label.setText(MSG.get("download_failed", "❌ 下载失败")),
            self.console and self.console.append_output(err, "red"),
        ))
        self._dl_thread.start()
        self.btn_fetch.setText(BTN.get("stop_download", "⏹ 停止下载"))
        self.btn_stop.setEnabled(True)

    # ═══════════════════════════════════════════════
    #  显存检测
    # ═══════════════════════════════════════════════

    def show_auto_ngl(self):
        if self._vram_thread and self._vram_thread.isRunning():
            return
        self.vram_label.setText(MSG.get("vram_detecting_label", "VRAM: 检测中..."))
        self._vram_thread = VramCheckThread()
        self._vram_thread.result_signal.connect(self.on_vram_result)
        self._vram_thread.start()

    def on_vram_result(self, total: int, free: int):
        used = total - free
        self.vram_label.setText(
            MSG.get("vram_label", "VRAM: 已用 {used} / 总计 {total} MiB")
            .replace("{used}", str(used)).replace("{total}", str(total)))

    # ═══════════════════════════════════════════════
    #  模型刷新
    # ═══════════════════════════════════════════════

    def refresh_models(self):
        path = self.custom_widgets["model_dir"].text()
        self.full_paths.clear()
        display = []
        try:
            if os.path.exists(path):
                grouped = {}
                for root, dirs, files in os.walk(path):
                    gguf = [f for f in files if f.lower().endswith(".gguf")]
                    if gguf:
                        rd = os.path.relpath(root, path).replace("\\", "/")
                        grouped[rd] = sorted(gguf)
                for f in grouped.pop(".", []):
                    n = f"📄 {f}"
                    display.append(n)
                    self.full_paths[n] = f
                for folder in sorted(grouped.keys()):
                    ft = f"📂 {folder}/"
                    display.append(ft)
                    self.full_paths[ft] = "__DIRECTORY__"
                    for f in grouped[folder]:
                        fd = f"    {f}"
                        display.append(fd)
                        self.full_paths[fd] = f"{folder}/{f}"
        except Exception as e:
            self.status_label.setText(
                MSG.get("refresh_error", "刷新出错: {error}").replace("{error}", str(e)))

        combo = self.get_combo()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(display)
        combo.blockSignals(False)

        last = self.config.get("last_model", "")
        if last in display:
            combo.setCurrentText(last)
        else:
            self.select_first_valid_model()
        cnt = sum(1 for v in self.full_paths.values() if v != "__DIRECTORY__")
        self.status_label.setText(
            MSG.get("refresh_done", "已刷新: {count} 个模型").replace("{count}", str(cnt)))

    def select_first_valid_model(self):
        combo = self.get_combo()
        for i in range(combo.count()):
            if self.full_paths.get(combo.itemText(i)) != "__DIRECTORY__":
                combo.setCurrentIndex(i)
                return

    # ═══════════════════════════════════════════════
    #  预设管理
    # ═══════════════════════════════════════════════

    def _load_widget_from_state(self, widget, val):
        """将预设值写入单个控件。"""
        if isinstance(widget, QLineEdit):
            widget.setText(str(val))
        elif isinstance(widget, QDoubleSpinBox):
            try: widget.setValue(float(val))
            except: pass
        elif isinstance(widget, QSpinBox):
            try: widget.setValue(int(val))
            except: pass
        elif isinstance(widget, QCheckBox):
            if isinstance(val, str):
                widget.setChecked(val.strip().lower() in ("true", "1", "yes", "on"))
            else:
                widget.setChecked(bool(val))
        elif isinstance(widget, QComboBox):
            widget.setCurrentText(str(val))

    def _reset_widget_to_default(self, widget, default):
        """将控件重置为默认值。"""
        if isinstance(widget, QLineEdit):
            widget.setText(str(default))
        elif isinstance(widget, QDoubleSpinBox):
            try: widget.setValue(float(default))
            except: widget.setValue(0.0)
        elif isinstance(widget, QSpinBox):
            try: widget.setValue(int(default))
            except: widget.setValue(0)
        elif isinstance(widget, QCheckBox):
            widget.setChecked(bool(default))
        elif isinstance(widget, QComboBox):
            if isinstance(default, str) and default in [widget.itemText(i) for i in range(widget.count())]:
                widget.setCurrentText(default)
            elif widget.count() > 0:
                widget.setCurrentIndex(0)

    def on_model_change(self, index: int):
        combo = self.get_combo()
        name  = combo.currentText()
        if not name:
            return
        presets = self.config.get("presets", {})
        self.config["last_model"] = name

        if name in presets:
            p = presets[name]
            # 加载所有 dynamic_vars
            for pid, widget in self.dynamic_vars.items():
                if pid in p:
                    self._load_widget_from_state(widget, p[pid])
            # 加载所有 custom_widgets
            for cid, widget in self.custom_widgets.items():
                if cid in p:
                    self._load_widget_from_state(widget, p[cid])
            # 加载 think_mode（radio buttons）
            mode = p.get("think_mode", "normal")
            self._think_mode = mode
            for rb_val in ("normal", "hide", "stop"):
                rb = getattr(self, f"radio_{rb_val}", None)
                if rb:
                    rb.setChecked(rb_val == mode)
        else:
            # 无预设 → 重置为 JSON 默认值。
            # 重置期间阻断信号，避免 checkbox/radio/text 的回调把默认值
            # 写回配置并落盘（覆盖用户的 is_server_mode/mmproj 等设置）
            _suspend = [w for w in list(self.dynamic_vars.values()) + list(self.custom_widgets.values())
                        if isinstance(w, (QCheckBox, QLineEdit))]
            for rb_val in ("normal", "hide", "stop"):
                rb = getattr(self, f"radio_{rb_val}", None)
                if rb:
                    _suspend.append(rb)
            for w in _suspend:
                w.blockSignals(True)
            try:
                for group in DYNAMIC_UI_SCHEMA:
                    for param in group["params"]:
                        pid = param["id"]
                        w   = self.dynamic_vars.get(pid)
                        if w:
                            self._reset_widget_to_default(w, param.get("default", ""))
                # 重置 custom_widgets（从 UI_SECTIONS JSON 读取默认值）
                for section in UI_SECTIONS:
                    for ctrl in section.get("controls", []):
                        cid = ctrl.get("id", "")
                        w = self.custom_widgets.get(cid)
                        if w and "default" in ctrl:
                            self._reset_widget_to_default(w, ctrl["default"])
                # 重置 radio buttons 为 normal
                self._think_mode = "normal"
                for rb_val in ("normal", "hide", "stop"):
                    rb = getattr(self, f"radio_{rb_val}", None)
                    if rb:
                        rb.setChecked(rb_val == "normal")
                # 重置 file 字段为空
                for cid in ("mmproj", "model_draft"):
                    w = self.custom_widgets.get(cid)
                    if w and isinstance(w, QLineEdit):
                        w.setText("")
            finally:
                for w in _suspend:
                    w.blockSignals(False)

        self.status_label.setText(
            MSG.get("preset_loaded", "已加载配置: {name}").replace("{name}", name.strip()))

    def save_current_preset(self):
        combo = self.get_combo()
        name  = combo.currentText()
        if not name:
            return
        state = {}
        # 保存所有 dynamic_vars
        for pid, widget in self.dynamic_vars.items():
            if isinstance(widget, QLineEdit):
                state[pid] = widget.text()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                state[pid] = widget.value()
            elif isinstance(widget, QCheckBox):
                state[pid] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                state[pid] = widget.currentText()
        # 保存所有 custom_widgets（checkbox/text/radio 等）
        for cid, widget in self.custom_widgets.items():
            if isinstance(widget, QLineEdit):
                state[cid] = widget.text()
            elif isinstance(widget, QCheckBox):
                state[cid] = widget.isChecked()
        state["think_mode"] = self._think_mode
        # 保存到预置字典
        self.config.setdefault("presets", {})[name] = state
        # 同时更新全局 config 持久字段
        self.config.update({
            "bin_dir":        self.custom_widgets.get("bin_dir", QLineEdit()).text(),
            "model_dir":      self.custom_widgets.get("model_dir", QLineEdit()).text(),
            "last_port":      self.custom_widgets.get("port", QLineEdit()).text(),
            "is_server_mode": self.custom_widgets.get("is_server_mode", QCheckBox()).isChecked(),
            "auto_open_browser": self.custom_widgets.get("auto_open_browser", QCheckBox()).isChecked(),
            "global_args":    self.custom_widgets.get("global_args", QLineEdit()).text(),
            "last_model":     name,
        })
        self.save_settings()

    def delete_current_preset(self):
        combo = self.get_combo()
        name  = combo.currentText()
        if not name:
            return
        if self.full_paths.get(name) == "__DIRECTORY__":
            QMessageBox.information(self,
                WIN_TITLES.get("preset_info_title", "提示"),
                MSG.get("preset_folder", "当前选中的是文件夹标题。"))
            return
        presets = self.config.get("presets", {})
        if name not in presets:
            QMessageBox.information(self,
                WIN_TITLES.get("preset_info_title", "提示"),
                MSG.get("preset_no_preset", "「{name}」没有预设。").replace("{name}", name.strip()))
            return
        if QMessageBox.question(self,
                WIN_TITLES.get("preset_confirm_title", "确认删除"),
                MSG.get("preset_confirm_msg", "确定删除「{name}」的预设吗？").replace("{name}", name.strip()),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            del presets[name]
            self.save_settings()
            self.status_label.setText(
                MSG.get("preset_deleted", "已删除预设: {name}").replace("{name}", name.strip()))
            self.on_model_change(combo.currentIndex())

    # ═══════════════════════════════════════════════
    #  窗口几何
    # ═══════════════════════════════════════════════

    def closeEvent(self, event):
        self._save_window_geometry()
        self.config["_font_scale"] = self._font_scale
        self.save_settings()
        self.save_current_preset()
        if self._dl_thread and self._dl_thread.isRunning():
            self._dl_thread.cancel()
            self._dl_thread.wait(3000)
            # 网络阻塞时协作式取消可能超时，退出前强制终止避免线程随进程销毁
            if self._dl_thread.isRunning():
                self._dl_thread.terminate()
                self._dl_thread.wait(1000)
        if self.launch_thread and self.launch_thread.isRunning():
            w = self.custom_widgets.get("console_mode")
            if w is None or not w.isChecked():
                self.console.append_output("🔄 关闭窗口，正在终止进程...", "yellow")
                self.launch_thread.stop()
                self.launch_thread.wait(3000)
                self.console.append_output("✅ 进程已终止", "green")
        super().closeEvent(event)

    def _save_window_geometry(self):
        try:
            geo = self.saveGeometry()
            if geo:
                self.config["window_geometry"] = geo.toBase64().data().decode("ascii")
            state = self.windowState()
            self.config["window_state"] = int(state)
            self.config["window_width"] = self.width()
            self.config["window_height"] = self.height()
        except Exception:
            pass

    def _restore_window_geometry(self):
        saved_font_scale = self.config.get("_font_scale")
        if saved_font_scale is not None:
            self._font_scale = float(saved_font_scale)
        try:
            geo_b64 = self.config.get("window_geometry")
            if geo_b64:
                geo = QByteArray.fromBase64(geo_b64.encode("ascii"))
                if not geo.isEmpty():
                    self.restoreGeometry(geo)
            state_val = self.config.get("window_state")
            if state_val is not None:
                self.setWindowState(self.windowState() | state_val)
        except Exception:
            pass
        if not self.config.get("window_geometry"):
            w = self.config.get("window_width", 960)
            h = self.config.get("window_height", 600)
            self.resize(w, h)

    # ═══════════════════════════════════════════════
    #  自适应字体缩放
    # ═══════════════════════════════════════════════

    def resizeEvent(self, event):
        if not self.config.get("auto_scale", True):
            super().resizeEvent(event)
            return
        if self._resize_timer is None:
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self._apply_font_scale)
        if self._resize_throttle_timer is None:
            self._resize_throttle_timer = QTimer(self)
            self._resize_throttle_timer.setSingleShot(True)
            self._resize_throttle_timer.timeout.connect(self._apply_font_scale)
        if not self._resize_throttle_timer.isActive():
            self._apply_font_scale()
            self._resize_throttle_timer.start(80)
        self._resize_timer.start(200)
        super().resizeEvent(event)

    def _apply_font_scale(self):
        ref_width = REF_WIDTH_FOR_SCALE
        window_scale = max(0.35, min(1.50, self.width() / ref_width))
        if abs(window_scale - self._font_scale) < 0.03:
            return
        self._font_scale = window_scale
        theme = self.config.get("theme", "dark")
        self._apply_full_stylesheet(theme)
        app = QApplication.instance()
        if app:
            af = app.font()
            af.setPointSizeF(max(6.5, 9.0 * window_scale))
            app.setFont(af)
        if hasattr(self, 'console') and self.console:
            combined = window_scale * self.config.get("ui_scale", 1.0)
            cf = self.console.output.font()
            cf.setPointSizeF(max(5.5, 9.0 * combined))
            self.console.output.setFont(cf)

    def _reset_font_scale(self):
        """关闭自适应缩放时恢复基础字号。"""
        self._font_scale = 1.0
        theme = self.config.get("theme", "dark")
        self._apply_full_stylesheet(theme)
        app = QApplication.instance()
        if app:
            af = app.font()
            af.setPointSize(9)
            app.setFont(af)
        if hasattr(self, 'console') and self.console:
            cf = self.console.output.font()
            cf.setPointSize(9)
            self.console.output.setFont(cf)

    # ═══════════════════════════════════════════════
    #  字体加载
    # ═══════════════════════════════════════════════

    def _select_font_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择字体文件",
            self.config.get("font_path", ""),
            "字体文件 (*.ttf *.otf);;所有文件 (*)")
        if path:
            self.custom_widgets["font_path"].setText(path)
            self.config["font_path"] = path
            self._load_custom_font()
            self.save_settings()
            self.apply_theme()

    def _load_custom_font(self):
        font_path = self.config.get("font_path", "")
        self._custom_font_family = None
        self._sheet_cache.clear()
        if not font_path or not os.path.isfile(font_path):
            return
        try:
            db = QFontDatabase()
            font_id = db.addApplicationFont(font_path)
            if font_id >= 0:
                families = db.applicationFontFamilies(font_id)
                if families:
                    family = families[0]
                    self._custom_font_family = family
                    app = QApplication.instance()
                    if app:
                        f = QFont(family, 9)
                        f.setStyleStrategy(QFont.StyleStrategy.PreferQuality | QFont.StyleStrategy.PreferAntialias)
                        f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
                        app.setFont(f)
                    self.status_label.setText(
                        MSG.get("font_loaded", "已加载字体: {name}").replace("{name}", family))
            else:
                self.status_label.setText(
                    MSG.get("font_load_failed", "字体加载失败: {path}").replace("{path}", os.path.basename(font_path)))
        except Exception as e:
            self.status_label.setText(
                MSG.get("font_error", "字体错误: {err}").replace("{err}", str(e)))

    # ═══════════════════════════════════════════════
    #  可执行文件查找
    # ═══════════════════════════════════════════════

    def find_executable(self, is_server: bool = False) -> Optional[str]:
        _exe_suffix = ".exe" if sys.platform == "win32" else ""
        target = f"llama-server{_exe_suffix}" if is_server else f"llama-cli{_exe_suffix}"
        target_lower = target.lower()
        bin_dir = os.path.abspath(self.custom_widgets["bin_dir"].text())
        if os.path.isdir(bin_dir):
            p = os.path.join(bin_dir, target)
            if os.path.isfile(p):
                return p
            for exe in COMMON_EXES:
                p = os.path.join(bin_dir, exe)
                if os.path.isfile(p):
                    return p
        all_lower = [x.lower() for x in COMMON_EXES]
        for root, _, files in os.walk(BASE_DIR):
            for f in files:
                fl = f.lower()
                if fl == target_lower or fl in all_lower:
                    found = os.path.join(root, f)
                    self.custom_widgets["bin_dir"].setText(root)
                    self.config["bin_dir"] = root
                    self.save_settings()
                    return found
        return None

    # ═══════════════════════════════════════════════
    #  构建命令
    # ═══════════════════════════════════════════════

    def build_command_args(self) -> Optional[list]:
        combo    = self.get_combo()
        name     = combo.currentText()
        rel_path = self.full_paths.get(name)
        if not rel_path or rel_path == "__DIRECTORY__":
            QMessageBox.warning(self, WIN_TITLES.get("startup_error_title", "启动错误"),
                MSG.get("startup_error_no_model", "请选择具体的模型文件。"))
            return None

        is_server = self.custom_widgets["is_server_mode"].isChecked()
        exe = self.find_executable(is_server)
        if not exe:
            QMessageBox.critical(self, WIN_TITLES.get("startup_error_title", "启动错误"),
                MSG.get("startup_error_no_exe", "找不到可执行文件，请检查 Bin 目录。"))
            return None

        model_path = os.path.abspath(os.path.normpath(
            os.path.join(self.custom_widgets["model_dir"].text(), rel_path)))
        if not os.path.exists(model_path):
            QMessageBox.critical(self, WIN_TITLES.get("startup_error_title", "启动错误"),
                MSG.get("startup_error_model_missing", "模型文件不存在:\n{path}").replace("{path}", model_path))
            return None

        args = [exe, "-m", model_path]

        current_spec_type = ""
        spec_w = self.dynamic_vars.get("spec_type")
        if isinstance(spec_w, QComboBox):
            current_spec_type = spec_w.currentText().strip()

        for group in DYNAMIC_UI_SCHEMA:
            for param in group["params"]:
                pid = param["id"]
                w   = self.dynamic_vars[pid]

                if pid == "spec_draft_n_max" and not current_spec_type.startswith("draft-"):
                    continue
                if pid.startswith("spec_ngram_") and not current_spec_type.startswith("ngram-"):
                    continue

                if isinstance(w, QCheckBox):
                    if param.get("type") == "check":
                        val = param.get("checked_val", "on") if w.isChecked() else param.get("unchecked_val", "off")
                        args.extend([param["arg"], val])
                    else:
                        if w.isChecked():
                            bv = param.get("bool_val")
                            if bv:
                                args.extend([param["arg"], bv])
                            else:
                                args.append(param["arg"])
                elif isinstance(w, QComboBox):
                    val = w.currentText().strip()
                    # spec_type="none" 表示不启用投机解码，跳过传参
                    if pid == "spec_type" and val == "none":
                        continue
                    if val:
                        if not self._validate_arg(val):
                            QMessageBox.warning(self, WIN_TITLES.get("param_error_title", "参数错误"),
                                MSG.get("invalid_param_value", "参数 {name} 包含不安全字符").replace("{name}", pid))
                            return None
                        args.extend([param["arg"], val])
                else:
                    if isinstance(w, QLineEdit):
                        val = w.text().strip()
                        if not val:
                            continue
                        if not self._validate_arg(val):
                            QMessageBox.warning(self, WIN_TITLES.get("param_error_title", "参数错误"),
                                MSG.get("invalid_param_value", "参数 {name} 包含不安全字符").replace("{name}", pid))
                            return None
                        args.extend([param["arg"], val])
                    elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                        val = w.value()
                        if val == 0:
                            continue
                        args.extend([param["arg"], str(val)])

        if is_server:
            port = self.custom_widgets["port"].text().strip()
            if not self._validate_port(port):
                QMessageBox.warning(self, WIN_TITLES.get("param_error_title", "参数错误"),
                    MSG.get("invalid_port", "端口号无效，必须是 1-65535 之间的整数。"))
                return None
            args += ["--port", port]
        else:
            args += ["--color", "on", "-cnv"]

        mode   = self._think_mode
        budget = self.custom_widgets["think_budget"].text().strip()
        if budget and not self._validate_number(budget, allow_negative=False):
            QMessageBox.warning(self, WIN_TITLES.get("param_error_title", "参数错误"),
                MSG.get("invalid_budget", "思考 Token 限制必须是非负整数。"))
            return None
        if mode == "normal":
            args += ["--reasoning", "on"]
            if budget and budget != "0":
                args += ["--reasoning-budget", budget]
        elif mode == "hide":
            args += ["--reasoning-format", "none", "--reasoning-budget", "0", "-rea", "off"]
        elif mode == "stop":
            args += ["--reasoning-format", "none", "-r", "</think>",
                     "--reasoning-budget", budget or "0"]

        mmproj = self.custom_widgets["mmproj"].text().strip()
        mmproj_cb = self.custom_widgets.get("mmproj_cb", QCheckBox())
        if mmproj and mmproj_cb.isChecked():
            if os.path.exists(mmproj):
                args += ["--mmproj", os.path.normpath(mmproj)]
            else:
                QMessageBox.warning(self, WIN_TITLES.get("warning_title", "警告"),
                    MSG.get("startup_warning_mmproj", "MMProj 文件不存在:\n{path}").replace("{path}", mmproj))

        model_draft = self.custom_widgets.get("model_draft", QLineEdit()).text().strip()
        draft_cb = self.custom_widgets.get("draft_cb", QCheckBox())
        if model_draft and draft_cb.isChecked() and current_spec_type.startswith("draft-"):
            if os.path.exists(model_draft):
                args += ["--model-draft", os.path.normpath(model_draft)]
            else:
                QMessageBox.warning(self, WIN_TITLES.get("warning_title", "警告"),
                    MSG.get("startup_warning_model_draft", "Draft 模型文件不存在:\n{path}").replace("{path}", model_draft))

        ga = self.custom_widgets["global_args"].text().strip()
        if ga:
            ga_parts = self._split_args(ga)
            for part in ga_parts:
                if not self._validate_arg(part):
                    QMessageBox.warning(self, WIN_TITLES.get("param_error_title", "参数错误"),
                        MSG.get("invalid_global_args", "全局参数包含不安全字符: {arg}").replace("{arg}", part[:50]))
                    return None
            args += ga_parts
        ca = self.custom_widgets["custom_args"].text().strip()
        if ca:
            ca_parts = self._split_args(ca)
            for part in ca_parts:
                if not self._validate_arg(part):
                    QMessageBox.warning(self, WIN_TITLES.get("param_error_title", "参数错误"),
                        MSG.get("invalid_custom_args", "模型专属参数包含不安全字符: {arg}").replace("{arg}", part[:50]))
                    return None
            args += ca_parts

        return args

    @staticmethod
    def _validate_arg(arg: str) -> bool:
        dangerous_chars = [';', '|', '&', '$', '`', '\n', '\r', '{', '}', '<', '>']
        return not any(c in arg for c in dangerous_chars)

    @staticmethod
    def _validate_port(port_str: str) -> bool:
        try:
            port = int(port_str)
            return 1 <= port <= 65535
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _validate_number(value: str, allow_negative: bool = False) -> bool:
        try:
            num = float(value)
            return allow_negative or num >= 0
        except (ValueError, TypeError):
            return False

    def _split_args(self, s: str) -> list:
        r = []
        i = 0
        while i < len(s):
            c = s[i]
            if c in ('"', "'"):
                quote = c
                i += 1
                start = i
                while i < len(s) and s[i] != quote:
                    i += 1
                r.append(s[start:i])
                if i < len(s):
                    i += 1
            elif c == ' ':
                i += 1
            else:
                start = i
                while i < len(s) and s[i] != ' ':
                    i += 1
                r.append(s[start:i])
        return r

    # ═══════════════════════════════════════════════
    #  命令预览
    # ═══════════════════════════════════════════════

    def show_command_preview(self) -> None:
        args = self.build_command_args()
        if args is None:
            return
        theme = str(self.config.get("theme", "dark"))
        dlg = CommandPreviewDialog(args, self, theme=theme)
        dlg.exec()

    # ═══════════════════════════════════════════════
    #  启动逻辑
    # ═══════════════════════════════════════════════

    def launch(self) -> None:
        self.save_current_preset()
        args = self.build_command_args()
        if args is None:
            return

        is_server = self.custom_widgets["is_server_mode"].isChecked()
        use_console = self.custom_widgets["console_mode"].isChecked()

        if self.launch_thread and self.launch_thread.isRunning():
            old = self.launch_thread
            for sig_name in ("output_signal", "finished_signal", "error_signal"):
                try:
                    getattr(old, sig_name).disconnect()
                except Exception:
                    pass
            self.console.append_output("⚠ 检测到旧进程，正在终止并重启...", "yellow")
            old.stop()
            old.finished.connect(
                lambda a=args, s=is_server, c=use_console: self._do_launch(a, s, c))
            return

        self._do_launch(args, is_server, use_console)

    def _do_launch(self, args: list, is_server: bool, use_console: bool) -> None:
        if use_console:
            try:
                exe_name = os.path.basename(args[0])
                self.status_label.setText(
                    MSG.get("launch_console_mode", "🖥 外部控制台: {name}").replace("{name}", exe_name))
                self.console.append_output("=" * 60, "blue")
                self.console.append_output(f"🖥 启动外部控制台: {exe_name}", "blue")
                self.console.append_output(f"📂 工作目录: {os.path.dirname(args[0])}", "blue")
                self.console.append_output("=" * 60, "blue")
                self.progress_bar.setVisible(False)

                popen_kwargs = {
                    "cwd": os.path.dirname(args[0]),
                    "close_fds": True,
                }
                if sys.platform == "win32":
                    popen_kwargs["creationflags"] = CREATE_NEW_CONSOLE
                subprocess.Popen(args, **popen_kwargs)
                self.console.append_output(
                    MSG.get("launch_console_started", "✅ 外部控制台已打开，进程独立运行中。"), "green")
            except Exception as e:
                self._recover_buttons_from_error(
                    MSG.get("launch_failed", "❌ 启动失败: {error}").replace("{error}", str(e)))
            return

        try:
            self.tabs.setCurrentIndex(2)
            self.console.output.clear()
            self.console.append_output("=" * 60, "blue")
            self.console.append_output(f"🚀 启动命令: {os.path.basename(args[0])}", "blue")
            self.console.append_output(f"📂 工作目录: {os.path.dirname(args[0])}", "blue")
            self.console.append_output("=" * 60, "blue")

            exe_name = os.path.basename(args[0])
            self.status_label.setText(
                MSG.get("launch_starting", "⏳ 启动中: {name}...").replace("{name}", exe_name))
            self.progress_bar.setVisible(True)

            self.btn_launch.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self.btn_preview.setEnabled(False)
            QTimer.singleShot(3000, self._on_launch_ready)

            self._server_ready_opened = False
            work_dir = os.path.dirname(args[0])
            self.launch_thread = LaunchThread(args, work_dir)
            self.launch_thread.output_signal.connect(self._on_process_output)
            self.launch_thread.finished_signal.connect(self._on_process_finished)
            self.launch_thread.error_signal.connect(self._on_process_error)
            self.launch_thread.start()

            QTimer.singleShot(2000, self._check_launch_status)
        except Exception as e:
            self._recover_buttons_from_error(
                MSG.get("launch_failed", "❌ 启动失败: {error}").replace("{error}", str(e)))

    def _recover_buttons_from_error(self, msg: str):
        self.progress_bar.setVisible(False)
        self.btn_launch.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_preview.setEnabled(True)
        self.status_label.setText(msg)
        self.console.append_output(msg, "red")
        QMessageBox.critical(self, MSG.get("launch_failed", "启动失败"), msg)

    def _on_process_output(self, line: str):
        color = None
        if any(kw in line.lower() for kw in ["error", "fatal", "panic", "fail"]):
            color = "red"
        elif any(kw in line.lower() for kw in ["warn", "info:", "loaded", "llm"]):
            color = "yellow"
        self.console.append_output(line, color)

        # 同步日志到底部统一状态栏（取最后一行，截断到 80 字符）
        log_text = line.strip()[:80]
        if hasattr(self, 'log_label'):
            self.log_label.setText(log_text)

        is_server = self.custom_widgets["is_server_mode"].isChecked()
        if is_server and not self._server_ready_opened:
            if any(kw in line.lower() for kw in [
                "http server listening", "listening on", "starting the main loop",
                "server is listening", "accessible via url"]):
                port = self.custom_widgets["port"].text()
                url = f"http://127.0.0.1:{port}"
                self._server_ready_opened = True
                self.mode_label.setText(
                    MSG.get("server_ready_label", "✅ Server 运行中 | {url}").replace("{url}", url))
                # 自动打开浏览器（如果启用）
                auto_br = self.custom_widgets.get("auto_open_browser", QCheckBox())
                if auto_br and auto_br.isChecked():
                    try:
                        webbrowser.open(url)
                        self.console.append_output(f"🌐 已自动打开浏览器 → {url}", "blue")
                    except Exception:
                        self.console.append_output(
                            f"🌐 请手动打开 {url}", "yellow")
                self.console.append_output(
                    f"✅ 服务器已就绪，访问 {url} 使用", "green")
                self.status_label.setText(f"🟢 Server 就绪 | 端口 {port}")

    def _on_console_input(self, text: str):
        if self.launch_thread and self.launch_thread.isRunning():
            self.console.append_output(f">>> {text}", "green")
            self.launch_thread.send_input(text)

    def _check_launch_status(self):
        if self.launch_thread and self.launch_thread.isRunning():
            self.status_label.setText(MSG.get("launch_running", "进程已在后台运行中"))

    def _on_launch_ready(self):
        if self.launch_thread and self.launch_thread.isRunning():
            self.btn_launch.setEnabled(True)
            self.btn_preview.setEnabled(True)
            self.status_label.setText(
                MSG.get("launch_running", "进程已在后台运行中"))

    def _on_process_finished(self, rc: int):
        self.progress_bar.setVisible(False)
        self.btn_launch.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_preview.setEnabled(True)
        if rc == 0:
            self.status_label.setText(MSG.get("launch_exit_ok", "✅ 进程已正常退出"))
        else:
            self.status_label.setText(
                MSG.get("launch_exit_fail", "⚠ 进程退出 (返回码 {code})").replace("{code}", str(rc)))

    def _on_process_error(self, err: str):
        self.progress_bar.setVisible(False)
        self.btn_launch.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_preview.setEnabled(True)
        self.status_label.setText(MSG.get("launch_failed", "❌ 启动失败"))
        QMessageBox.critical(self, MSG.get("launch_failed", "启动失败"), err)

    def stop_launch(self) -> None:
        stopped = False
        if self.launch_thread and self.launch_thread.isRunning():
            self.launch_thread.stop()
            self.launch_thread.finished.connect(lambda: setattr(self, 'launch_thread', None))
            self.status_label.setText(MSG.get("launch_stopping", "⏹ 正在停止进程..."))
            stopped = True
        if self._dl_thread and self._dl_thread.isRunning():
            dl = self._dl_thread
            dl.cancel()
            # 保留引用直到线程结束，避免运行中销毁 QThread 触发 abort
            dl.finished.connect(lambda: self._on_dl_thread_done(dl))
            self._dl_thread = None
            self.btn_fetch.setText(BTN.get("fetch_files", "📡 获取可用文件"))
            self.status_label.setText(MSG.get("download_cancelled", "下载已取消"))
            stopped = True
        if stopped:
            self.btn_stop.setEnabled(False)

    def _on_dl_thread_done(self, dl):
        if self._dl_thread is dl:
            self._dl_thread = None
        self.progress_bar.setVisible(False)
        self.btn_fetch.setText(BTN.get("fetch_files", "📡 获取可用文件"))


# ═══════════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════════

def main():
    if sys.platform == "win32":
        try:
            import PySide6
            _pkg = os.path.dirname(PySide6.__file__)
            _bin = os.path.join(_pkg, "Qt6", "bin")
            if os.path.isdir(_bin):
                os.add_dll_directory(_bin)
            _plugins = os.path.join(_pkg, "Qt6", "plugins")
            if os.path.isdir(_plugins):
                os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = _plugins
            # Qt 6 已原生支持每监视器 DPI 感知，无需手动调用 SetProcessDpiAwareness
            # 移除旧的 ctypes 调用避免与 Qt 内置 DPI 上下文冲突
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    # Qt 6 自动按监视器处理 DPI，无需额外设置

    # ── 字体渲染优化 ──
    _setup_app_font(app)

    # ── 深色主题调色板（利用 Qt 6 Fusion 原生 QPalette，比纯 QSS 更稳定）──
    _apply_dark_palette(app)

    window = LlamaProLauncher()
    window.show()
    sys.exit(app.exec())


def _setup_app_font(app):
    """Qt 6 字体优化：抗锯齿 + 无 hinting，匹配系统渲染。"""
    f = app.font()
    f.setStyleStrategy(QFont.StyleStrategy.PreferQuality | QFont.StyleStrategy.PreferAntialias)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    f.setFamilies(["Microsoft YaHei", "Segoe UI", "Noto Sans SC", "sans-serif"])
    f.setPointSize(9)
    app.setFont(f)


def _apply_dark_palette(app):
    """Qt 6 Fusion 深色调色板：在 QSS 之下提供全局基础色，减少 QSS 闪烁。"""
    from PySide6.QtGui import QPalette, QColor
    pal = QPalette()

    dark_bg = QColor("#1e1e2e")
    dark_surface = QColor("#252540")
    dark_base = QColor("#14142a")
    dark_text = QColor("#e0e0f0")
    dark_dim = QColor("#8080a0")
    dark_highlight = QColor("#3d88e0")
    dark_button = QColor("#2a2a40")
    dark_bright = QColor("#ffffff")

    pal.setColor(QPalette.ColorRole.Window, dark_bg)
    pal.setColor(QPalette.ColorRole.WindowText, dark_text)
    pal.setColor(QPalette.ColorRole.Base, dark_base)
    pal.setColor(QPalette.ColorRole.AlternateBase, dark_surface)
    pal.setColor(QPalette.ColorRole.ToolTipBase, dark_surface)
    pal.setColor(QPalette.ColorRole.ToolTipText, dark_text)
    pal.setColor(QPalette.ColorRole.Text, dark_text)
    pal.setColor(QPalette.ColorRole.Button, dark_button)
    pal.setColor(QPalette.ColorRole.ButtonText, dark_text)
    pal.setColor(QPalette.ColorRole.BrightText, dark_bright)
    pal.setColor(QPalette.ColorRole.Highlight, dark_highlight)
    pal.setColor(QPalette.ColorRole.HighlightedText, dark_bright)
    pal.setColor(QPalette.ColorRole.Link, dark_highlight)
    pal.setColor(QPalette.ColorRole.Mid, QColor("#3a3a55"))
    pal.setColor(QPalette.ColorRole.Midlight, QColor("#353550"))
    pal.setColor(QPalette.ColorRole.Dark, QColor("#1a1a30"))
    pal.setColor(QPalette.ColorRole.Shadow, QColor("#0a0a18"))

    app.setPalette(pal)


def _apply_light_palette(app):
    """Qt 6 Fusion 浅色调色板：随主题切换，与 light_style.qss 配色一致。"""
    from PySide6.QtGui import QPalette, QColor
    pal = QPalette()

    light_bg = QColor("#f2f3f5")
    light_surface = QColor("#ffffff")
    light_base = QColor("#ffffff")
    light_text = QColor("#1e1e2e")
    light_dim = QColor("#666680")
    light_highlight = QColor("#3d88e0")
    light_button = QColor("#f0f2f5")
    light_bright = QColor("#000000")

    pal.setColor(QPalette.ColorRole.Window, light_bg)
    pal.setColor(QPalette.ColorRole.WindowText, light_text)
    pal.setColor(QPalette.ColorRole.Base, light_base)
    pal.setColor(QPalette.ColorRole.AlternateBase, light_surface)
    pal.setColor(QPalette.ColorRole.ToolTipBase, light_surface)
    pal.setColor(QPalette.ColorRole.ToolTipText, light_text)
    pal.setColor(QPalette.ColorRole.Text, light_text)
    pal.setColor(QPalette.ColorRole.Button, light_button)
    pal.setColor(QPalette.ColorRole.ButtonText, light_text)
    pal.setColor(QPalette.ColorRole.BrightText, light_bright)
    pal.setColor(QPalette.ColorRole.Highlight, light_highlight)
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.Link, light_highlight)
    pal.setColor(QPalette.ColorRole.Mid, QColor("#d4d6dc"))
    pal.setColor(QPalette.ColorRole.Midlight, QColor("#e8eaf0"))
    pal.setColor(QPalette.ColorRole.Dark, QColor("#c8ccd4"))
    pal.setColor(QPalette.ColorRole.Shadow, QColor("#a0a8b4"))

    app.setPalette(pal)


if __name__ == "__main__":
    main()
