"""集成层纯逻辑测试（不需要启动 ComfyUI / CosyVoice2）。"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from integrations.comfyui import _parse_size, _prepare_workflow  # noqa: E402


class ComfyWorkflowTest(unittest.TestCase):
    def test_parse_size_rounds_to_multiple_of_64(self):
        self.assertEqual(_parse_size("832x1216"), (832, 1216))
        self.assertEqual(_parse_size("800x1200"), (768, 1216))

    def test_parse_size_clamps(self):
        self.assertEqual(_parse_size("256x256"), (512, 512))
        self.assertEqual(_parse_size("4096x4096"), (1536, 1536))

    def test_parse_size_rejects_bad_format(self):
        with self.assertRaises(ValueError):
            _parse_size("large")

    def test_prepare_workflow_overrides_fields(self):
        workflow = json.loads(
            (PROJECT_ROOT / "workflows" / "text2img_sdxl.json").read_text(encoding="utf-8")
        )
        prepared, seed = _prepare_workflow(workflow, "a test prompt", "512x768", 123)

        self.assertEqual(seed, 123)
        self.assertEqual(prepared["6"]["inputs"]["text"], "a test prompt")
        self.assertEqual(prepared["5"]["inputs"]["width"], 512)
        self.assertEqual(prepared["5"]["inputs"]["height"], 768)
        self.assertEqual(prepared["3"]["inputs"]["seed"], 123)
        self.assertEqual(prepared["9"]["inputs"]["filename_prefix"], "agent")


if __name__ == "__main__":
    unittest.main()
