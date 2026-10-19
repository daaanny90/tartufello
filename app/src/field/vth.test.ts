import { describe, expect, it } from 'vitest'
import { param } from './model'
import { assess, classFor, hostsPoints, matchRule, orchidsPoints, remoteClass } from './vth'

const rules = (id: Parameters<typeof param>[0]) => param(id).rules!

describe('soglie numeriche VTH', () => {
  it('pH', () => {
    expect(matchRule(7.51, rules('ph'))).toBe(3)
    expect(matchRule(7.2, rules('ph'))).toBe(3)
    expect(matchRule(7.15, rules('ph'))).toBe(2)
    expect(matchRule(6.8, rules('ph'))).toBe(2)
    expect(matchRule(6.75, rules('ph'))).toBe(1)
    expect(matchRule(5.7, rules('ph'))).toBe(1)
    expect(matchRule(5.69, rules('ph'))).toBe(0)
  })

  it('quota', () => {
    expect(matchRule(599, rules('elevation'))).toBe(3)
    expect(matchRule(600, rules('elevation'))).toBe(2)
    expect(matchRule(1000, rules('elevation'))).toBe(1)
    expect(matchRule(1600, rules('elevation'))).toBe(1)
    expect(matchRule(1601, rules('elevation'))).toBe(0)
  })

  it('CaCO3', () => {
    expect(matchRule(0, rules('caco3'))).toBe(0)
    expect(matchRule(0.5, rules('caco3'))).toBe(1)
    expect(matchRule(1, rules('caco3'))).toBe(2)
    expect(matchRule(5, rules('caco3'))).toBe(2)
    expect(matchRule(5.1, rules('caco3'))).toBe(3)
  })

  it('Ca scambiabile', () => {
    expect(matchRule(0, rules('ca_exch'))).toBe(0)
    expect(matchRule(10, rules('ca_exch'))).toBe(1)
    expect(matchRule(15, rules('ca_exch'))).toBe(2)
    expect(matchRule(30, rules('ca_exch'))).toBe(3)
    expect(matchRule(60, rules('ca_exch'))).toBe(3)
    expect(matchRule(61, rules('ca_exch'))).toBe(2)
  })
})

describe('ospiti, orchidee', () => {
  it('3 punti solo con più di 2 arboree (nocciolo escluso) e nocciolo', () => {
    expect(hostsPoints({ tree: ['fagus', 'ostrya', 'quercus_cerris'], lower: ['corylus'] })).toBe(3)
    expect(hostsPoints({ tree: ['fagus', 'ostrya', 'corylus'], lower: [] })).toBe(1)
    expect(hostsPoints({ tree: ['fagus', 'ostrya', 'quercus_cerris'], lower: [] })).toBe(1)
    expect(hostsPoints({ tree: ['fagus'], lower: ['corylus'] })).toBe(2)
    expect(hostsPoints({ tree: [], lower: ['corylus'] })).toBe(1)
    expect(hostsPoints({ tree: [], lower: [] })).toBe(0)
  })

  it('orchidee: 1 specie vale 2, più di una vale 3', () => {
    expect(orchidsPoints({ speciesCount: 0 })).toBe(0)
    expect(orchidsPoints({ speciesCount: 1 })).toBe(2)
    expect(orchidsPoints({ speciesCount: 3 })).toBe(3)
  })
})

describe('valutazione combinata', () => {
  it('scheda completa tutta da campo arriva a 36 quando tutto è al massimo (C/N escluso)', () => {
    const a = assess({
      bedrock: 'calcari',
      ph: 7.6,
      caExch: 40,
      caco3Pct: 12,
      texture: 'franca',
      elevation: 450,
      forestType: 'latifoglie_fresche',
      forestStructure: 'aperta',
      hosts: { tree: ['fagus', 'ostrya', 'quercus_pubescens'], lower: ['corylus'] },
      orchids: { genera: ['Cephalanthera', 'Epipactis'], speciesCount: 2 },
      insects: ['Leiodes'],
    })
    expect(a.pts).toBe(33)
    expect(a.max).toBe(33)
    expect(a.score36).toBe(36)
    expect(a.vthClass?.id).toBe('alta')
    expect(a.observed).toBe(11)
    expect(a.params.find((p) => p.id === 'cn')?.origin).toBe('escluso')
  })

  it('il campo vince sulla mappa e gli ospiti da mappa pesano al massimo 1', () => {
    const a = assess({ ph: 6.0 }, { ph: 3, elevation: 3, hosts: 1 })
    const ph = a.params.find((p) => p.id === 'ph')!
    expect(ph.origin).toBe('campo')
    expect(ph.points).toBe(1)
    const hosts = a.params.find((p) => p.id === 'hosts')!
    expect(hosts.origin).toBe('mappa')
    expect(hosts.max).toBe(1)
    expect(a.pts).toBe(1 + 3 + 1)
    expect(a.max).toBe(3 + 3 + 1)
  })

  it('senza dati non c’è punteggio', () => {
    const a = assess({})
    expect(a.score36).toBeNull()
    expect(a.vthClass).toBeNull()
  })

  it('effervescenza come stima dei carbonati', () => {
    const a = assess({ caco3Fizz: 'visibile' })
    expect(a.params.find((p) => p.id === 'caco3')?.points).toBe(2)
  })
})

describe('classi', () => {
  it('soglie su 36', () => {
    expect(classFor(31).id).toBe('alta')
    expect(classFor(30.9).id).toBe('media')
    expect(classFor(25).id).toBe('media')
    expect(classFor(19).id).toBe('bassa')
    expect(classFor(18.9).id).toBe('nulla')
    expect(remoteClass(1).id).toBe('alta')
    expect(remoteClass(0.5).id).toBe('nulla')
  })
})

describe('classe provvisoria', () => {
  it('con pochi parametri la classe è provvisoria', () => {
    const few = assess({ forestStructure: 'aperta', forestType: 'latifoglie_fresche', ph: 7.6 })
    expect(few.vthClass?.id).toBe('alta')
    expect(few.provisional).toBe(true)
  })

  it('con campo più mappa smette di esserlo', () => {
    const full = assess(
      { forestStructure: 'aperta', orchids: { genera: [], speciesCount: 0 }, insects: [] },
      { bedrock: 3, ph: 3, caco3: 2, texture: 3, elevation: 3, forest_type: 2, hosts: 1 },
    )
    expect(full.provisional).toBe(false)
    expect(full.estimated).toBe(7)
    expect(full.observed).toBe(3)
  })
})
