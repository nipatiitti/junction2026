// Local stand-in for https://spread.bahnexpress.com: same routes, same JSON.
//   pnpm sim [--port 8787]        then   SPREAD_URL=http://localhost:8787 <your system>
// Any key works. Each key has its own worlds. No rate limit, no 8-world cap. No WebSocket stream, no final.
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http'
import * as S from './world.ts'

const port = Number(process.argv[process.argv.indexOf('--port') + 1]) || 8787
if (process.argv.includes('--full-fork-history')) S.setFullForkHistory(true) // as the server: slower
const worlds = new Map<string, any>()
type Reply = { status: number; body: any }
const json = (body: any, status = 200): Reply => ({ status, body })
const err = (status: number, error: string) => json({ error }, status)

async function readJson(req: IncomingMessage): Promise<any> {
  const chunks: Buffer[] = []
  for await (const c of req) chunks.push(c as Buffer)
  const text = Buffer.concat(chunks).toString()
  return text ? JSON.parse(text) : {}
}

async function route(req: IncomingMessage): Promise<Reply> {
  const url = new URL(req.url ?? '/', 'http://localhost'),
    path = url.pathname.split('/').filter(Boolean),
    m = req.method
  if (url.pathname === '/v1/map') return json(S.MAP)
  const key = req.headers.authorization ?? ''
  if (path[0] !== 'v1' || path[1] !== 'worlds') return err(404, 'Not found')
  if (path.length === 2) {
    if (m === 'GET')
      return json(
        [...worlds.values()]
          .filter((w) => w.key === key)
          .map((w) => ({
            worldId: w.worldId,
            kind: 'practice',
            level: w.level,
            parent: w.parent ?? null,
            season: null,
            boardRun: null,
            ended: w.ended,
          })),
      )
    const b: any = await readJson(req)
    if (b.board) return err(409, 'The simulator has no ranking rounds')
    const W = S.createWorld(b.seed ?? `random-${Math.random().toString(36).slice(2)}`, b.level ?? 8)
    W.key = key
    worlds.set(W.worldId, W)
    return json({ worldId: W.worldId }, 201)
  }
  const W = worlds.get(path[2])
  if (!W) return err(404, `No world ${path[2]}`)
  const what = path[3]
  if (!what) {
    if (m === 'DELETE') {
      worlds.delete(W.worldId)
      return json(null, 204)
    }
    return json(S.snapshot(W))
  }
  if (what === 'actions') return json(S.act(W, (await readJson(req)) as any[]))
  if (what === 'advance') return json(S.advance(W, await readJson(req)))
  if (what === 'events')
    return json(
      S.events(W, Number(url.searchParams.get('after') ?? -1), Number(url.searchParams.get('limit')) || undefined),
    )
  if (what === 'drivers') return json(S.roster(W))
  if (what === 'score') return json(S.score(W))
  if (what === 'fork') {
    const C = S.fork(W)
    worlds.set(C.worldId, C)
    return json({ worldId: C.worldId }, 201)
  }
  if (what === 'reveal') return W.ended ? json(S.reveal(W)) : err(409, 'The world has not ended')
  return err(404, 'Not found')
}

const server = createServer(async (req: IncomingMessage, res: ServerResponse) => {
  let r: Reply
  try {
    r = await route(req)
  } catch (e: any) {
    console.error(e)
    r = err(500, String(e?.message ?? e))
  }
  if (r.body === null) {
    res.writeHead(r.status).end()
    return
  }
  res.writeHead(r.status, { 'content-type': 'application/json' }).end(JSON.stringify(r.body))
})
server.keepAliveTimeout = 120_000
server.listen(port, () => console.log(`Spread simulator on http://localhost:${port}`))
