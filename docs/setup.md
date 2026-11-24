# 环境搭建

以下命令以 Windows 11 + PowerShell 为主，Linux / macOS 只需替换路径与环境变量写法。

## 0. 硬件与基础环境

- NVIDIA 显卡，8GB 显存（本项目在 RTX 5050 Laptop 上验证）
- Python 3.9+
- Git
- 磁盘空间：模型与依赖建议预留 30GB 以上

## 1. 获取仓库

```powershell
git clone https://github.com/CLKK522/llm-agent-workflow.git
cd llm-agent-workflow
copy config.example.json config.json
```

核心 Agent 只依赖 Python 标准库，不需要创建虚拟环境；ComfyUI 与 CosyVoice2 各自使用独立环境。

## 2. Ollama 与 Qwen3-8B

从 <https://ollama.com/download> 安装 Ollama，然后：

```powershell
ollama pull qwen3:8b
ollama run qwen3:8b "你好"
```

确认模型在 GPU 上：

```powershell
ollama ps
```

输出中的 `PROCESSOR` 应该是 `100% GPU`。8GB 显存建议限制并发与常驻模型数：

```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_PARALLEL", "1", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_MAX_LOADED_MODELS", "1", "User")
```

修改后重启 Ollama 服务。实测显存占用约 5.6GB，生成速度约 20 tok/s。

> 8GB 卡上，本地 Qwen3 与 ComfyUI 同时加载很容易 OOM。跑完整多模态链路时建议用 DeepSeek API 做编排，本地显存留给 ComfyUI / CosyVoice；如果坚持全本地，请在调用出图工具前执行 `ollama stop qwen3:8b`。

### 使用 DeepSeek API（可选）

```powershell
$env:DEEPSEEK_API_KEY="sk-..."
python examples/demo.py --provider deepseek --model deepseek-chat "用一句话介绍你自己"
```

也可以把 `config.json` 的 `provider` 改成 `deepseek`，并填写 `providers.deepseek.api_key`。

## 3. ComfyUI

```powershell
git clone https://github.com/comfyanonymous/ComfyUI.git D:\Aurabot\comfy\ComfyUI
cd D:\Aurabot\comfy\ComfyUI
python -m venv ..\env
..\env\Scripts\activate
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
```

下载一个 SDXL 底模（本项目使用 `Illustrious-XL-v1.0.safetensors`），放到：

```text
ComfyUI/models/checkpoints/Illustrious-XL-v1.0.safetensors
```

启动：

```powershell
python main.py --listen 127.0.0.1 --port 8188 --lowvram
```

验证：

```powershell
curl http://127.0.0.1:8188/system_stats
```

工作流文件是 `workflows/text2img_sdxl.json`。如果换了底模，需要同步修改其中的 `ckpt_name`，或设置 `COMFYUI_CKPT` 环境变量（仅 DSH 桥接脚本使用）。

> 8GB 显存建议加 `--lowvram`。首次加载模型约 30–40 秒。

## 4. CosyVoice2

```powershell
git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git D:\Aurabot\tts\CosyVoice
cd D:\Aurabot\tts\CosyVoice
python -m venv ..\env
..\env\Scripts\activate
pip install -r requirements.txt
```

从 ModelScope 或 Hugging Face 下载 `CosyVoice2-0.5B` 到本地目录，例如：

```text
D:\Aurabot\tts\models\CosyVoice2-0.5B
```

准备一段 16kHz 单声道参考音频（建议 5–15 秒、清晰无背景音乐），例如 `D:\voices\reference.wav`，并准备与音频内容一致的参考文本。

启动本仓库自带的服务：

```powershell
$env:COSYVOICE_ROOT="D:\Aurabot\tts\CosyVoice"
$env:COSYVOICE_MODEL_DIR="D:\Aurabot\tts\models\CosyVoice2-0.5B"
$env:COSYVOICE_REF_WAV="D:\voices\reference.wav"
$env:COSYVOICE_REF_TEXT="参考音频对应的文字内容"
python integrations\cosyvoice_server.py
```

服务默认监听 `127.0.0.1:50002`，可用 `COSYVOICE_PORT` 修改。

验证：

```powershell
curl http://127.0.0.1:50002/
```

> 参考音频、音色与克隆模型都不在仓库中。请确保你有权使用所选的参考音频。

## 5. 运行与测试

```powershell
# 检查两个本地服务
python -c "from integrations import comfyui, cosyvoice; print(comfyui.health()); print(cosyvoice.health())"

# 跑一个完整的演示
python examples/demo.py "画一只在窗边看雨的橘猫，再用温柔的语气说一句晚安。"

# 单元测试（不依赖网络）
python -m unittest discover -s tests -v

# 复现实测数据
python integrations/ollama_bench.py --model qwen3:8b --runs 3
```

## 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `LLM 服务不可用` | Ollama 没启动 | `ollama serve` 或重启 Ollama |
| `ComfyUI 不可用` | ComfyUI 没启动 / 端口不对 | 检查 8188 端口与 `config.json` |
| ComfyUI 提交成功但一直不出图 | 显存不足或模型加载失败 | 加 `--lowvram`，关闭其他占显存的进程 |
| TTS 报错或没有声音 | 参考音频/模型路径不对 | 检查三个 `COSYVOICE_*` 路径 |
| TTS 把语气指令念出来 | instruct 缺少 `<|endofprompt|>` | 使用本仓库的服务，会自动补齐 |
| 显存 OOM | 出图与 TTS 同时加载 | 串行调用，一次只跑一个重任务 |

更多实践记录见 [8gb-vram-notes.md](8gb-vram-notes.md)。
