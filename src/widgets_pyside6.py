"""
PySide6 自定义控件模块：折叠面板、自适应下拉框、控制台面板、命令预览对话框。
"""
import os
import sys
import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QDialog, QApplication, QFileDialog, QMessageBox, QSizePolicy,
    QListWidget, QListView, QFrame, QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont

from .platform import save_script
from .config import (MSG, BTN, PH, WIN_TITLES, CONSOLE_COLORS,
                     MAX_COMBO_ITEMS, DEFAULT_ITEM_HEIGHT)


# ═══════════════════════════════════════════════
#  CollapsibleSection
# ═══════════════════════════════════════════════

class CollapsibleSection(QWidget):
    """可点击标题栏展开/收纳的折叠面板，使用 opacity 淡入淡出避免布局抖动。"""

    def __init__(self, title: str, content: QWidget, section_key: str = "",
                 collapsed: bool = False, parent=None):
        super().__init__(parent)
        self._key       = section_key
        self._collapsed = collapsed
        self._content   = content
        self._animating = False

        # 标题栏
        header = QWidget()
        header.setObjectName("collapsibleHeader")
        header.setFixedHeight(28)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(8, 0, 8, 0)
        h_layout.setSpacing(6)

        self._arrow_label = QLabel()
        self._arrow_label.setObjectName("collapsibleArrow")
        self._arrow_label.setFixedWidth(18)
        self._arrow_label.setMinimumWidth(18)
        self._arrow_label.setAlignment(Qt.AlignCenter)
        self._arrow_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("collapsibleTitle")
        self._title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        h_layout.addWidget(self._arrow_label, 0, Qt.AlignLeft | Qt.AlignVCenter)
        h_layout.addWidget(self._title_label)

        header.setCursor(Qt.PointingHandCursor)
        header.mousePressEvent = lambda e: self._toggle()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self._content)

        # 透明度动画：只影响视觉效果，不触发布局重算，彻底消除窗口抖动
        self._opacity = QGraphicsOpacityEffect(self._content)
        self._content.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity")
        self._fade.setDuration(150)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.finished.connect(self._on_fade_finished)

        self.set_collapsed(collapsed, animate=False, update_header=True)

    def _toggle(self):
        if self._animating:
            return
        self.set_collapsed(not self._collapsed, animate=True)

    def _on_fade_finished(self):
        self._animating = False
        if self._collapsed:
            self._content.setVisible(False)
        self._opacity.setOpacity(1.0 if not self._collapsed else 0.0)

    def set_collapsed(self, collapsed: bool, animate: bool = True, update_header: bool = True):
        self._collapsed = collapsed
        if update_header:
            self._arrow_label.setText("▶" if collapsed else "▼")
            f = self._arrow_label.font()
            f.setPointSize(8 if collapsed else 10)
            self._arrow_label.setFont(f)

        # 非动画模式（初始化时）：直接设置可见性，避免启动时折叠段闪烁
        if not animate:
            self._animating = False
            self._content.setVisible(not collapsed)
            self._opacity.setOpacity(1.0 if not collapsed else 0.0)
            return

        if collapsed:
            self._animating = True
            self._fade.stop()
            self._fade.setStartValue(self._opacity.opacity())
            self._fade.setEndValue(0.0)
            self._fade.start()
        else:
            self._content.setVisible(True)
            self._animating = True
            self._fade.stop()
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.start()


# ═══════════════════════════════════════════════
#  控件类
# ═══════════════════════════════════════════════

class NoWheelSpinBox(QSpinBox):
    """QSpinBox 子类：禁用鼠标滚轮更改数值。"""
    def wheelEvent(self, event):
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox 子类：禁用鼠标滚轮更改数值。"""
    def wheelEvent(self, event):
        event.ignore()


# ── 下拉弹窗样式表（暗色） ──
_POPUP_DARK_QSS = """
    QFrame#dropdownFrame {
        background: #252540;
        border: 1px solid #4a4a6a;
        border-radius: 5px;
    }
    QListWidget {
        background: transparent;
        color: #e0e0f0;
        border: none;
        outline: none;
        font-size: 8.5pt;
    }
    QListWidget::item {
        padding: 4px 10px;
        min-height: 22px;
        border-radius: 3px;
    }
    QListWidget::item:hover {
        background: #363658;
    }
    QListWidget::item:selected {
        background: #3d5575;
        color: #ffffff;
    }
