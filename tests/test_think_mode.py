"""思考控制参数构建 —— 回归测试。

背景：原实现中 hide 模式误用 --reasoning-format none（llama.cpp 语义是
"思考留在 message.content"，实测残留空的 <think></think> 标签）；stop 模式
的 --reasoning-budget 与 -r 在 b10107 实测无效。修复：hide 仅用 -rea off，
删除 stop 模式。本测试断言修复后的命令参数。

运行：.venv/Scripts/python.exe -m unittest tests.test_think_mode -v
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.config import _apply_locale_to_globals, DYNAMIC_UI_SCHEMA
from src.command_builder import LaunchConfig, build_command_args


def _cfg(think_mode="normal", think_budget=""):
    return LaunchConfig(
        model_rel_path="model.gguf",
        model_display="model.gguf",
        exe_path="llama-server",
        model_dir="C:/models",
        think_mode=think_mode,
        think_budget=think_budget,
    )


class ThinkModeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 加载语言包与 UI schema（含思考控制参数定义）
        _apply_locale_to_globals("zh")

    def _build(self, mode, budget=""):
        args, errors = build_command_args(_cfg(mode, budget), DYNAMIC_UI_SCHEMA)
        self.assertEqual(errors, [], f"unexpected warnings/errors: {errors}")
        return args

    # ── normal（正常输出） ──
    def test_normal_mode_default(self):
        args = self._build("normal")
        self.assertIn("--reasoning", args)
        self.assertEqual(args[args.index("--reasoning") + 1], "on")
        # 默认预算 0 → 不传 --reasoning-budget
        self.assertNotIn("--reasoning-budget", args)

    def test_normal_with_budget(self):
        args = self._build("normal", "500")
        self.assertEqual(args[args.index("--reasoning-budget") + 1], "500")

    # ── hide（完全隐藏） ──
    def test_hide_mode_only_rea_off(self):
        """hide 必须只含 -rea off；禁止 format none / budget 0 / -r 等失效参数。"""
        args = self._build("hide")
        self.assertIn("-rea", args)
        self.assertEqual(args[args.index("-rea") + 1], "off")
        for bad in ("--reasoning-format", "--reasoning-budget", "-r", "--reasoning"):
            self.assertNotIn(bad, args)

    def test_hide_ignores_budget(self):
        args = self._build("hide", "999")
        self.assertNotIn("--reasoning-budget", args)
        self.assertEqual(args[args.index("-rea") + 1], "off")

    # ── stop 已移除 ──
    def test_removed_stop_mode_is_noop(self):
        """旧 stop 值不再产出任何 thinking 参数（UI 层已归一为 hide，此处防御）。"""
        args = self._build("stop")
        for bad in ("--reasoning-format", "-r", "--reasoning-budget", "--reasoning", "-rea"):
            self.assertNotIn(bad, args)

    # ── 预算校验保留 ──
    def test_invalid_budget(self):
        args, errors = build_command_args(_cfg("normal", "abc"), DYNAMIC_UI_SCHEMA)
        self.assertIsNone(args)
        self.assertTrue(any(e.code == "invalid_budget" for e in errors))

    def test_negative_budget(self):
        args, errors = build_command_args(_cfg("normal", "-5"), DYNAMIC_UI_SCHEMA)
        self.assertIsNone(args)
        self.assertTrue(any(e.code == "invalid_budget" for e in errors))


class _FakeLauncher:
    """模拟 UI 窗口：验证 radio 回调不会因 dict.update 短路而失效。"""

    def __init__(self):
        self.config = {}
        self._think_mode = "normal"
        self.saved_count = 0

    def set_think_mode(self, mode):
        self._think_mode = mode

    def save_settings(self):
        self.saved_count += 1


class RadioToggleTest(unittest.TestCase):
    """回归：radio toggled 回调曾用 `and` 链导致 dict.update 返回 None 短路，
    set_think_mode / save_settings 永不执行（点「完全隐藏」不生效）。"""

    def _make(self):
        import main as m
        fake = _FakeLauncher()
        # 把真实方法绑定到 fake 实例（duck-typing，无需实例化 Qt 窗口）
        fake._on_radio_toggled = m.LlamaProLauncher._on_radio_toggled.__get__(fake)
        return fake

    def test_hide_selected_updates_think_mode(self):
        fake = self._make()
        fake._on_radio_toggled(True, "hide", "think_mode")
        self.assertEqual(fake._think_mode, "hide")
        self.assertEqual(fake.config.get("think_mode"), "hide")
        self.assertGreaterEqual(fake.saved_count, 1, "save_settings 应被执行（and 链不再短路）")

    def test_uncheck_is_noop(self):
        fake = self._make()
        fake._on_radio_toggled(False, "hide", "think_mode")
        self.assertEqual(fake._think_mode, "normal")
        self.assertEqual(fake.saved_count, 0)

    def test_normal_selected_after_hide(self):
        fake = self._make()
        fake._on_radio_toggled(True, "hide", "think_mode")
        fake._on_radio_toggled(True, "normal", "think_mode")
        self.assertEqual(fake._think_mode, "normal")


if __name__ == "__main__":
    unittest.main()
