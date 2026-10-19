import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { FileSource, PMTiles } from 'pmtiles'
import { describe, expect, it } from 'vitest'
import { insideRings, remoteAt, tileFor, toRemote } from './remote'

describe('tessere e poligoni', () => {
  it('tessera che contiene un punto', () => {
    // A z0 tutto il mondo è una tessera; Greenwich-equatore sta al centro.
    expect(tileFor(0, 0, 0, 4096)).toEqual({ x: 0, y: 0, px: 2048, py: 2048 })
    const t = tileFor(10.05, 44.65, 14, 4096)
    expect(t.x).toBe(8649)
    expect(t.y).toBe(5916)
  })

  it('pari-dispari con buco', () => {
    const outer = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 10 },
      { x: 0, y: 10 },
    ]
    const hole = [
      { x: 4, y: 4 },
      { x: 6, y: 4 },
      { x: 6, y: 6 },
      { x: 4, y: 6 },
    ]
    expect(insideRings(2, 2, [outer, hole])).toBe(true)
    expect(insideRings(5, 5, [outer, hole])).toBe(false)
    expect(insideRings(12, 5, [outer, hole])).toBe(false)
  })

  it('le proprietà assenti restano assenti', () => {
    const r = toRemote({ score: 0.8, n: 5, pts: 12, max: 15, ph: 3, elevation: 2 })
    expect(r.points).toEqual({ ph: 3, elevation: 2 })
    expect(r.score).toBe(0.8)
  })
})

const fixture = fileURLToPath(new URL('../../e2e/fixtures/synthetic-vth.pmtiles', import.meta.url))

describe.skipIf(!existsSync(fixture))('fixture sintetica della pipeline', () => {
  it('rispetta il contratto e si legge in un punto', async () => {
    const file = new File([readFileSync(fixture)], 'synthetic.pmtiles')
    const pm = new PMTiles(new FileSource(file))
    const meta = (await pm.getMetadata()) as Record<string, unknown>
    expect(meta.synthetic === true || meta.synthetic === 'true').toBe(true)
    const header = await pm.getHeader()
    // Scorre una griglia sull'area della fixture e controlla le proprietà trovate.
    let found = 0
    for (let lon = 10.0; lon <= 10.1; lon += 0.01) {
      for (let lat = 44.6; lat <= 44.7; lat += 0.01) {
        const r = await remoteAt(pm, lon, lat)
        if (!r) continue
        found++
        for (const v of Object.values(r.points)) expect(v).toBeGreaterThanOrEqual(0)
        if (r.points.hosts !== undefined) expect(r.points.hosts).toBeLessThanOrEqual(1)
        if (r.score !== undefined) {
          expect(r.score).toBeGreaterThanOrEqual(0)
          expect(r.score).toBeLessThanOrEqual(1)
          expect(r.score).toBeCloseTo(r.pts! / r.max!, 2)
        }
      }
    }
    expect(found).toBeGreaterThan(0)
    expect(header.maxZoom).toBeGreaterThanOrEqual(12)
  })
})
