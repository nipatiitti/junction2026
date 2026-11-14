// Serves the joke-video player and saves the videos it renders.
//   node video/serve.ts [--port 8790] [--out <folder>]
// GET serves the files under video/. POST /save?name=<file>.mp4 writes the body to the Downloads folder (or --out),
// next to any earlier file of that name; /save?to=out writes to video/out/ instead (stills for checks).
// GET /voices lists the recorded voice lines in video/audio/voice/.
// GET /events sends `reload` when a file under video/ changes, so the page reloads at the same view and time.
import { createReadStream, existsSync, mkdirSync, readdirSync, statSync, watch, writeFileSync } from 'node:fs'
import { createServer, type ServerResponse } from 'node:http'
import { homedir } from 'node:os'
import { dirname, extname, join, normalize, parse, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = dirname(fileURLToPath(import.meta.url))
const option = (name: string) => {
  const at = process.argv.indexOf(name)
  return at > 0 ? process.argv[at + 1] : undefined
}
const port = Number(option('--port') ?? 8790)
const downloads = resolve(option('--out') ?? join(homedir(), 'Downloads'))
const scratch = join(root, 'out')
const voices = join(root, 'audio', 'voice')

const types: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.md': 'text/markdown; charset=utf-8',
  '.mp4': 'video/mp4',
  '.png': 'image/png',
  '.mp3': 'audio/mpeg',
  '.m4a': 'audio/mp4',
  '.wav': 'audio/wav',
  '.ogg': 'audio/ogg',
}

/** The first free path for `name` in `folder`: name.mp4, name-2.mp4, name-3.mp4, ... */
function freePath(folder: string, name: string) {
  const { name: base, ext } = parse(name)
  let path = join(folder, name)
  for (let n = 2; existsSync(path); n++) path = join(folder, `${base}-${n}${ext}`)
  return path
}

const clients = new Set<ServerResponse>()
let pending: ReturnType<typeof setTimeout> | undefined
watch(root, { recursive: true }, (_event, file) => {
  if (!file || file === 'out' || file.startsWith(`out${sep}`)) return
  clearTimeout(pending)
  pending = setTimeout(() => {
    for (const client of clients) client.write('data: reload\n\n')
  }, 120)
})

createServer((req, res) => {
  const url = new URL(req.url ?? '/', 'http://localhost')
  if (url.pathname === '/events') {
    res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-store', connection: 'keep-alive' })
    res.write('retry: 1000\n\n')
    clients.add(res)
    req.on('close', () => clients.delete(res))
    return
  }
  if (url.pathname === '/voices') {
    const files = existsSync(voices) ? readdirSync(voices).filter((f) => types[extname(f)]?.startsWith('audio/')) : []
    res.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store' })
    res.end(JSON.stringify(files))
    return
  }
  if (req.method === 'POST' && url.pathname === '/save') {
    const name = (url.searchParams.get('name') ?? 'video.mp4').replace(/[^\w.-]/g, '_')
    const toScratch = url.searchParams.get('to') === 'out'
    const chunks: Buffer[] = []
    req.on('data', (chunk: Buffer) => chunks.push(chunk))
    req.on('end', () => {
      const folder = toScratch ? scratch : downloads
      mkdirSync(folder, { recursive: true })
      const file = toScratch ? join(folder, name) : freePath(folder, name)
      writeFileSync(file, Buffer.concat(chunks))
      console.log(`saved ${file}`)
      res.writeHead(200, { 'content-type': 'application/json' })
      res.end(JSON.stringify({ file }))
    })
    return
  }
  const path = normalize(join(root, url.pathname === '/' ? 'index.html' : decodeURIComponent(url.pathname)))
  if (!path.startsWith(root) || !existsSync(path) || !statSync(path).isFile()) {
    res.writeHead(404, { 'content-type': 'text/plain' })
    res.end('Not found')
    return
  }
  res.writeHead(200, {
    'content-type': types[extname(path)] ?? 'application/octet-stream',
    'cache-control': 'no-store',
  })
  createReadStream(path).pipe(res)
}).listen(port, () => console.log(`Joke-video player: http://localhost:${port} (videos go to ${downloads})`))
