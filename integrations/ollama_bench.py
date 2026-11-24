"""实测 Ollama 生成速度与显存占用。

用法：
    python integrations/ollama_bench.py --model qwen3:8b --runs 3
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

DEFAULT_HOST = "http://127.0.0.1:11434"


def _post(url: str, payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _get(url: str, timeout: int = 5) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def gpu_memory() -> Optional[str]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return result.stdout.strip().splitlines()[0]
    except (OSError, subprocess.SubprocessError):
        return None


def loaded_models(host: str) -> List[Dict[str, Any]]:
    try:
        data = _get(host.rstrip("/") + "/api/ps")
        return data.get("models") or []
    except Exception:
        return []


def run_once(host: str, model: str, prompt: str, num_predict: int, timeout: int) -> Dict[str, float]:
    data = _post(
        host.rstrip("/") + "/api/generate",
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": num_predict},
        },
        timeout=timeout,
    )
    eval_count = int(data.get("eval_count") or 0)
    eval_ns = int(data.get("eval_duration") or 0)
    load_ns = int(data.get("load_duration") or 0)
    tokens_per_second = eval_count / (eval_ns / 1e9) if eval_ns else 0.0
    return {
        "tokens": eval_count,
        "seconds": eval_ns / 1e9,
        "tokens_per_second": tokens_per_second,
        "load_seconds": load_ns / 1e9,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="实测 Ollama 模型生成速度")
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--prompt", default="用三句话解释什么是量化。")
    parser.add_argument("--num-predict", type=int, default=128)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    print(f"模型：{args.model}")
    print(f"主机：{args.host}")
    print(f"显存：{gpu_memory() or '未检测到 nvidia-smi'}")
    print("-" * 56)

    results: List[Dict[str, float]] = []
    for index in range(1, args.runs + 1):
        try:
            result = run_once(args.host, args.model, args.prompt, args.num_predict, args.timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"第 {index} 次失败：{exc}")
            return 1
        results.append(result)
        print(
            f"第 {index} 次：{result['tokens']} tokens / "
            f"{result['seconds']:.2f}s = {result['tokens_per_second']:.1f} tok/s"
            f"（加载 {result['load_seconds']:.2f}s）"
        )

    average = sum(item["tokens_per_second"] for item in results) / len(results)
    print("-" * 56)
    print(f"平均生成速度：{average:.1f} tok/s")

    models = loaded_models(args.host)
    for model in models:
        vram = model.get("size_vram") or 0
        total = model.get("size") or 0
        print(
            f"已加载模型：{model.get('name')}，"
            f"显存 {vram / 1024**3:.2f}GB / 总占用 {total / 1024**3:.2f}GB"
        )
    print(f"GPU 当前显存：{gpu_memory() or '未知'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
