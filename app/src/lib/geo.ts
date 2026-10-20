import type { LineString } from 'geojson'
import type { TrackPoint } from '../diary/db'

const R = 6_371_008.8

/** Distanza in metri tra due punti [lon, lat]. */
export function distance(a: [number, number], b: [number, number]): number {
  const toRad = (x: number) => (x * Math.PI) / 180
  const dLat = toRad(b[1] - a[1])
  const dLon = toRad(b[0] - a[0])
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[1])) * Math.cos(toRad(b[1])) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)))
}

export function trackLength(track: TrackPoint[]): number {
  let len = 0
  for (let i = 1; i < track.length; i++) {
    len += distance([track[i - 1].lon, track[i - 1].lat], [track[i].lon, track[i].lat])
  }
  return len
}

export function trackToLineString(track: TrackPoint[]): LineString {
  return { type: 'LineString', coordinates: track.map((p) => [p.lon, p.lat]) }
}

/** Distanza minima tra un punto e i vertici della traccia (basta: i punti sono fitti). */
export function minDistanceToTrack(p: [number, number], track: TrackPoint[]): number {
  let min = Infinity
  for (const t of track) min = Math.min(min, distance(p, [t.lon, t.lat]))
  return min
}

/** Poligono circolare approssimato, per il cerchio di precisione del GPS. */
export function circle(center: [number, number], radiusM: number, steps = 48): [number, number][] {
  const [lon, lat] = center
  const dLat = (radiusM / R) * (180 / Math.PI)
  const dLon = dLat / Math.cos((lat * Math.PI) / 180)
  const ring: [number, number][] = []
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * 2 * Math.PI
    ring.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)])
  }
  return ring
}

/** Direzione in gradi (0 = nord, senso orario) da a verso b. */
export function bearing(a: [number, number], b: [number, number]): number {
  const toRad = (x: number) => (x * Math.PI) / 180
  const dLon = toRad(b[0] - a[0])
  const y = Math.sin(dLon) * Math.cos(toRad(b[1]))
  const x = Math.cos(toRad(a[1])) * Math.sin(toRad(b[1])) - Math.sin(toRad(a[1])) * Math.cos(toRad(b[1])) * Math.cos(dLon)
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360
}

const COMPASS = ['N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO']

export function compass(deg: number): string {
  return COMPASS[Math.round(deg / 45) % 8]
}

export function formatDistance(m: number): string {
  return m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`
}

export function formatDuration(ms: number): string {
  const min = Math.round(ms / 60000)
  const h = Math.floor(min / 60)
  return h ? `${h} h ${min % 60} min` : `${min} min`
}

export function formatCoord(p: [number, number]): string {
  return `${p[1].toFixed(5)}, ${p[0].toFixed(5)}`
}
