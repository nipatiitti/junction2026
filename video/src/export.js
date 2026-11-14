import { ArrayBufferTarget, Muxer } from 'mp4-muxer'

// Frame-exact export: draws every frame at its own time, encodes it as H.264 and saves the MP4 through serve.ts.

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/**
 * Renders the time range from–to of the player at `fps` and saves it as video/out/<name>.
 * draw(time) must paint the frame for that time on `canvas`. Returns the path of the saved file.
 */
export async function exportMp4({ canvas, from, to, fps, draw, name, onProgress }) {
  const { width, height } = canvas
  const config = { codec: 'avc1.640028', width, height, bitrate: 12_000_000, framerate: fps }
  if (!('VideoEncoder' in window) || !(await VideoEncoder.isConfigSupported(config)).supported) {
    throw new Error('this browser cannot encode H.264 with WebCodecs')
  }
  const muxer = new Muxer({
    target: new ArrayBufferTarget(),
    video: { codec: 'avc', width, height },
    fastStart: 'in-memory',
  })
  let failure = null
  const encoder = new VideoEncoder({
    output: (chunk, meta) => muxer.addVideoChunk(chunk, meta),
    error: (error) => {
      failure = error
    },
  })
  encoder.configure(config)
  const frames = Math.round((to - from) * fps)
  for (let i = 0; i < frames; i++) {
    if (failure) throw failure
    draw(from + i / fps)
    const frame = new VideoFrame(canvas, { timestamp: Math.round((i * 1e6) / fps), duration: Math.round(1e6 / fps) })
    encoder.encode(frame, { keyFrame: i % (fps * 2) === 0 })
    frame.close()
    while (encoder.encodeQueueSize > 6) await wait(1)
    if (i % 15 === 0) {
      onProgress?.(i / frames)
      await wait(0)
    }
  }
  await encoder.flush()
  if (failure) throw failure
  muxer.finalize()
  const response = await fetch(`/save?name=${encodeURIComponent(name)}`, {
    method: 'POST',
    body: muxer.target.buffer,
  })
  if (!response.ok) throw new Error(`saving failed: ${response.status}`)
  return (await response.json()).file
}
