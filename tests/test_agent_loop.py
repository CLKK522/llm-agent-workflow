"""不依赖网络的 Agent 循环测试。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.loop import Agent
from agent.memory import ShortTermMemory
from agent.tools import Tool, ToolRegistry


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, tools=None, temperature=0.3):
        self.calls.append({"messages": messages, "tools": tools})
        if not self.replies:
            raise AssertionError("FakeClient 的预设回复已用完")
        return self.replies.pop(0)


def tool_call(name: str, arguments: str, call_id: str = "call_1"):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def make_registry(handler):
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo",
            description="回显文本",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            handler=handler,
        )
    )
    return registry


class AgentLoopTest(unittest.TestCase):
    def test_tool_call_then_final_answer(self):
        executed = []

        def echo(text):
            executed.append(text)
            return {"echo": text}

        client = FakeClient(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [tool_call("echo", json.dumps({"text": "你好"}))],
                },
                {"role": "assistant", "content": "任务完成"},
            ]
        )
        agent = Agent(client, make_registry(echo), "system", max_steps=3)

        answer = agent.run("测试")

        self.assertEqual(answer, "任务完成")
        self.assertEqual(executed, ["你好"])
        second_messages = client.calls[1]["messages"]
        tool_messages = [m for m in second_messages if m["role"] == "tool"]
        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(tool_messages[0]["tool_call_id"], "call_1")
        self.assertIn('"ok": true', tool_messages[0]["content"])

    def test_tool_error_does_not_break_loop(self):
        def boom(text):
            raise RuntimeError("服务未启动")

        client = FakeClient(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [tool_call("echo", '{"text": "x"}')],
                },
                {"role": "assistant", "content": "工具失败了，但循环还在"},
            ]
        )
        agent = Agent(client, make_registry(boom), "system", max_steps=3)

        answer = agent.run("测试")

        self.assertEqual(answer, "工具失败了，但循环还在")
        tool_messages = [m for m in client.calls[1]["messages"] if m["role"] == "tool"]
        self.assertIn('"ok": false', tool_messages[0]["content"])
        self.assertIn("服务未启动", tool_messages[0]["content"])

    def test_unknown_tool_returns_structured_error(self):
        registry = make_registry(lambda text: text)
        result = registry.execute("missing", "{}")
        payload = json.loads(result)
        self.assertFalse(payload["ok"])
        self.assertIn("未知工具", payload["error"])

    def test_max_steps_forces_final_answer(self):
        client = FakeClient(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [tool_call("echo", '{"text": "1"}')],
                },
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [tool_call("echo", '{"text": "2"}', "call_2")],
                },
                {"role": "assistant", "content": "强制总结"},
            ]
        )
        agent = Agent(client, make_registry(lambda text: text), "system", max_steps=2)

        answer = agent.run("测试")

        self.assertEqual(answer, "强制总结")
        self.assertIsNone(client.calls[-1]["tools"])

    def test_memory_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            memory = ShortTermMemory(path, max_turns=2)
            memory.add("第一轮", "回答一")
            memory.add("第二轮", "回答二")
            memory.add("第三轮", "回答三")

            reloaded = ShortTermMemory(path, max_turns=2)
            messages = reloaded.recent()

            self.assertEqual(len(messages), 4)
            self.assertEqual(messages[0]["content"], "第二轮")
            self.assertEqual(messages[-1]["content"], "回答三")


if __name__ == "__main__":
    unittest.main()
