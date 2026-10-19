import { reactive, readonly } from 'vue'

export interface Fix {
  lon: number
  lat: number
  acc: number
  alt: number | null
  t: number
}

type Listener = (fix: Fix) => void

const state = reactive({
  fix: null as Fix | null,
  error: null as string | null,
  watching: false,
})

let watchId: number | null = null
let users = 0
const listeners = new Set<Listener>()

function onPosition(p: GeolocationPosition) {
  const fix: Fix = {
    lon: p.coords.longitude,
    lat: p.coords.latitude,
    acc: p.coords.accuracy,
    alt: p.coords.altitude,
    t: p.timestamp,
  }
  state.fix = fix
  state.error = null
  listeners.forEach((l) => l(fix))
}

function onError(e: GeolocationPositionError) {
  state.error =
    e.code === e.PERMISSION_DENIED
      ? 'Permesso di posizione negato.'
      : e.code === e.TIMEOUT
        ? 'Il GPS non risponde, riprovo.'
        : 'Posizione non disponibile.'
}

function start() {
  if (watchId !== null) return
  if (!('geolocation' in navigator)) {
    state.error = 'Questo dispositivo non ha la geolocalizzazione.'
    return
  }
  watchId = navigator.geolocation.watchPosition(onPosition, onError, {
    enableHighAccuracy: true,
    maximumAge: 5000,
    timeout: 30000,
  })
  state.watching = true
}

function stop() {
  if (watchId === null) return
  navigator.geolocation.clearWatch(watchId)
  watchId = null
  state.watching = false
}

/** Posizione condivisa: il GPS resta acceso finché almeno un utilizzatore la tiene. Tutto resta sul telefono. */
export function acquireLocation(listener?: Listener): () => void {
  users++
  if (listener) listeners.add(listener)
  start()
  return () => {
    users = Math.max(0, users - 1)
    if (listener) listeners.delete(listener)
    if (users === 0) stop()
  }
}

export const location = readonly(state)

/** Una posizione sola, per azioni puntuali (es. ritrovamento). */
export function currentFix(maxAgeMs = 15000): Promise<Fix> {
  if (state.fix && Date.now() - state.fix.t < maxAgeMs) return Promise.resolve(state.fix)
  return new Promise((resolve, reject) => {
    if (!('geolocation' in navigator)) return reject(new Error('Geolocalizzazione non disponibile'))
    navigator.geolocation.getCurrentPosition(
      (p) => {
        onPosition(p)
        resolve(state.fix!)
      },
      (e) => {
        onError(e)
        reject(new Error(state.error ?? 'Posizione non disponibile'))
      },
      { enableHighAccuracy: true, timeout: 30000, maximumAge: maxAgeMs },
    )
  })
}
