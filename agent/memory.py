"""轻量短期记忆：按轮保存，限制轮数，可选持久化。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional


class ShortTermMemory:
    def __init__(self, path: Optional[str] = None, max_turns: int = 6) -> None:
        self.path = Path(path) if path else None
        self.max_turns = max_turns
        self.turns: List[List[Dict[str, str]]] = []
        if self.path and self.path.exists():
            self._load()

    def recent(self) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        for turn in self.turns[-self.max_turns :]:
            messages.extend(turn)
        return messages

    def add(self, user_text: str, assistant_text: str) -> None:
        self.turns.append(
            [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": assistant_text},
            ]
        )
        self.turns = self.turns[-self.max_turns :]
        self._save()

    def clear(self) -> None:
        self.turns.clear()
        self._save()

    def _load(self) -> None:
        try:
            data: Any = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(data, list):
            self.turns = [turn for turn in data if isinstance(turn, list)][-self.max_turns :]

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.turns, handle, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
