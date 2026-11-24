"""Agent 主循环：任务拆解 → 工具执行 → 结果回传 → 最终回答。"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .llm import ChatClient, LLMError
from .memory import ShortTermMemory
from .tools import ToolRegistry

Message = Dict[str, Any]


class Agent:
    def __init__(
        self,
        client: ChatClient,
        registry: ToolRegistry,
        system_prompt: str,
        memory: Optional[ShortTermMemory] = None,
        max_steps: int = 6,
        logger: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.client = client
        self.registry = registry
        self.system_prompt = system_prompt
        self.memory = memory
        self.max_steps = max_steps
        self.logger = logger

    def run(self, user_text: str) -> str:
        messages: List[Message] = [{"role": "system", "content": self.system_prompt}]
        if self.memory:
            messages.extend(self.memory.recent())
        messages.append({"role": "user", "content": user_text})

        for step in range(1, self.max_steps + 1):
            reply = self.client.chat(messages, tools=self.registry.schemas())
            tool_calls = reply.get("tool_calls") or []

            for index, call in enumerate(tool_calls):
                call.setdefault("id", f"call_{step}_{index}")

            assistant: Message = {
                "role": "assistant",
                "content": reply.get("content") or "",
            }
            if tool_calls:
                assistant["tool_calls"] = tool_calls
            messages.append(assistant)

            if not tool_calls:
                final = (reply.get("content") or "").strip()
                self._remember(user_text, final)
                return final

            for call in tool_calls:
                function = call.get("function") or {}
                name = function.get("name") or ""
                arguments = function.get("arguments") or "{}"
                self._log(f"[step {step}] 调用工具 {name}，参数 {str(arguments)[:160]}")
                result = self.registry.execute(name, arguments)
                self._log(f"[step {step}] 工具返回 {result[:200]}")
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "name": name,
                        "content": result,
                    }
                )

        # 达到步数上限后，强制模型在不调用工具的情况下做一次总结。
        self._log(f"[warn] 达到最大步数 {self.max_steps}，请求最终总结")
        try:
            reply = self.client.chat(messages, tools=None)
            final = (reply.get("content") or "").strip()
        except LLMError as exc:
            final = f"任务未在 {self.max_steps} 步内完成，最终总结也失败了：{exc}"
        self._remember(user_text, final)
        return final

    def _remember(self, user_text: str, assistant_text: str) -> None:
        if self.memory:
            self.memory.add(user_text, assistant_text)

    def _log(self, message: str) -> None:
        if self.logger:
            self.logger(message)
