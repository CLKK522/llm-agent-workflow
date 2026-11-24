"""本地 CosyVoice2 服务客户端：把文字合成为 WAV。"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_URL = "http://127.0.0.1:50002"


class CosyVoiceError(RuntimeError):
    pass


def health(url: str = DEFAULT_URL, timeout: int = 3) -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/", timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
        try:
            data = json.loads(raw)
        except ValueError:
            data = {"ok": True, "response": raw[:200]}
        data.setdefault("ok", True)
        data["url"] = url
        return data
    except Exception as exc:
        return {"ok": False, "url": url, "error": f"{type(exc).__name__}: {exc}"}


def synthesize(
    text: str,
    instruct: str = "",
    speed: float = 1.0,
    output_dir: Optional[str] = None,
    out_path: Optional[str] = None,
    url: str = DEFAULT_URL,
    timeout: int = 300,
) -> Dict[str, Any]:
    """调用本地 TTS 服务，保存 WAV 并返回路径。"""

    if not text or not str(text).strip():
        raise ValueError("text 不能为空")

    form = urllib.parse.urlencode(
        {
            "tts_text": str(text),
            "spk_id": "",
            "speed": str(speed),
            "instruct_text": instruct or "",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url.rstrip("/") + "/inference_sft",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            audio = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise CosyVoiceError(f"TTS 合成失败：HTTP {exc.code}，{detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CosyVoiceError(f"CosyVoice2 不可用（{url}）：{exc}") from exc

    if not audio:
        raise CosyVoiceError("TTS 服务返回了空音频")

    if out_path:
        destination = Path(out_path)
    else:
        directory = Path(output_dir) if output_dir else Path.cwd() / "outputs"
        destination = directory / f"tts_{int(time.time())}.wav"

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(audio)

    return {
        "file": str(destination),
        "bytes": len(audio),
        "speed": speed,
        "instruct": instruct,
    }
