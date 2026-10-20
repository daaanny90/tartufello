/**
 * Alba e tramonto (algoritmo NOAA semplificato, come SunCalc).
 * Confrontato con astral (Python): scarti fino a circa 2,5 minuti. Per questo la
 * finestra legale si mostra ristretta di SAFETY_MIN minuti per lato.
 */

/** Margine prudenziale sull'imprecisione del calcolo, in minuti. */
export const SAFETY_MIN = 5

const RAD = Math.PI / 180
const DAY_MS = 86_400_000
const J1970 = 2440588
const J2000 = 2451545
const J0 = 0.0009
const OBLIQUITY = RAD * 23.4397
/** Altezza del sole all'alba/tramonto: rifrazione + raggio del disco. */
const H0 = RAD * -0.833

const toJulian = (d: Date) => d.valueOf() / DAY_MS - 0.5 + J1970
const fromJulian = (j: number) => new Date((j + 0.5 - J1970) * DAY_MS)
const toDays = (d: Date) => toJulian(d) - J2000

const meanAnomaly = (d: number) => RAD * (357.5291 + 0.98560028 * d)

function eclipticLongitude(m: number): number {
  const c = RAD * (1.9148 * Math.sin(m) + 0.02 * Math.sin(2 * m) + 0.0003 * Math.sin(3 * m))
  return m + c + RAD * 102.9372 + Math.PI
}

const declination = (l: number) => Math.asin(Math.sin(OBLIQUITY) * Math.sin(l))

export interface SunTimes {
  sunrise: Date
  sunset: Date
}

/** null se il sole non sorge o non tramonta (non succede alle nostre latitudini). */
export function sunTimes(date: Date, lat: number, lon: number): SunTimes | null {
  // Mezzogiorno locale per prendere il giorno giusto anche vicino alla mezzanotte.
  const noon = new Date(date.getFullYear(), date.getMonth(), date.getDate(), 12)
  const lw = RAD * -lon
  const phi = RAD * lat
  const d = toDays(noon)
  const n = Math.round(d - J0 - lw / (2 * Math.PI))
  const ds = J0 + lw / (2 * Math.PI) + n
  const m = meanAnomaly(ds)
  const l = eclipticLongitude(m)
  const dec = declination(l)
  const jNoon = J2000 + ds + 0.0053 * Math.sin(m) - 0.0069 * Math.sin(2 * l)
  const cosW = (Math.sin(H0) - Math.sin(phi) * Math.sin(dec)) / (Math.cos(phi) * Math.cos(dec))
  if (cosW < -1 || cosW > 1) return null
  const w = Math.acos(cosW)
  const a = J0 + (w + lw) / (2 * Math.PI) + n
  const jSet = J2000 + a + 0.0053 * Math.sin(m) - 0.0069 * Math.sin(2 * l)
  const jRise = jNoon - (jSet - jNoon)
  return { sunrise: fromJulian(jRise), sunset: fromJulian(jSet) }
}

export interface Window {
  from: Date
  to: Date
}

/**
 * Finestra in cui la ricerca è consentita: da N minuti prima dell'alba a M minuti
 * dopo il tramonto, ristretta di `safetyMin` per lato.
 */
export function legalWindow(
  date: Date,
  lat: number,
  lon: number,
  beforeSunriseMin: number,
  afterSunsetMin: number,
  safetyMin = SAFETY_MIN,
): Window | null {
  const t = sunTimes(date, lat, lon)
  if (!t) return null
  return {
    from: new Date(t.sunrise.getTime() - (beforeSunriseMin - safetyMin) * 60_000),
    to: new Date(t.sunset.getTime() + (afterSunsetMin - safetyMin) * 60_000),
  }
}

export function formatTime(d: Date): string {
  return d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })
}
