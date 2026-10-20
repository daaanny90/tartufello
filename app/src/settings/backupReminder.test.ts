import { describe, expect, it } from 'vitest'
import { backupOverdue } from './backupReminder'

describe('promemoria backup', () => {
  const now = new Date('2026-11-20T10:00:00Z')
  it('niente dati, niente promemoria', () => {
    expect(backupOverdue('', false, now)).toBe(false)
  })
  it('dati e mai un backup', () => {
    expect(backupOverdue('', true, now)).toBe(true)
  })
  it('backup recente o vecchio', () => {
    expect(backupOverdue('2026-11-15T10:00:00Z', true, now)).toBe(false)
    expect(backupOverdue('2026-10-30T10:00:00Z', true, now)).toBe(true)
  })
})
