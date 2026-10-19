import { VectorTile } from '@mapbox/vector-tile'
import Pbf from 'pbf'
import type { PMTiles } from 'pmtiles'
import { model, REMOTE_PARAMS, type ParamId } from '../field/model'
import type { RemotePoints } from '../field/vth'

export interface RemoteAt {
  score?: number
  pts?: number
  max?: number
  n?: number
  points: RemotePoints
}

/** Tessera e posizione (in unità della tessera) che contengono il punto. */
export function tileFor(lon: number, lat: number, z: number, extent: number) {
  const n = 2 ** z
  const fx = ((lon + 180) / 360) * n
  const latRad = (lat * Math.PI) / 180
  const fy = ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n
  const x = Math.floor(fx)
  const y = Math.floor(fy)
  return { x, y, px: (fx - x) * extent, py: (fy - y) * extent }
}

/** Pari-dispari su tutti gli anelli: gestisce buchi e multipoligoni. */
export function insideRings(px: number, py: number, rings: { x: number; y: number }[][]): boolean {
  let inside = false
  for (const ring of rings) {
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const a = ring[i]
      const b = ring[j]
      if (a.y > py !== b.y > py && px < ((b.x - a.x) * (py - a.y)) / (b.y - a.y) + a.x) inside = !inside
    }
  }
  return inside
}

export function toRemote(props: Record<string, unknown>): RemoteAt {
  const points: RemotePoints = {}
  for (const id of REMOTE_PARAMS) {
    const v = props[id]
    if (typeof v === 'number') points[id as ParamId] = v
  }
  const num = (k: string) => (typeof props[k] === 'number' ? (props[k] as number) : undefined)
  return { score: num('score'), pts: num('pts'), max: num('max'), n: num('n'), points }
}

/**
 * Legge lo score remoto in un punto direttamente dal PMTiles, senza mappa.
 * Serve alla checklist sul posto: posizione GPS -> parametri stimati.
 */
export async function remoteAt(pm: PMTiles, lon: number, lat: number): Promise<RemoteAt | null> {
  const header = await pm.getHeader()
  const z = header.maxZoom
  const { x, y, px, py } = tileFor(lon, lat, z, 4096)
  const res = await pm.getZxy(z, x, y)
  if (!res) return null
  const tile = new VectorTile(new Pbf(new Uint8Array(res.data)))
  const layer = tile.layers[model.tiles.layer]
  if (!layer) return null
  const scale = layer.extent / 4096
  for (let i = 0; i < layer.length; i++) {
    const f = layer.feature(i)
    if (f.type !== 3) continue
    if (insideRings(px * scale, py * scale, f.loadGeometry())) return toRemote(f.properties)
  }
  return null
}
