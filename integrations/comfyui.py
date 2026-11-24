"""ComfyUI HTTP 客户端：提交工作流、轮询进度、下载图片。"""

from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

DEFAULT_URL = "http://127.0.0.1:8188"
DEFAULT_WORKFLOW = Path(__file__).resolve().parent.parent / "workflows" / "text2img_sdxl.json"


class ComfyUIError(RuntimeError):
    pass


def health(url: str = DEFAULT_URL, timeout: int = 3) -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/system_stats", timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        system = data.get("system") or {}
        return {
            "ok": True,
            "url": url,
            "comfyui_version": system.get("comfyui_version"),
            "python_version": system.get("python_version"),
        }
    except Exception as exc:
        return {"ok": False, "url": url, "error": f"{type(exc).__name__}: {exc}"}


def _parse_size(size: str) -> Tuple[int, int]:
    match = re.match(r"^\s*(\d+)\s*[xX×*]\s*(\d+)\s*$", str(size))
    if not match:
        raise ValueError(f"尺寸格式应为 WxH，例如 832x1216，收到：{size!r}")
    width, height = (int(match.group(1)), int(match.group(2)))
    width = max(512, min(1536, round(width / 64) * 64))
    height = max(512, min(1536, round(height / 64) * 64))
    return width, height


def _text_node_id(workflow: Dict[str, Any], sampler: Dict[str, Any], key: str) -> Optional[str]:
    ref = (sampler.get("inputs") or {}).get(key)
    if isinstance(ref, list) and ref:
        return str(ref[0])
    return None


def _prepare_workflow(
    workflow: Dict[str, Any],
    prompt: str,
    size: str,
    seed: Optional[int],
) -> Tuple[Dict[str, Any], int]:
    samplers = [node for node in workflow.values() if node.get("class_type") == "KSampler"]
    if not samplers:
        raise ComfyUIError("工作流中没有找到 KSampler 节点")
    sampler = samplers[0]

    positive_id = _text_node_id(workflow, sampler, "positive")
    if positive_id and positive_id in workflow:
        workflow[positive_id].setdefault("inputs", {})["text"] = prompt

    latent_ref = (sampler.get("inputs") or {}).get("latent_image")
    if isinstance(latent_ref, list) and latent_ref:
        latent = workflow.get(str(latent_ref[0]))
        if latent:
            width, height = _parse_size(size)
            latent.setdefault("inputs", {}).update(
                {"width": width, "height": height, "batch_size": 1}
            )

    if seed is None:
        seed = random.randint(0, 2**31 - 1)
    sampler.setdefault("inputs", {})["seed"] = int(seed)

    for node in workflow.values():
        if node.get("class_type") == "SaveImage":
            node.setdefault("inputs", {})["filename_prefix"] = "agent"

    return workflow, int(seed)


def _post_json(url: str, payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise ComfyUIError(f"ComfyUI 提交失败：HTTP {exc.code}，{detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ComfyUIError(f"ComfyUI 不可用（{url}）：{exc}") from exc


def generate(
    prompt: str,
    size: str = "832x1216",
    seed: Optional[int] = None,
    output_dir: Optional[str] = None,
    workflow_path: Optional[str] = None,
    url: str = DEFAULT_URL,
    timeout: int = 300,
) -> Dict[str, Any]:
    """提交一次文生图任务，返回保存后的文件路径。"""

    if not prompt or not str(prompt).strip():
        raise ValueError("prompt 不能为空")

    workflow_file = Path(workflow_path) if workflow_path else DEFAULT_WORKFLOW
    workflow = json.loads(workflow_file.read_text(encoding="utf-8"))
    workflow, seed = _prepare_workflow(workflow, str(prompt), size, seed)

    base = url.rstrip("/")
    submitted = _post_json(
        base + "/prompt",
        {"prompt": workflow, "client_id": uuid.uuid4().hex},
        timeout=30,
    )
    prompt_id = submitted.get("prompt_id")
    if not prompt_id:
        raise ComfyUIError(f"ComfyUI 未返回 prompt_id：{submitted}")

    deadline = time.time() + timeout
    image: Optional[Dict[str, Any]] = None
    while time.time() < deadline:
        time.sleep(2)
        try:
            with urllib.request.urlopen(
                f"{base}/history/{prompt_id}", timeout=15
            ) as response:
                history = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError):
            continue

        entry = history.get(prompt_id)
        if entry and entry.get("outputs"):
            for node in entry["outputs"].values():
                images = node.get("images") or []
                if images:
                    image = images[0]
                    break
        if image:
            break

    if not image:
        raise ComfyUIError(f"ComfyUI 在 {timeout} 秒内没有出图（prompt_id={prompt_id}）")

    query = urllib.parse.urlencode(
        {
            "filename": image.get("filename", ""),
            "subfolder": image.get("subfolder", ""),
            "type": image.get("type", "output"),
        }
    )
    output = Path(output_dir) if output_dir else Path.cwd() / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    suffix = Path(image.get("filename", "")).suffix or ".png"
    destination = output / f"image_{int(time.time())}_{seed}{suffix}"

    try:
        with urllib.request.urlopen(f"{base}/view?{query}", timeout=60) as response:
            destination.write_bytes(response.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ComfyUIError(f"取图失败：{exc}") from exc

    return {
        "file": str(destination),
        "prompt_id": prompt_id,
        "seed": seed,
        "size": size,
    }
