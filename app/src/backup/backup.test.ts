import 'fake-indexeddb/auto'
import { describe, expect, it } from 'vitest'
import { FiutoDb } from '../diary/db'
import { exportEncrypted, importEncrypted } from './backup'
import { decrypt, encrypt, WrongPassphraseError } from './crypto'

const PASS = 'cane-lagotto-2027'

describe('cifratura', () => {
  it('andata e ritorno', async () => {
    const env = await encrypt('ciao Fragno', PASS, 1000)
    expect(env.payload).not.toContain('Fragno')
    expect(await decrypt(env, PASS)).toBe('ciao Fragno')
  })

  it('passphrase sbagliata', async () => {
    const env = await encrypt('segreto', PASS, 1000)
    await expect(decrypt(env, 'sbagliata-davvero')).rejects.toBeInstanceOf(WrongPassphraseError)
  })

  it('rifiuta passphrase corte', async () => {
    await expect(encrypt('x', 'corta')).rejects.toThrow()
  })
})

describe('backup del diario', () => {
  it('esporta e reimporta tutto, foto comprese', async () => {
    const src = new FiutoDb('src-' + crypto.randomUUID())
    await src.outings.add({ id: 'o1', date: '2027-06-12T06:00:00Z', dog: 'Lagotta', track: [{ lon: 10.1, lat: 44.6, t: 1 }], spotsVisited: [] })
    await src.finds.add({
      id: 'f1',
      outingId: 'o1',
      date: '2027-06-12T07:00:00Z',
      position: [10.1, 44.6],
      species: 'aestivum',
      grams: 42,
      photo: new Blob([new Uint8Array([1, 2, 3, 250])], { type: 'image/jpeg' }),
    })
    await src.settings.put({ key: 'zone', value: 'collina' })

    const file = await exportEncrypted(PASS, src)
    const text = await file.text()
    expect(text).not.toContain('Lagotta')
    expect(text).not.toContain('44.6')

    const dst = new FiutoDb('dst-' + crypto.randomUUID())
    await dst.spots.add({ id: 'vecchio', name: 'da cancellare', kind: 'interesse', geom: { type: 'Point', coordinates: [0, 0] }, createdAt: '' })
    const res = await importEncrypted(file, PASS, 'replace', dst)
    expect(res.counts.finds).toBe(1)
    expect(await dst.spots.count()).toBe(0)
    const find = await dst.finds.get('f1')
    expect(find?.grams).toBe(42)
    expect(find?.photo).toBeInstanceOf(Blob)
    expect(new Uint8Array(await find!.photo!.arrayBuffer())).toEqual(new Uint8Array([1, 2, 3, 250]))
    expect((await dst.outings.get('o1'))?.track).toHaveLength(1)
  })

  it('merge non cancella quello che c’è', async () => {
    const src = new FiutoDb('src-' + crypto.randomUUID())
    await src.spots.add({ id: 's1', name: 'Fragno alto', kind: 'interesse', geom: { type: 'Point', coordinates: [10, 44.6] }, createdAt: '' })
    const file = await exportEncrypted(PASS, src)
    const dst = new FiutoDb('dst-' + crypto.randomUUID())
    await dst.spots.add({ id: 's0', name: 'già qui', kind: 'riservato', geom: { type: 'Point', coordinates: [10, 44.5] }, createdAt: '' })
    await importEncrypted(file, PASS, 'merge', dst)
    expect(await dst.spots.count()).toBe(2)
  })
})
