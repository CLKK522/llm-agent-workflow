// DSH 本地接口 · 生图：转给本机 ComfyUI。
// 参数：{ prompt, size, outDir, log }；返回图片 Buffer。
const API = process.env.COMFYUI_URL || 'http://127.0.0.1:8188'
const CKPT = process.env.COMFYUI_CKPT || 'Illustrious-XL-v1.0.safetensors'

export default async function image({ prompt, size, log }) {
  const match = String(size || '832x1216').toLowerCase().match(/(\d+)\s*[x*×]\s*(\d+)/)
  let width = match ? parseInt(match[1], 10) : 832
  let height = match ? parseInt(match[2], 10) : 1216
  width = Math.max(512, Math.min(1536, Math.round(width / 64) * 64))
  height = Math.max(512, Math.min(1536, Math.round(height / 64) * 64))

  const workflow = {
    '3': { class_type: 'KSampler', inputs: { seed: Math.floor(Math.random() * 1e9), steps: 28, cfg: 5.5, sampler_name: 'dpmpp_2m', scheduler: 'karras', denoise: 1.0, model: ['4', 0], positive: ['6', 0], negative: ['7', 0], latent_image: ['5', 0] } },
    '4': { class_type: 'CheckpointLoaderSimple', inputs: { ckpt_name: CKPT } },
    '5': { class_type: 'EmptyLatentImage', inputs: { width, height, batch_size: 1 } },
    '6': { class_type: 'CLIPTextEncode', inputs: { text: String(prompt || ''), clip: ['4', 1] } },
    '7': { class_type: 'CLIPTextEncode', inputs: { text: 'lowres, worst quality, bad anatomy, watermark, text, signature', clip: ['4', 1] } },
    '8': { class_type: 'VAEDecode', inputs: { samples: ['3', 0], vae: ['4', 2] } },
    '9': { class_type: 'SaveImage', inputs: { filename_prefix: 'aurabot', images: ['8', 0] } },
  }

  const submit = await fetch(API + '/prompt', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ prompt: workflow, client_id: 'aurabot-' + Date.now() }),
    signal: AbortSignal.timeout(30000),
  })
  if (!submit.ok) {
    throw new Error('ComfyUI 提交失败 ' + submit.status + '：' + (await submit.text()).slice(0, 200))
  }
  const { prompt_id } = await submit.json()
  try {
    log?.info?.('ComfyUI 开始出图：' + String(prompt).slice(0, 24))
  } catch {}

  let output = null
  const deadline = Date.now() + 5 * 60 * 1000
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 1500))
    const response = await fetch(API + '/history/' + prompt_id, { signal: AbortSignal.timeout(15000) })
    if (!response.ok) continue
    const data = await response.json()
    const entry = data[prompt_id]
    if (entry && entry.outputs) {
      for (const node of Object.values(entry.outputs)) {
        if (node.images && node.images.length) {
          output = node.images[0]
          break
        }
      }
      if (output) break
    }
  }
  if (!output) throw new Error('ComfyUI 超时，没有出图')

  const query = new URLSearchParams({
    filename: output.filename,
    subfolder: output.subfolder || '',
    type: output.type || 'output',
  })
  const imageResponse = await fetch(API + '/view?' + query.toString(), {
    signal: AbortSignal.timeout(60000),
  })
  if (!imageResponse.ok) throw new Error('取图失败 ' + imageResponse.status)
  const buffer = Buffer.from(await imageResponse.arrayBuffer())
  try {
    log?.info?.('ComfyUI 出图完成 ' + Math.round(buffer.length / 1024) + 'KB')
  } catch {}
  return buffer
}
