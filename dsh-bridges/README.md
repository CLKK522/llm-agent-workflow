# DSH 本地接口桥接

实际部署时，Agent 的宿主环境是 DSH（DeepSeek Harness）。DSH 允许用本地 Node.js 脚本接管内置能力：

- 文件是 ES Module（`.mjs`），导出 `export default async function (参数) { ... }`；
- 可以使用 Node 自带的 `fetch`、`node:fs`、`node:child_process`，但不能安装第三方包；
- 失败时 `throw new Error(...)`，宿主会决定回退内置能力还是告知用户；
- 通过参数里的 `log.info()` 写日志。

这里的 `tts.mjs` 与 `image.mjs` 是当时实际使用的桥接脚本的脱敏版：去掉了本机绝对路径和个人音色配置，端点改为环境变量。它们只作为 DSH 接口示例保留，脱离 DSH 无法直接运行。

| 文件 | 接管能力 | 下游服务 |
|---|---|---|
| `tts.mjs` | 语音合成 | 本地 CosyVoice2 `POST /inference_sft` |
| `image.mjs` | 文生图 | 本地 ComfyUI `POST /prompt` |

环境变量：

```bash
COSYVOICE_URL=http://127.0.0.1:50002
COMFYUI_URL=http://127.0.0.1:8188
COMFYUI_CKPT=Illustrious-XL-v1.0.safetensors
```

DSH 的宿主本身不是本仓库的一部分；本仓库的 `agent/` 提供了脱离宿主也能运行的最小实现。
