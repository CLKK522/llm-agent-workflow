# 8GB 显存实践笔记

> 设备：RTX 5050 Laptop，8151 MiB 显存，Windows 11。以下结论来自实际踩坑记录。

## 1. 显存红线：重任务必须串行

本地 TTS、出图、语音克隆同时运行时，8GB 显存不够用：

- 轻则模型被挤到 CPU，速度骤降；
- 重则 CUDA OOM，语音服务直接崩溃；
- ComfyUI 与 CosyVoice2 同时加载时，后启动的一方最容易失败。

**规则：一次只跑一件。** 要出图就先停语音克隆；要合成语音就先让 ComfyUI 空闲。本项目的工具设计也遵循串行调用，不要在提示词里鼓励模型并行发起生成任务。

## 2. 量化选型

`qwen3:8b` 的 Q4_K_M 版本：

- 磁盘占用 5.2GB；
- 运行时显存约 5.6GB；
- 8GB 卡上仍能留出上下文与视觉缓冲；
- 实测生成速度约 20 tok/s。

更大的量化（Q5/Q6）在 8GB 卡上会挤压上下文，速度也明显下降；更小的量化（Q3）质量损失开始明显。Q4_K_M 是当前硬件的平衡点。

## 3. 上下文不要贪大

本地 8B 模型在长上下文下：

- KV cache 占用线性增长；
- 生成速度下降；
- 显存更容易被其他服务挤爆。

因此工具结果要截断后再回传（本项目限制 6000 字符），长文档先摘要再交给模型。

## 4. CosyVoice2 的 instruct 坑

1. **`<|endofprompt|>` 不能省。** 缺少结束符时，模型会把语气指令当成正文念出来，音频时长会翻倍。前缀可以省略，结束符必须补。`integrations/cosyvoice_server.py` 中的 `_normalize_instruct` 会自动补齐。
2. **不要写英文情感值。** `happy`、`sad` 这类英文词会被念出来，用中文短祈使句更稳定，例如：「用不耐烦、有点不好意思的语气说这句话」。
3. **正文可以嵌入控制标记。** 实测 `[breath]`、`[sigh]`、`<strong>…</strong>` 会生效且不会被念出来，但不要滥用。

## 5. 服务启动耗时

| 服务 | 冷启动 |
|---|---|
| ComfyUI | 约 30–40 秒 |
| CosyVoice2 | 约 40 秒 |
| Ollama 首次加载 qwen3:8b | 数秒到十几秒 |

因此主力服务适合常驻；频繁重启会让交互体验很差。写 Agent 时要给工具调用留足超时（本项目默认 300 秒）。

## 6. Windows 下的进程生命周期

用普通方式从脚本里启动的子进程，可能在工具调用结束后被宿主清理。需要长期运行的服务，可以用计划任务、服务包装器，或用 WMI 创建脱离父进程的进程：

```powershell
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
  CommandLine = 'D:\Aurabot\tts\env\Scripts\python.exe integrations\cosyvoice_server.py'
  CurrentDirectory = 'C:\path\to\llm-agent-workflow'
}
```

## 7. 依赖与镜像

- PyTorch `cu128` 的国内镜像不一定更快，实测官方 wheel 反而更稳；先测速再换源。
- ComfyUI 的模板包在部分镜像缺依赖，界面里的「模板」页可能为空。直接用本仓库的 `workflows/text2img_sdxl.json` 更可控。
- CosyVoice2 依赖较重，建议单独虚拟环境，避免和 ComfyUI 的 torch 版本互相污染。

## 8. 显存观测

```powershell
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
ollama ps
```

`ollama ps` 的 `PROCESSOR` 列应显示 `100% GPU`；如果出现 CPU 比例，说明模型部分卸载到了内存，速度会明显变慢。
