import { describe, expect, it } from 'vitest'
import { bearing, compass, distance } from './geo'
import { averageFixes } from './geolocation'

describe('direzioni', () => {
  it('bearing e punti cardinali', () => {
    const a: [number, number] = [10, 44.6]
    expect(Math.round(bearing(a, [10, 44.7]))).toBe(0)
    expect(Math.round(bearing(a, [10.1, 44.6]))).toBe(90)
    expect(Math.round(bearing(a, [10, 44.5]))).toBe(180)
    expect(Math.round(bearing(a, [9.9, 44.6]))).toBe(270)
    expect(compass(44)).toBe('NE')
    expect(compass(350)).toBe('N')
    expect(compass(200)).toBe('S')
    expect(compass(250)).toBe('O')
  })

  it('distanza di un decimo di grado di latitudine', () => {
    expect(distance([10, 44.6], [10, 44.7])).toBeCloseTo(11119.5, 0)
  })
})

describe('media delle letture GPS', () => {
  it('pesa di più le letture precise', () => {
    const avg = averageFixes([
      { lon: 10, lat: 44.6, acc: 5, alt: 500, t: 1 },
      { lon: 10.001, lat: 44.601, acc: 50, alt: null, t: 2 },
    ])!
    expect(avg.lon).toBeLessThan(10.0001)
    expect(avg.lat).toBeLessThan(44.6001)
    expect(avg.alt).toBe(500)
    expect(avg.t).toBe(2)
    expect(avg.acc).toBeLessThanOrEqual(5)
    expect(avg.acc).toBeGreaterThanOrEqual(2.5)
  })

  it('nessuna lettura, nessuna media', () => {
    expect(averageFixes([])).toBeNull()
  })
})
