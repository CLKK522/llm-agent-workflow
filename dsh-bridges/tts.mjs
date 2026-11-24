// DSH 本地接口 · 语音合成：转给本机 CosyVoice2 服务。
// 参数：{ text, outDir, log }；返回生成的 wav 文件路径。
import { writeFileSync } from 'node:fs'
import { join } from 'node:path'

const API = (process.env.COSYVOICE_URL || 'http://127.0.0.1:50002') + '/inference_sft'

export default async function tts({ text, outDir, log }) {
  const body = new URLSearchParams({ tts_text: text, spk_id: '' })
  const response = await fetch(API, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
    signal: AbortSignal.timeout(300000),
  })
  if (!response.ok) {
    throw new Error(`本地 TTS 返回 ${response.status}：${(await response.text()).slice(0, 200)}`)
  }
  const file = join(outDir, `tts-${Date.now()}.wav`)
  writeFileSync(file, Buffer.from(await response.arrayBuffer()))
  try {
    log?.info?.(`本地语音合成完成：${String(text).slice(0, 20)}`)
  } catch {}
  return file
}
