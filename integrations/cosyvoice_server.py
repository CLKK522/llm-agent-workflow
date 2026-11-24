# -*- coding: utf-8 -*-
"""本地 CosyVoice2 HTTP 服务（Windows 友好版）。

在 CosyVoice2 官方推理代码外提供一层轻量 HTTP 接口，供 Agent 工具调用。
用法（先按 docs/setup.md 安装 CosyVoice2）：

    set COSYVOICE_ROOT=D:\\Aurabot\\tts\\CosyVoice
    set COSYVOICE_MODEL_DIR=D:\\Aurabot\\tts\\models\\CosyVoice2-0.5B
    set COSYVOICE_REF_WAV=D:\\voices\\reference.wav
    set COSYVOICE_REF_TEXT=参考音频对应的文字内容
    python integrations/cosyvoice_server.py

注意：参考音频需要自行准备（16kHz 单声道 WAV），仓库不附带任何声音样本。
"""

from __future__ import annotations

import io
import os
import sys
import types

# pyworld 只在训练流程中使用；Windows 下没有编译环境时用空壳绕过导入。
if "pyworld" not in sys.modules:
    stub = types.ModuleType("pyworld")
    stub.harvest = lambda *args, **kwargs: (None, None)
    stub.dio = lambda *args, **kwargs: (None, None)
    stub.stonemask = lambda *args, **kwargs: None
    sys.modules["pyworld"] = stub

ROOT = os.environ.get("COSYVOICE_ROOT", "")
MODEL_DIR = os.environ.get("COSYVOICE_MODEL_DIR", "")
REF_WAV = os.environ.get("COSYVOICE_REF_WAV", "")
REF_TEXT = os.environ.get("COSYVOICE_REF_TEXT", "")
PORT = int(os.environ.get("COSYVOICE_PORT", "50002"))

if not ROOT or not MODEL_DIR or not REF_WAV:
    raise SystemExit(
        "请先设置 COSYVOICE_ROOT、COSYVOICE_MODEL_DIR、COSYVOICE_REF_WAV 环境变量。"
    )
if not os.path.exists(REF_WAV):
    raise SystemExit(f"参考音频不存在：{REF_WAV}")

sys.path.append(ROOT)
sys.path.append(os.path.join(ROOT, "third_party", "Matcha-TTS"))

import soundfile as sf  # noqa: E402
import torch  # noqa: E402
import torchaudio  # noqa: E402
import uvicorn  # noqa: E402
from cosyvoice.cli.cosyvoice import AutoModel  # noqa: E402
from fastapi import FastAPI, Form  # noqa: E402
from fastapi.responses import Response  # noqa: E402


def _load_wav(wav: str, target_sr: int):
    """重写官方 load_wav：用 soundfile 读取并统一为单声道 float32。"""
    data, sample_rate = sf.read(wav, dtype="float32", always_2d=True)
    speech = torch.from_numpy(data.mean(axis=1)).unsqueeze(0)
    if sample_rate != target_sr:
        speech = torchaudio.functional.resample(speech, sample_rate, target_sr)
    return speech


import cosyvoice.cli.frontend as _frontend  # noqa: E402
import cosyvoice.utils.file_utils as _file_utils  # noqa: E402

_file_utils.load_wav = _load_wav
_frontend.load_wav = _load_wav

print("加载 CosyVoice2 模型…", flush=True)
model = AutoModel(model_dir=MODEL_DIR)
print(f"模型就绪，采样率 {model.sample_rate}", flush=True)

app = FastAPI()


def _normalize_instruct(text: str) -> str:
    """instruct2 的指令必须以 <|endofprompt|> 结尾，否则会被当成正文念出来。"""
    text = str(text or "").strip()
    if not text:
        return ""
    if "<|endofprompt|>" not in text:
        text += "<|endofprompt|>"
    return text


def _synthesize(text: str, instruct: str = "", speed: float = 1.0) -> bytes:
    instruction = _normalize_instruct(instruct)
    if instruction:
        chunks = [
            item["tts_speech"]
            for item in model.inference_instruct2(text, instruction, REF_WAV, speed=speed)
        ]
    else:
        chunks = [
            item["tts_speech"]
            for item in model.inference_zero_shot(text, REF_TEXT, REF_WAV, speed=speed)
        ]
    audio = torch.cat(chunks, dim=1).clamp(-1, 1).squeeze(0).cpu().numpy()
    buffer = io.BytesIO()
    sf.write(buffer, audio, model.sample_rate, format="WAV")
    return buffer.getvalue()


@app.post("/inference_sft")
def inference_sft(
    tts_text: str = Form(...),
    spk_id: str = Form(""),
    speed: float = Form(1.0),
    instruct_text: str = Form(""),
):
    return Response(
        content=_synthesize(tts_text, instruct_text, speed),
        media_type="audio/wav",
    )


@app.post("/inference_instruct")
def inference_instruct(
    tts_text: str = Form(...),
    spk_id: str = Form(""),
    instruct_text: str = Form(""),
    speed: float = Form(1.0),
):
    return Response(
        content=_synthesize(tts_text, instruct_text, speed),
        media_type="audio/wav",
    )


@app.get("/")
def health():
    return {
        "ok": True,
        "engine": "local-cosyvoice2",
        "sample_rate": model.sample_rate,
        "per_request_instruct": True,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
