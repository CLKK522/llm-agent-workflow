"""配置加载：默认值 → config.json → 环境变量。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PRESETS: Dict[str, Dict[str, str]] = {
    "ollama": {
        "model": "qwen3:8b",
        "api_base": "http://127.0.0.1:11434/v1",
        "api_key": "ollama",
    },
    "deepseek": {
        "model": "deepseek-chat",
        "api_base": "https://api.deepseek.com/v1",
        "api_key": "",
    },
}


@dataclass
class Settings:
    provider: str = "ollama"
    model: str = "qwen3:8b"
    api_base: str = "http://127.0.0.1:11434/v1"
    api_key: str = "ollama"
    comfyui_url: str = "http://127.0.0.1:8188"
    cosyvoice_url: str = "http://127.0.0.1:50002"
    workspace: str = "outputs"
    max_steps: int = 6
    timeout: int = 300

    @property
    def workspace_path(self) -> Path:
        path = Path(self.workspace)
        return path if path.is_absolute() else PROJECT_ROOT / path

    def validate(self) -> None:
        if self.provider == "deepseek" and not self.api_key:
            raise ValueError(
                "使用 DeepSeek API 时需要设置 DEEPSEEK_API_KEY，"
                "或在 config.json 的 providers.deepseek.api_key 中填写。"
            )


def _read_config(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"配置文件必须是 JSON 对象：{path}")
    return raw


def load_settings(
    config_path: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> Settings:
    """读取配置。

    优先级：命令行参数 > 环境变量 > config.json > provider 预设。
    """

    path = Path(config_path) if config_path else PROJECT_ROOT / "config.json"
    raw = _read_config(path)

    provider_name = (
        provider or os.getenv("LLM_PROVIDER") or raw.get("provider") or "ollama"
    )
    if provider_name not in PRESETS:
        raise ValueError(
            f"未知 provider：{provider_name}（可选：{', '.join(PRESETS)}）"
        )

    profile: Dict[str, Any] = dict(PRESETS[provider_name])
    configured = (raw.get("providers") or {}).get(provider_name) or {}
    if isinstance(configured, dict):
        profile.update({key: value for key, value in configured.items() if value is not None})

    settings = Settings(provider=provider_name, **profile)

    # 兼容顶层直接写 model / api_base / api_key 的旧格式。
    for key in ("model", "api_base", "api_key"):
        if key in raw and raw[key] is not None:
            setattr(settings, key, raw[key])

    for key in ("comfyui_url", "cosyvoice_url", "workspace", "max_steps", "timeout"):
        if key in raw and raw[key] is not None:
            setattr(settings, key, raw[key])

    env_map = {
        "LLM_MODEL": "model",
        "LLM_API_BASE": "api_base",
        "LLM_API_KEY": "api_key",
        "COMFYUI_URL": "comfyui_url",
        "COSYVOICE_URL": "cosyvoice_url",
        "AGENT_WORKSPACE": "workspace",
    }
    for env_name, attr in env_map.items():
        value = os.getenv(env_name)
        if value:
            setattr(settings, attr, value)

    for env_name, attr in (("AGENT_MAX_STEPS", "max_steps"), ("LLM_TIMEOUT", "timeout")):
        value = os.getenv(env_name)
        if value:
            setattr(settings, attr, int(value))

    if model:
        settings.model = model

    if settings.provider == "deepseek" and not settings.api_key:
        settings.api_key = os.getenv("DEEPSEEK_API_KEY", "")

    return settings
