import { describe, expect, it } from 'vitest'
import { DANGER_RADIUS_M, DANGER_REARM_M, updateDanger } from './danger'
import type { Spot } from './db'

const spot = (id: string, lon: number, lat: number, kind: Spot['kind'] = 'pericolo'): Spot => ({
  id,
  name: id,
  kind,
  hazard: kind === 'pericolo' ? 'esca' : undefined,
  geom: { type: 'Point', coordinates: [lon, lat] },
  createdAt: '2026-10-29T08:00:00Z',
})

// Un grado di latitudine sono circa 111,2 km: metri -> gradi verso nord.
const north = (m: number) => ({ lon: 10, lat: 44.6 + m / 111195, acc: 8 })

describe('avviso pericolo', () => {
  it('scatta una volta entrando nel raggio e si riarma solo uscendo oltre la soglia', () => {
    const spots = [spot('esca', 10, 44.6)]
    const inside = new Set<string>()
    expect(updateDanger(inside, north(500), spots).entered).toEqual([])

    const first = updateDanger(inside, north(DANGER_RADIUS_M - 20), spots)
    expect(first.entered.map((h) => h.spot.id)).toEqual(['esca'])
    expect(first.near[0].d).toBeCloseTo(DANGER_RADIUS_M - 20, 0)

    // Il GPS balla tra raggio e soglia: niente nuove vibrazioni, l'avviso resta.
    for (const m of [200, DANGER_RADIUS_M + 50, DANGER_RADIUS_M - 10]) {
      const r = updateDanger(inside, north(m), spots)
      expect(r.entered).toEqual([])
      expect(r.near.map((h) => h.spot.id)).toEqual(['esca'])
    }

    expect(updateDanger(inside, north(DANGER_REARM_M + 30), spots).near).toEqual([])
    expect(updateDanger(inside, north(DANGER_RADIUS_M - 20), spots).entered).toHaveLength(1)
  })

  it('ignora letture troppo imprecise', () => {
    const inside = new Set<string>()
    const spots = [spot('esca', 10, 44.6)]
    expect(updateDanger(inside, { lon: 10, lat: 44.6, acc: 900 }, spots).entered).toEqual([])
    updateDanger(inside, north(50), spots)
    // Una lettura dalle celle a 2 km non fa uscire dal raggio.
    expect(updateDanger(inside, { ...north(2000), acc: 900 }, spots).near).toHaveLength(1)
  })

  it('considera solo gli spot pericolo, dal più vicino', () => {
    const inside = new Set<string>()
    const spots = [spot('lontano', 10, 44.6 + 250 / 111195), spot('vicino', 10, 44.6 + 40 / 111195), spot('fungaia', 10, 44.6, 'interesse'), spot('tabella', 10, 44.6, 'riservato')]
    const r = updateDanger(inside, north(0), spots)
    expect(r.entered.map((h) => h.spot.id)).toEqual(['vicino', 'lontano'])
    expect(r.near.map((h) => h.spot.id)).toEqual(['vicino', 'lontano'])
  })

  it('dimentica gli spot cancellati', () => {
    const inside = new Set<string>()
    updateDanger(inside, north(0), [spot('esca', 10, 44.6)])
    expect(updateDanger(inside, north(0), []).near).toEqual([])
    expect(inside.size).toBe(0)
  })
})
