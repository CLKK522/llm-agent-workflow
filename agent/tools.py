"""工具注册表：JSON Schema 描述、统一执行、结构化错误回传。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .config import Settings


@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Any]

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self, max_result_chars: int = 6000) -> None:
        self._tools: Dict[str, Tool] = {}
        self.max_result_chars = max_result_chars

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"工具重复注册：{tool.name}")
        self._tools[tool.name] = tool

    def names(self) -> List[str]:
        return list(self._tools)

    def schemas(self) -> List[Dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def execute(self, name: str, arguments: Any) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return self._error(f"未知工具：{name}")

        if isinstance(arguments, str):
            try:
                kwargs = json.loads(arguments or "{}")
            except json.JSONDecodeError as exc:
                return self._error(f"参数不是合法 JSON：{exc}")
        elif isinstance(arguments, dict):
            kwargs = arguments
        else:
            return self._error("参数必须是 JSON 对象")

        if not isinstance(kwargs, dict):
            return self._error("参数必须是 JSON 对象")

        try:
            result = tool.handler(**kwargs)
        except TypeError as exc:
            return self._error(f"参数不匹配：{exc}")
        except Exception as exc:  # 工具失败不应中断整个 Agent 循环
            return self._error(f"{type(exc).__name__}: {exc}")

        payload = json.dumps(
            {"ok": True, "tool": name, "result": result},
            ensure_ascii=False,
            default=str,
        )
        return self._truncate(payload)

    def _error(self, message: str) -> str:
        return json.dumps(
            {"ok": False, "error": message},
            ensure_ascii=False,
        )

    def _truncate(self, text: str) -> str:
        if len(text) <= self.max_result_chars:
            return text
        return text[: self.max_result_chars] + "…（结果过长，已截断）"


def build_default_registry(settings: Settings) -> ToolRegistry:
    """注册本项目的三个本地工具。"""

    from integrations import comfyui, cosyvoice

    registry = ToolRegistry()
    output_dir = settings.workspace_path

    def generate_image(
        prompt: str,
        size: str = "832x1216",
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        return comfyui.generate(
            prompt=prompt,
            size=size,
            seed=seed,
            output_dir=str(output_dir),
            url=settings.comfyui_url,
            timeout=settings.timeout,
        )

    def text_to_speech(
        text: str,
        instruct: str = "",
        speed: float = 1.0,
    ) -> Dict[str, Any]:
        return cosyvoice.synthesize(
            text=text,
            instruct=instruct,
            speed=speed,
            output_dir=str(output_dir),
            url=settings.cosyvoice_url,
            timeout=settings.timeout,
        )

    def check_services() -> Dict[str, Any]:
        return {
            "comfyui": comfyui.health(settings.comfyui_url),
            "cosyvoice": cosyvoice.health(settings.cosyvoice_url),
        }

    registry.register(
        Tool(
            name="generate_image",
            description="调用本地 ComfyUI（SDXL）生成图片，返回保存后的文件路径。耗时约 30–120 秒。",
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "正向提示词，建议英文，包含主体、场景、风格与画质词。",
                    },
                    "size": {
                        "type": "string",
                        "description": "图片尺寸，格式 WxH，例如 832x1216；长宽需为 64 的倍数。",
                        "default": "832x1216",
                    },
                    "seed": {
                        "type": "integer",
                        "description": "随机种子；不传则自动生成。",
                    },
                },
                "required": ["prompt"],
            },
            handler=generate_image,
        )
    )

    registry.register(
        Tool(
            name="text_to_speech",
            description="调用本地 CosyVoice2 把文字合成为语音，返回 WAV 文件路径。耗时约 5–30 秒。",
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "要朗读的文本，建议 100 字以内。",
                    },
                    "instruct": {
                        "type": "string",
                        "description": "可选的语气指令，用中文短句描述，例如：用温柔、放慢的语气说这句话。",
                    },
                    "speed": {
                        "type": "number",
                        "description": "语速倍率，默认 1.0。",
                        "default": 1.0,
                    },
                },
                "required": ["text"],
            },
            handler=text_to_speech,
        )
    )

    registry.register(
        Tool(
            name="check_services",
            description="检查 ComfyUI 与 CosyVoice2 是否在线，返回两个本地服务的状态。",
            parameters={"type": "object", "properties": {}},
            handler=check_services,
        )
    )

    return registry
