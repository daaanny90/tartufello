import { describe, expect, it } from 'vitest'
import { groupByArea, kindOf } from './published'

describe('mappe pubblicate', () => {
  it('raggruppa per zona e mette lo score per primo', () => {
    const areas = groupByArea([
      { file: 'vb-rilievo.pmtiles', title: 'r', kind: 'rilievo', area: 'Val Baganza', built: '', size: 3 },
      { file: 'vb.pmtiles', title: 'Val Baganza (bozza)', area: 'Val Baganza', built: '', size: 2 },
      { file: 'vb-base.pmtiles', title: 'b', kind: 'basemap', area: 'Val Baganza', built: '', size: 1 },
      { file: 'vp.pmtiles', title: 'Val Parma', built: '', size: 5 },
    ])
    expect(areas.map((a) => a.area)).toEqual(['Val Baganza', 'Val Parma'])
    expect(areas[0].maps.map(kindOf)).toEqual(['score', 'basemap', 'rilievo'])
    expect(areas[0].size).toBe(6)
  })
})
