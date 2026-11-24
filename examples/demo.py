#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""命令行演示：一句话指令 → Agent 调用本地工具 → 图像 / 语音产物。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent import (  # noqa: E402
    Agent,
    ChatClient,
    ShortTermMemory,
    build_default_registry,
    build_system_prompt,
    load_settings,
)
from agent.llm import LLMError  # noqa: E402

DEFAULT_PROMPT = "画一只在窗边看雨的橘猫，再用温柔的语气说一句晚安。"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="本地多模态 Agent 演示")
    parser.add_argument("prompt", nargs="?", default=DEFAULT_PROMPT, help="发给 Agent 的指令")
    parser.add_argument("--config", help="配置文件路径，默认读取仓库根目录的 config.json")
    parser.add_argument("--provider", choices=["ollama", "deepseek"], help="覆盖模型提供方")
    parser.add_argument("--model", help="覆盖模型名，例如 qwen3:8b / deepseek-chat")
    parser.add_argument("--max-steps", type=int, help="最大工具调用轮数")
    parser.add_argument("--no-memory", action="store_true", help="关闭短期记忆")
    parser.add_argument("--quiet", action="store_true", help="不输出工具调用日志")
    args = parser.parse_args()

    try:
        settings = load_settings(args.config, provider=args.provider, model=args.model)
        if args.max_steps:
            settings.max_steps = args.max_steps
        settings.validate()
    except (ValueError, OSError) as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 2

    settings.workspace_path.mkdir(parents=True, exist_ok=True)

    client = ChatClient(
        base_url=settings.api_base,
        api_key=settings.api_key,
        model=settings.model,
        timeout=settings.timeout,
    )
    registry = build_default_registry(settings)
    memory = None
    if not args.no_memory:
        memory = ShortTermMemory(settings.workspace_path / "memory.json")

    def logger(message: str) -> None:
        if not args.quiet:
            print(message, file=sys.stderr)

    agent = Agent(
        client=client,
        registry=registry,
        system_prompt=build_system_prompt(str(settings.workspace_path)),
        memory=memory,
        max_steps=settings.max_steps,
        logger=logger,
    )

    print(f"模型：{settings.provider} / {settings.model}")
    print(f"用户：{args.prompt}")
    try:
        answer = agent.run(args.prompt)
    except LLMError as exc:
        print(f"模型调用失败：{exc}", file=sys.stderr)
        return 1

    print("\nAgent：")
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
