import { ArrayBufferTarget, Muxer } from 'mp4-muxer'

// Frame-exact export: draws every frame at its own time, encodes it as H.264 with the sound as AAC (Opus where the
// browser has no AAC encoder), and saves the MP4 through serve.ts, by default into the Downloads folder.

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/** The first audio codec that this browser can encode: [encoder config, muxer codec name], or null. */
async function audioCodec(sampleRate) {
  if (!('AudioEncoder' in window)) return null
  for (const [codec, name] of [
    ['mp4a.40.2', 'aac'],
    ['opus', 'opus'],
  ]) {
    const config = { codec, sampleRate, numberOfChannels: 2, bitrate: 192_000 }
    if ((await AudioEncoder.isConfigSupported(config)).supported) return [config, name]
  }
  return null
}

/** Encodes the from–to part of the stereo AudioBuffer `audio` into the muxer's audio track. */
async function encodeSound(muxer, audio, config, from, to, fail) {
  const encoder = new AudioEncoder({ output: (chunk, meta) => muxer.addAudioChunk(chunk, meta), error: fail })
  encoder.configure(config)
  const rate = audio.sampleRate
  const first = Math.round(from * rate)
  const last = Math.min(audio.length, Math.round(to * rate))
  const left = audio.getChannelData(0)
  const right = audio.getChannelData(1)
  for (let i = first; i < last; i += 1024) {
    const frames = Math.min(1024, last - i)
    const data = new Float32Array(frames * 2)
    data.set(left.subarray(i, i + frames), 0)
    data.set(right.subarray(i, i + frames), frames)
    const chunk = new AudioData({
      format: 'f32-planar',
      sampleRate: rate,
      numberOfFrames: frames,
      numberOfChannels: 2,
      timestamp: Math.round(((i - first) / rate) * 1e6),
      data,
    })
    encoder.encode(chunk)
    chunk.close()
  }
  await encoder.flush()
}

/**
 * Renders the time range from–to of the player at `fps`, with the matching part of `audio` (an AudioBuffer of the
 * whole video, or null), and saves it under `name` (saveTo 'out' puts it in video/out/ instead of Downloads).
 * draw(time) must paint the frame for that time on `canvas`.
 * Returns the path of the saved file.
 */
export async function exportMp4({ canvas, from, to, fps, draw, audio, name, saveTo, onProgress }) {
  const { width, height } = canvas
  // H.264 level 4.0 holds up to 8,192 macroblocks a frame (1920×1080); a bigger picture such as 1920×1200 needs 5.0
  const blocks = Math.ceil(width / 16) * Math.ceil(height / 16)
  const codec = blocks > 8192 ? 'avc1.640032' : 'avc1.640028'
  const config = { codec, width, height, bitrate: 12_000_000, framerate: fps }
  if (!('VideoEncoder' in window) || !(await VideoEncoder.isConfigSupported(config)).supported) {
    throw new Error('this browser cannot encode H.264 with WebCodecs')
  }
  const sound = audio ? await audioCodec(audio.sampleRate) : null
  const muxer = new Muxer({
    target: new ArrayBufferTarget(),
    video: { codec: 'avc', width, height },
    audio: sound ? { codec: sound[1], numberOfChannels: 2, sampleRate: audio.sampleRate } : undefined,
    fastStart: 'in-memory',
    firstTimestampBehavior: 'offset',
  })
  let failure = null
  const fail = (error) => {
    failure = error
  }
  if (sound) await encodeSound(muxer, audio, sound[0], from, to, fail)
  const encoder = new VideoEncoder({ output: (chunk, meta) => muxer.addVideoChunk(chunk, meta), error: fail })
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
  const where = saveTo ? `&to=${saveTo}` : ''
  const response = await fetch(`/save?name=${encodeURIComponent(name)}${where}`, {
    method: 'POST',
    body: muxer.target.buffer,
  })
  if (!response.ok) throw new Error(`saving failed: ${response.status}`)
  return (await response.json()).file
}
