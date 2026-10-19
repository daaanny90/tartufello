import { describe, expect, it } from 'vitest'
import { calendar, dayStatus, inRange, isOpen, nextChange, suspensionOn, targetStatus } from './calendar'

const sp = (id: string) => calendar.species.find((s) => s.id === id)!
const d = (y: number, m: number, day: number) => new Date(y, m - 1, day)

describe('inRange', () => {
  it('gestisce intervalli normali e a cavallo di capodanno', () => {
    expect(inRange('06-01', '06-01', '08-15')).toBe(true)
    expect(inRange('08-16', '06-01', '08-15')).toBe(false)
    expect(inRange('12-31', '10-01', '01-31')).toBe(true)
    expect(inRange('01-31', '10-01', '01-31')).toBe(true)
    expect(inRange('02-01', '10-01', '01-31')).toBe(false)
  })
})

describe('calendario ER 2026-2030', () => {
  it('sospende tutto a maggio e dal 16 agosto al 30 settembre', () => {
    expect(suspensionOn(d(2027, 5, 1))).not.toBeNull()
    expect(suspensionOn(d(2027, 5, 31))).not.toBeNull()
    expect(suspensionOn(d(2027, 8, 16))).not.toBeNull()
    expect(suspensionOn(d(2027, 9, 30))).not.toBeNull()
    expect(suspensionOn(d(2027, 10, 1))).toBeNull()
    expect(suspensionOn(d(2027, 8, 15))).toBeNull()
  })

  it('scorzone estivo: collina fino al 15 agosto, pianura fino al 31 luglio', () => {
    expect(isOpen(sp('aestivum'), d(2027, 8, 15), 'collina')).toBe(true)
    expect(isOpen(sp('aestivum'), d(2027, 8, 15), 'pianura')).toBe(false)
    expect(isOpen(sp('aestivum'), d(2027, 7, 31), 'pianura')).toBe(true)
    expect(isOpen(sp('aestivum'), d(2027, 5, 31), 'collina')).toBe(false)
  })

  it('uncinatum aperto da ottobre a gennaio in tutte le zone', () => {
    expect(isOpen(sp('uncinatum'), d(2026, 10, 19), 'collina')).toBe(true)
    expect(isOpen(sp('uncinatum'), d(2027, 1, 31), 'pianura')).toBe(true)
    expect(isOpen(sp('uncinatum'), d(2027, 2, 1), 'collina')).toBe(false)
  })

  it('calcola il prossimo cambio di stato', () => {
    expect(nextChange(sp('aestivum'), d(2027, 2, 10), 'collina')).toEqual(d(2027, 6, 1))
    expect(nextChange(sp('aestivum'), d(2027, 6, 10), 'collina')).toEqual(d(2027, 8, 16))
    expect(nextChange(sp('uncinatum'), d(2026, 10, 19), 'collina')).toEqual(d(2027, 2, 1))
  })

  it('stato del nero target', () => {
    const autumn = targetStatus(d(2026, 10, 19), 'collina')
    expect(autumn.open).toBe(true)
    expect(autumn.forms.map((s) => s.id)).toEqual(['uncinatum'])
    expect(autumn.until).toEqual(d(2027, 2, 1))

    const spring = targetStatus(d(2027, 3, 1), 'collina')
    expect(spring.open).toBe(false)
    expect(spring.from).toEqual(d(2027, 6, 1))
    expect(spring.forms.map((s) => s.id)).toEqual(['aestivum'])

    const september = targetStatus(d(2027, 9, 10), 'collina')
    expect(september.open).toBe(false)
    expect(september.from).toEqual(d(2027, 10, 1))
  })

  it('segnala le date fuori dal periodo di validità del calendario', () => {
    expect(dayStatus(d(2030, 12, 31), 'collina').inValidity).toBe(true)
    expect(dayStatus(d(2031, 1, 1), 'collina').inValidity).toBe(false)
  })

  it('nessuna specie risulta aperta durante una sospensione', () => {
    for (const day of [d(2027, 5, 15), d(2027, 9, 1)]) {
      expect(dayStatus(day, 'collina').species.every((s) => !s.open)).toBe(true)
    }
  })
})
