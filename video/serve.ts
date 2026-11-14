// Serves the joke-video player and saves the videos it renders.
//   node video/serve.ts [--port 8790]
// GET serves the files under video/. POST /save?name=<file>.mp4 writes the body to video/out/.
// GET /events sends `reload` when a file under video/ changes, so the page reloads at the same view and time.
import { createReadStream, existsSync, mkdirSync, statSync, watch, writeFileSync } from 'node:fs'
import { createServer, type ServerResponse } from 'node:http'
import { dirname, extname, join, normalize, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = dirname(fileURLToPath(import.meta.url))
const outDir = join(root, 'out')
const portAt = process.argv.indexOf('--port')
const port = portAt > 0 ? Number(process.argv[portAt + 1]) : 8790

const types: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.md': 'text/markdown; charset=utf-8',
  '.mp4': 'video/mp4',
  '.png': 'image/png',
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
  if (req.method === 'POST' && url.pathname === '/save') {
    const name = (url.searchParams.get('name') ?? 'video.mp4').replace(/[^\w.-]/g, '_')
    const chunks: Buffer[] = []
    req.on('data', (chunk: Buffer) => chunks.push(chunk))
    req.on('end', () => {
      mkdirSync(outDir, { recursive: true })
      const file = join(outDir, name)
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
}).listen(port, () => console.log(`Joke-video player: http://localhost:${port}`))
