import { describe, expect, it } from 'vitest'
import { legalWindow, sunTimes } from './sun'

// Riferimenti calcolati con la libreria Python astral (indipendente), orari UTC.
const CASES = [
  { lat: 44.801, lon: 10.328, date: [2026, 10, 20], rise: '2026-10-20T05:40:41Z', set: '2026-10-20T16:25:32Z' },
  { lat: 44.6, lon: 10.1, date: [2027, 6, 21], rise: '2027-06-21T03:34:41Z', set: '2027-06-21T19:08:02Z' },
  { lat: 44.6, lon: 10.1, date: [2027, 1, 15], rise: '2027-01-15T06:53:26Z', set: '2027-01-15T16:04:43Z' },
  { lat: 44.801, lon: 10.328, date: [2027, 3, 28], rise: '2027-03-28T05:07:53Z', set: '2027-03-28T17:40:31Z' },
]

const minutes = (a: Date, b: string) => Math.abs(a.getTime() - new Date(b).getTime()) / 60_000

describe('alba e tramonto', () => {
  it.each(CASES)('entro 3 minuti da astral ($date)', ({ lat, lon, date, rise, set }) => {
    const t = sunTimes(new Date(date[0], date[1] - 1, date[2]), lat, lon)!
    expect(minutes(t.sunrise, rise)).toBeLessThan(3)
    expect(minutes(t.sunset, set)).toBeLessThan(3)
  })

  it('finestra legale: un\'ora prima dell\'alba, un\'ora dopo il tramonto, meno il margine', () => {
    const d = new Date(2026, 9, 20)
    const t = sunTimes(d, 44.801, 10.328)!
    const exact = legalWindow(d, 44.801, 10.328, 60, 60, 0)!
    expect(t.sunrise.getTime() - exact.from.getTime()).toBe(3_600_000)
    expect(exact.to.getTime() - t.sunset.getTime()).toBe(3_600_000)
    const safe = legalWindow(d, 44.801, 10.328, 60, 60)!
    expect(safe.from.getTime() - exact.from.getTime()).toBe(5 * 60_000)
    expect(exact.to.getTime() - safe.to.getTime()).toBe(5 * 60_000)
  })
})
