import { reactive } from 'vue'
import { acquireLocation, type Fix } from '../lib/geolocation'
import { distance, minDistanceToTrack } from '../lib/geo'
import { settings } from '../settings/settings'
import { db, newId, nowIso, type Outing, type TrackPoint } from './db'

/** Sotto questa precisione il punto non entra nella traccia. */
const MAX_ACCURACY_M = 50
/** Spostamento minimo tra due punti salvati. */
const MIN_STEP_M = 5
/** Uno spot conta come visitato se la traccia ci passa entro questa distanza. */
export const VISIT_RADIUS_M = 75

export const tracking = reactive({
  outingId: null as string | null,
  points: 0,
  lastFix: null as Fix | null,
  wakeLock: false,
})

let release: (() => void) | null = null
let lastSaved: TrackPoint | null = null
let wakeLock: WakeLockSentinel | null = null

async function acquireWakeLock() {
  if (!settings.wakeLock || !('wakeLock' in navigator)) return
  try {
    wakeLock = await navigator.wakeLock.request('screen')
    tracking.wakeLock = true
    wakeLock.addEventListener('release', () => (tracking.wakeLock = false))
  } catch {
    tracking.wakeLock = false
  }
}

function onVisibility() {
  // Il browser rilascia il wake lock quando la pagina va in background: lo riprendo al ritorno.
  if (document.visibilityState === 'visible' && tracking.outingId && (!wakeLock || wakeLock.released)) {
    void acquireWakeLock()
  }
}

async function onFix(fix: Fix) {
  tracking.lastFix = fix
  const id = tracking.outingId
  if (!id || fix.acc > MAX_ACCURACY_M) return
  if (lastSaved && distance([lastSaved.lon, lastSaved.lat], [fix.lon, fix.lat]) < MIN_STEP_M) return
  const p: TrackPoint = { lon: fix.lon, lat: fix.lat, t: fix.t, acc: Math.round(fix.acc), alt: fix.alt }
  lastSaved = p
  await db.outings.where('id').equals(id).modify((o) => {
    o.track.push(p)
  })
  tracking.points++
}

function startRecording(outing: Outing) {
  tracking.outingId = outing.id
  tracking.points = outing.track.length
  lastSaved = outing.track.at(-1) ?? null
  release?.()
  release = acquireLocation(onFix)
  void acquireWakeLock()
  document.addEventListener('visibilitychange', onVisibility)
}

function stopRecording() {
  release?.()
  release = null
  tracking.outingId = null
  tracking.points = 0
  lastSaved = null
  void wakeLock?.release()
  wakeLock = null
  document.removeEventListener('visibilitychange', onVisibility)
}

export async function activeOuting(): Promise<Outing | undefined> {
  const open = await db.outings.filter((o) => !o.endedAt).toArray()
  return open.sort((a, b) => b.date.localeCompare(a.date))[0]
}

/** Riprende la registrazione se l'app è stata chiusa durante un'uscita. */
export async function resumeOuting(): Promise<void> {
  const o = await activeOuting()
  if (o && !tracking.outingId) startRecording(o)
}

export async function startOuting(): Promise<Outing> {
  const existing = await activeOuting()
  if (existing) {
    startRecording(existing)
    return existing
  }
  const outing: Outing = { id: newId(), date: nowIso(), dog: settings.dog, track: [], spotsVisited: [] }
  await db.outings.add(outing)
  startRecording(outing)
  return outing
}

/** Spot toccati dalla traccia o con un ritrovamento vicino. */
export async function detectVisitedSpots(outing: Outing): Promise<string[]> {
  const spots = await db.spots.toArray()
  const finds = await db.finds.where('outingId').equals(outing.id).toArray()
  const visited = new Set(outing.spotsVisited)
  for (const s of spots) {
    if (s.geom.type !== 'Point') continue
    const p = s.geom.coordinates as [number, number]
    const nearTrack = outing.track.length && minDistanceToTrack(p, outing.track) <= VISIT_RADIUS_M
    const nearFind = finds.some((f) => distance(p, f.position) <= VISIT_RADIUS_M)
    if (nearTrack || nearFind) visited.add(s.id)
  }
  return [...visited]
}

export async function endOuting(id: string): Promise<void> {
  const outing = await db.outings.get(id)
  if (!outing) return
  const spotsVisited = await detectVisitedSpots(outing)
  await db.outings.update(id, { endedAt: nowIso(), spotsVisited })
  if (tracking.outingId === id) stopRecording()
}
