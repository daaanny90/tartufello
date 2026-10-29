import { liveQuery } from 'dexie'
import { reactive, watch } from 'vue'
import { distance } from '../lib/geo'
import { location, type Fix } from '../lib/geolocation'
import { db, type Spot } from './db'

/** Sotto questa distanza da uno spot "pericolo" l'app avvisa e vibra. */
export const DANGER_RADIUS_M = 300
/** Si riarma solo oltre questa distanza: sotto le chiome il GPS balla e non deve vibrare a ripetizione. */
export const DANGER_REARM_M = 400
/** Letture peggiori (posizione dalle celle) non fanno scattare né riarmare niente. */
export const DANGER_MAX_ACCURACY_M = 200

export interface DangerHit {
  spot: Spot
  d: number
}

/**
 * Aggiorna l'insieme degli spot pericolo "dentro" con una nuova posizione.
 * Restituisce quelli appena entrati (da avvisare) e tutti quelli dentro, dal più vicino.
 */
export function updateDanger(inside: Set<string>, fix: Pick<Fix, 'lon' | 'lat' | 'acc'>, spots: Spot[]): { entered: DangerHit[]; near: DangerHit[] } {
  const here: [number, number] = [fix.lon, fix.lat]
  const reliable = fix.acc <= DANGER_MAX_ACCURACY_M
  const entered: DangerHit[] = []
  const near: DangerHit[] = []
  const seen = new Set<string>()
  for (const s of spots) {
    if (s.kind !== 'pericolo' || s.geom.type !== 'Point') continue
    seen.add(s.id)
    const d = distance(here, s.geom.coordinates as [number, number])
    if (reliable && !inside.has(s.id) && d <= DANGER_RADIUS_M) {
      inside.add(s.id)
      entered.push({ spot: s, d })
    } else if (reliable && inside.has(s.id) && d > DANGER_REARM_M) {
      inside.delete(s.id)
    }
    if (inside.has(s.id)) near.push({ spot: s, d })
  }
  // Spot cancellati o non più "pericolo".
  for (const id of [...inside]) if (!seen.has(id)) inside.delete(id)
  const byDistance = (a: DangerHit, b: DangerHit) => a.d - b.d
  return { entered: entered.sort(byDistance), near: near.sort(byDistance) }
}

/** Avviso mostrato in tutta l'app. "dismissed" si azzera quando si entra nel raggio di un altro spot. */
export const danger = reactive({
  near: [] as DangerHit[],
  dismissed: false,
})

function vibrate() {
  try {
    navigator.vibrate?.([400, 200, 400, 200, 400])
  } catch {
    /* niente vibrazione (iPhone): resta l'avviso a schermo */
  }
}

let started = false

/** Controlla la distanza dagli spot pericolo a ogni posizione, finché il GPS è acceso (uscita o mappa aperta). */
export function watchDanger(): void {
  if (started) return
  started = true
  const inside = new Set<string>()
  let spots: Spot[] = []

  const check = (alert: boolean) => {
    const f = location.fix
    if (!f || !location.watching) return
    const { entered, near } = updateDanger(inside, f, spots)
    danger.near = near
    if (entered.length && alert) {
      danger.dismissed = false
      vibrate()
    }
  }

  // Uno spot appena segnato dove sono non deve farmi vibrare in mano: entra in silenzio.
  liveQuery(() => db.spots.where('kind').equals('pericolo').toArray()).subscribe((s) => {
    spots = s
    check(false)
  })
  watch(
    () => location.fix,
    () => check(true),
  )
  // GPS spento: l'avviso sarebbe vecchio. Alla riaccensione vicino a un pericolo riavvisa.
  watch(
    () => location.watching,
    (on) => {
      if (on) return
      inside.clear()
      danger.near = []
    },
  )
}