"""
_POPUP_LIGHT_QSS = """
    QFrame#dropdownFrame {
        background: #ffffff;
        border: 1px solid #c8ccd4;
        border-radius: 5px;
    }
    QListWidget {
        background: transparent;
        color: #1e1e2e;
        border: none;
        outline: none;
        font-size: 8.5pt;
    }
    QListWidget::item {
        padding: 4px 10px;
        min-height: 22px;
        border-radius: 3px;
    }
    QListWidget::item:hover {
        background: #eef2f8;
    }
    QListWidget::item:selected {
        background: #dce8f8;
        color: #1e1e2e;
    }
"""


class AdaptiveComboBox(QComboBox):
    """自定义下拉框 — 完全接管弹窗行为，使用 QFrame+QListWidget 替代
    Qt 6 QComboBox 原生弹窗，避免 Fusion 风格下的渲染问题。"""

    # 类级主题跟踪（由主窗口切换主题时更新）
    _theme = "dark"

    @classmethod
    def set_theme(cls, theme: str):
        cls._theme = theme

    def __init__(self, parent=None):
        super().__init__(parent)
        # 创建自定义弹窗（不依赖 QComboBox 原生弹窗机制）。
        # 弹窗以自身为父对象：随 ComboBox 销毁，避免 _rebuild_ui 后孤儿弹窗泄漏
        self._popup_frame = QFrame(self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._popup_frame.setObjectName("dropdownFrame")
        self._popup_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._update_popup_style()

        ply = QVBoxLayout(self._popup_frame)
        ply.setContentsMargins(4, 4, 4, 4)
        ply.setSpacing(0)

        self._popup_list = QListWidget()
        self._popup_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self._popup_list.itemClicked.connect(self._on_item_clicked)
        self._popup_list.itemActivated.connect(self._on_item_clicked)
        # Escape 关闭弹窗（Qt::Popup 不自动处理 Escape）
        self._popup_list.keyPressEvent = self._popup_key_press
        ply.addWidget(self._popup_list)

        # 避免默认弹窗干扰
        self.setMaxVisibleItems(1)

    def _update_popup_style(self):
        """根据当前主题刷新弹窗样式。"""
        qss = _POPUP_DARK_QSS if self._theme == "dark" else _POPUP_LIGHT_QSS
        self._popup_frame.setStyleSheet(qss)

    # ── 公开 API 兼容 ──

    def addItems(self, texts):
        super().addItems(texts)

    def clear(self):
        super().clear()

    def currentText(self) -> str:
        return super().currentText()

    def setCurrentText(self, text: str):
        super().setCurrentText(text)

    def currentIndex(self) -> int:
        return super().currentIndex()

    def setCurrentIndex(self, idx: int):
        super().setCurrentIndex(idx)

    def count(self) -> int:
        return super().count()

    def itemText(self, idx: int) -> str:
        return super().itemText(idx)

    # ── 滚轮：仅在弹出状态下滚轮生效 ──

    def wheelEvent(self, event):
        if self._popup_frame and self._popup_frame.isVisible():
            event.accept()
        else:
            event.ignore()

    # ── 弹窗核心逻辑 ──

    def _popup_key_press(self, event):
        """弹窗列表按键：Escape 关闭，其余交给 QListWidget 默认处理。"""
        if event.key() == Qt.Key.Key_Escape:
            self.hidePopup()
            self.setFocus()
            return
        QListWidget.keyPressEvent(self._popup_list, event)

    def showPopup(self):
        """完全接管弹窗：用 QFrame·Popup 替代 QComboBox 原生弹窗。"""
        if self.count() == 0:
            return
        # 0. 刷新弹窗主题（支持动态切换）
        self._update_popup_style()
        # 1. 同步数据到 QListWidget
        self._popup_list.clear()
        for i in range(self.count()):
            self._popup_list.addItem(self.itemText(i))

        # 2. 高亮当前选中
        cur = self.currentIndex()
        if 0 <= cur < self._popup_list.count():
            self._popup_list.setCurrentRow(cur)
            self._popup_list.scrollToItem(self._popup_list.item(cur))

        # 3. 计算弹窗高度
        max_items = MAX_COMBO_ITEMS
        window = self.window()
        max_h = int(window.height() * 0.30) if window else 220
        item_h = DEFAULT_ITEM_HEIGHT
        visible_count = min(self.count(), max_items, max(2, max_h // item_h))
        popup_height = visible_count * item_h + 12  # 12px padding

        self._popup_list.setFixedHeight(popup_height)

        # 4. 计算弹窗宽度（与 ComboBox 等宽）
        popup_width = max(self.width(), 120)
        self._popup_frame.setFixedWidth(popup_width)

        # 5. 定位在 ComboBox 正下方
        pos = self.mapToGlobal(self.rect().bottomLeft())
        screen = QApplication.primaryScreen()
        if screen:
            sg = screen.availableGeometry()
            # 向下溢出则改为向上弹出
            if pos.y() + popup_height > sg.bottom():
                pos.setY(pos.y() - popup_height - self.height())
            # 左溢出校正
            if pos.x() < sg.left():
                pos.setX(sg.left())
            elif pos.x() + popup_width > sg.right():
                pos.setX(sg.right() - popup_width)

        self._popup_frame.move(pos)
        self._popup_frame.show()
        self._popup_list.setFocus()

        # 6. 忽略 ComboBox 原生弹窗（只设了 max=1 不会弹出）

    def hidePopup(self):
        """隐藏自定义弹窗。"""
        if self._popup_frame:
            self._popup_frame.hide()

    def _on_item_clicked(self, item):
        """选中一项 → 更新 ComboBox 的值并关闭弹窗。
        重选当前项时不发信号，避免预设重载/UI 重建等副作用。"""
        idx = self._popup_list.row(item)
        if 0 <= idx < self.count():
            if idx != self.currentIndex():
                was = self.signalsBlocked()
                self.blockSignals(True)
                self.setCurrentIndex(idx)
                self.blockSignals(was)
                if not was:
                    self.currentIndexChanged.emit(idx)
                    self.currentTextChanged.emit(self.currentText())
        self.hidePopup()
        self.setFocus()


# ═══════════════════════════════════════════════
#  ConsoleWidget
# ═══════════════════════════════════════════════

class ConsoleWidget(QWidget):
    """可停靠的控制台面板，显示进程输出并支持 CLI 交互输入。"""
    input_signal = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._interactive = False
        self._theme = "dark"
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        cf = QFont("Consolas", 9)
        cf.setStyleStrategy(QFont.StyleStrategy.PreferQuality | QFont.StyleStrategy.PreferAntialias)
        cf.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        self.output.setFont(cf)
        self.output.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.output, 1)

        self.input_row = QWidget()
        ir = QHBoxLayout(self.input_row)
        ir.setContentsMargins(0, 2, 0, 0)
        ir.setSpacing(4)

        self.clear_btn = QPushButton(BTN.get("clear", "清空"))
        self.clear_btn.clicked.connect(self.output.clear)
        ir.addWidget(self.clear_btn)

        self.export_btn = QPushButton(BTN.get("export_log", "导出日志"))
        self.export_btn.clicked.connect(self._export_log)
        ir.addWidget(self.export_btn)

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText(PH.get("cli_placeholder", "输入消息后回车发送..."))
        self.input_edit.returnPressed.connect(self._send_input)
        ir.addWidget(self.input_edit, 1)

        self.send_btn = QPushButton(BTN.get("send", "发送"))
        self.send_btn.clicked.connect(self._send_input)
        ir.addWidget(self.send_btn)

        layout.addWidget(self.input_row)

        self._apply_theme()

    def _export_log(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            WIN_TITLES.get("export_log_title", "导出日志"),
            os.path.expanduser("~"),
            "Text (*.txt);;All (*)",
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.output.toPlainText())
                self.append_output(MSG.get("export_log_success", "✅ 日志已导出"), "green")
            except Exception as e:
                self.append_output(
                    MSG.get("export_log_fail", "❌ 导出失败: {err}").replace("{err}", str(e)), "red")

    def _send_input(self):
        text = self.input_edit.text()
        if text:
            self.input_signal.emit(text)
            self.input_edit.clear()

    def set_interactive(self, enabled: bool):
        self._interactive = enabled
        self.input_row.setVisible(enabled)
        if enabled:
            self.input_edit.setFocus()

    def set_theme(self, theme: str):
        self._theme = theme
        self._apply_theme()

    def _apply_theme(self):
        colors = CONSOLE_COLORS.get(self._theme, CONSOLE_COLORS.get("dark", {}))
        self._console_colors = colors

        styles = CONSOLE_THEME_STYLES.get(self._theme, CONSOLE_THEME_STYLES["dark"])
        self.output.setStyleSheet(styles["output"])
        self.input_edit.setStyleSheet(styles["input"])
        self.clear_btn.setStyleSheet(styles["clear_btn"])
        self.export_btn.setStyleSheet(styles["export_btn"])
        self.send_btn.setStyleSheet(styles["send_btn"])

    def append_output(self, text: str, color: str = None):
        if color:
            hex_color = getattr(self, '_console_colors', {}).get(color, color)
            self.output.append(f'<span style="color:{hex_color}">{text}</span>')
        else:
            self.output.append(text)
        scrollbar = self.output.verticalScrollBar()
        if scrollbar:
            scrollbar.setValue(scrollbar.maximum())

    def refresh_last_line(self, text: str, color: str = None):
        cursor = self.output.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.movePosition(cursor.MoveOperation.StartOfBlock, cursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        self.output.setTextCursor(cursor)
        self.append_output(text, color)


# ═══════════════════════════════════════════════
#  CommandPreviewDialog
# ═══════════════════════════════════════════════

CONSOLE_THEME_STYLES = {
    "dark": {
        "output": """
            QTextEdit {
                background-color: #14142a;
                color: #e0e0f0;
                border: 1px solid #2e2e48;
                border-radius: 6px;
                padding: 5px;
                font-family: 'Consolas', 'Courier New', monospace;
                selection-background-color: #3d5575;
            }
        """,
        "input": "background-color:#2a2a40;color:#e0e0f0;border:1px solid #3f3f5c;"
                 "border-radius:4px;padding:3px 8px;font-size:8.5pt;",
        "clear_btn": "QPushButton{background-color:#2a2a40;color:#a0a0c8;border:1px solid #3f3f5c;"
                     "border-radius:4px;padding:3px 8px;font-size:8pt;}"
                     "QPushButton:hover{background-color:#363658;border-color:#5a5a80;}",
        "export_btn": "QPushButton{background-color:#2a2a40;color:#a0a0c8;border:1px solid #3f3f5c;"
                      "border-radius:4px;padding:3px 8px;font-size:8pt;}"
                      "QPushButton:hover{background-color:#363658;border-color:#5a5a80;}",
        "send_btn": "QPushButton{background-color:#1e3a5a;color:#6db3ff;border:1px solid #2a5080;"
                    "border-radius:4px;padding:3px 10px;font-size:8pt;font-weight:bold;}"
                    "QPushButton:hover{background-color:#264a70;border-color:#6db3ff;}"
                    "QPushButton:pressed{background-color:#1e3a5a;}",
    },
    "light": {
        "output": """
            QTextEdit {
                background-color: #ffffff;
                color: #1a1a2e;
                border: 1px solid #c8ccd4;
                border-radius: 6px;
                padding: 5px;
                font-family: 'Consolas', 'Courier New', monospace;
                selection-background-color: #c8dcf8;
            }
        """,
        "input": "background-color:#ffffff;color:#1a1a2e;border:1px solid #c8ccd4;"
                 "border-radius:4px;padding:3px 8px;font-size:8.5pt;",
        "clear_btn": "QPushButton{background-color:#f0f2f5;color:#505060;border:1px solid #d4d6dc;"
                     "border-radius:4px;padding:3px 8px;font-size:8pt;}"
                     "QPushButton:hover{background-color:#e0e4ea;border-color:#b0b8c4;}",
        "export_btn": "QPushButton{background-color:#f0f2f5;color:#505060;border:1px solid #d4d6dc;"
                      "border-radius:4px;padding:3px 8px;font-size:8pt;}"
                      "QPushButton:hover{background-color:#e0e4ea;border-color:#b0b8c4;}",
        "send_btn": "QPushButton{background-color:#3d88e0;color:#ffffff;border:1px solid #2a6ec0;"
                    "border-radius:4px;padding:3px 10px;font-size:8pt;font-weight:bold;}"
                    "QPushButton:hover{background-color:#4a9ae8;border-color:#3d88e0;}"
                    "QPushButton:pressed{background-color:#2a6ec0;}",
    },
}


class CommandPreviewDialog(QDialog):
    """显示完整的命令行参数，支持复制和保存为 bat/sh。"""

    def __init__(self, cmd_parts: list, parent=None, theme: str = "dark"):
        super().__init__(parent)
        self.cmd_parts = cmd_parts
        self.theme = theme
        self.setWindowTitle(WIN_TITLES.get("preview_dialog", "命令预览"))
        self.setMinimumSize(560, 340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        oneline = " ".join(cmd_parts)
        self.cmd_label = QLabel(f"<pre>{oneline}</pre>")
        self.cmd_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.cmd_label.setWordWrap(True)
        layout.addWidget(self.cmd_label)

        self.list_widget = QListWidget()
        for i, a in enumerate(cmd_parts):
            self.list_widget.addItem(f"[{i}] {a}")
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        copy_btn = QPushButton(BTN.get("copy", "📋 复制命令"))
        copy_btn.clicked.connect(self._copy_command)
        btn_layout.addWidget(copy_btn)

        save_btn = QPushButton(BTN.get("save_script", "💾 保存脚本"))
        save_btn.clicked.connect(self._save_script)
        btn_layout.addWidget(save_btn)

        btn_layout.addStretch()

        close_btn = QPushButton(BTN.get("close", "关闭"))
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        self._apply_theme()

    def _apply_theme(self):
        if self.theme == "light":
            self.setStyleSheet("""
                QDialog { background-color: #f2f3f5; color: #1e1e2e; }
                QLabel { color: #1e1e2e; }
                QListWidget {
                    background-color: #ffffff; color: #1e1e2e;
                    border: 1px solid #d4d6dc; border-radius: 5px;
                    font-family: 'Consolas', monospace; font-size: 8.5pt;
                    padding: 3px;
                }
                QListWidget::item { padding: 2px 4px; border-radius: 3px; }
                QListWidget::item:selected { background-color: #dce8f8; }
                QListWidget::item:hover:!selected { background-color: #eef2f8; }
                QPushButton {
                    background-color: #ffffff; color: #1e1e2e;
                    border: 1px solid #d4d6dc; border-radius: 5px;
                    padding: 4px 10px; min-height: 22px; font-size: 8.5pt;
                }
                QPushButton:hover { background-color: #e8eaf0; border-color: #b0b8c4; }
                QPushButton:pressed { background-color: #dce0e8; border-color: #3d88e0; }
            """)
        else:
            self.setStyleSheet("""
                QDialog { background-color: #1a1a2e; color: #e0e0f0; }
                QLabel { color: #d0d0e8; }
                QListWidget {
                    background-color: #14142a; color: #e0e0f0;
                    border: 1px solid #2e2e48; border-radius: 5px;
                    font-family: 'Consolas', monospace; font-size: 8.5pt;
                    padding: 3px;
                }
                QListWidget::item { padding: 2px 4px; border-radius: 3px; }
                QListWidget::item:selected { background-color: #2a4a6a; }
                QListWidget::item:hover:!selected { background-color: #262640; }
                QPushButton {
                    background-color: #2a2a40; color: #e0e0f0;
                    border: 1px solid #3f3f5c; border-radius: 5px;
                    padding: 4px 10px; min-height: 22px; font-size: 8.5pt;
                }
                QPushButton:hover { background-color: #363658; border-color: #5a5a80; }
                QPushButton:pressed { background-color: #3f3f5c; border-color: #6db3ff; }
            """)

    def _copy_command(self):
        cb = QApplication.clipboard()
        cb.setText(" ".join(self.cmd_parts))
        self.cmd_label.setText(
            f"<pre>{' '.join(self.cmd_parts)}</pre>\n"
            f"<span style='color:green'>✅ {MSG.get('copied', '已复制到剪贴板')}</span>")

    def _save_script(self):
        path = save_script(self.cmd_parts, os.path.dirname(os.path.abspath(__file__)))
        msg = MSG.get("script_saved", "脚本已保存到:\n{path}").replace("{path}", path)
        if sys.platform == "win32":
            vbs_path = path.replace(".bat", ".vbs")
            msg += MSG.get("script_saved_vbs", "\n\n💡 双击 {vbs} 可无窗口启动").replace("{vbs}", vbs_path)
        QMessageBox.information(
            self,
            WIN_TITLES.get("bat_save_success_title", "脚本已保存"),
            msg,
        )
