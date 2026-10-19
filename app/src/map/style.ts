import { layers as protomapsLayers, namedFlavor } from '@protomaps/basemaps'
import type { ExpressionSpecification, LayerSpecification, StyleSpecification } from 'maplibre-gl'
import { model } from '../field/model'
import type { BasemapId } from '../settings/settings'
import { sourceUrl } from './mapFiles'

export const FONT = ['Noto Sans Regular']

const origin = () => (typeof location !== 'undefined' ? location.origin : '')

const RASTER: Record<Exclude<BasemapId, 'offline'>, { tiles: string[]; maxzoom: number; attribution: string }> = {
  opentopomap: {
    tiles: ['a', 'b', 'c'].map((s) => `https://${s}.tile.opentopomap.org/{z}/{x}/{y}.png`),
    maxzoom: 17,
    attribution:
      'Dati © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>, SRTM | Stile © <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)',
  },
  osm: {
    tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
    maxzoom: 19,
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  },
}

/** Stile di base. Le sovrapposizioni (score, spot, tracce) si aggiungono dopo. */
export function baseStyle(basemap: BasemapId, offlineReady: boolean): StyleSpecification {
  const common = {
    version: 8 as const,
    glyphs: `${origin()}/basemap/fonts/{fontstack}/{range}.pbf`,
  }
  if (basemap === 'offline' && offlineReady) {
    return {
      ...common,
      sprite: `${origin()}/basemap/sprites/light`,
      sources: {
        protomaps: {
          type: 'vector',
          url: sourceUrl('basemap'),
          attribution: '© <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>, <a href="https://protomaps.com">Protomaps</a>',
        },
      },
      layers: protomapsLayers('protomaps', namedFlavor('light'), { lang: 'it' }),
    }
  }
  const r = RASTER[basemap === 'offline' ? 'opentopomap' : basemap]
  return {
    ...common,
    sources: { base: { type: 'raster', tiles: r.tiles, tileSize: 256, maxzoom: r.maxzoom, attribution: r.attribution } },
    layers: [
      { id: 'bg', type: 'background', paint: { 'background-color': '#ece6da' } },
      { id: 'base', type: 'raster', source: 'base' },
    ],
  }
}

const cls = (id: string) => model.classes.find((c) => c.id === id)!.color

/** Colore per classe VTH sullo score remoto 0..1 riportato a 36. */
export const scoreColor: ExpressionSpecification = [
  'step',
  ['*', ['get', 'score'], model.maxTotal],
  cls('nulla'),
  model.classes.find((c) => c.id === 'bassa')!.min36,
  cls('bassa'),
  model.classes.find((c) => c.id === 'media')!.min36,
  cls('media'),
  model.classes.find((c) => c.id === 'alta')!.min36,
  cls('alta'),
]

const POINT_COLORS = ['#d73027', '#fc8d59', '#a6d96a', '#1a9850']

export function paramColor(param: string, max: number): ExpressionSpecification {
  // Con massimo 1 (ospiti da remoto) 1 punto vale "pieno".
  const stops = max === 1 ? [0, POINT_COLORS[0], 1, POINT_COLORS[3]] : [0, POINT_COLORS[0], 1, POINT_COLORS[1], 2, POINT_COLORS[2], 3, POINT_COLORS[3]]
  return ['match', ['get', param], ...stops, 'rgba(0,0,0,0)'] as unknown as ExpressionSpecification
}

export type ScoreView = { kind: 'score' } | { kind: 'param'; param: string; max: number } | { kind: 'off' }

export function scoreLayers(view: ScoreView): LayerSpecification[] {
  const layer = model.tiles.layer
  const visibility = view.kind === 'off' ? 'none' : 'visible'
  const filter: ExpressionSpecification = view.kind === 'param' ? ['has', view.param] : ['has', 'score']
  return [
    {
      id: 'vth-nodata',
      type: 'fill',
      source: 'vth',
      'source-layer': layer,
      filter: view.kind === 'param' ? ['!', ['has', view.param]] : ['!', ['has', 'score']],
      layout: { visibility },
      paint: { 'fill-color': '#7a7a7a', 'fill-opacity': 0.25 },
    },
    {
      id: 'vth-fill',
      type: 'fill',
      source: 'vth',
      'source-layer': layer,
      filter,
      layout: { visibility },
      paint: {
        'fill-color': view.kind === 'param' ? paramColor(view.param, view.max) : scoreColor,
        'fill-opacity': ['interpolate', ['linear'], ['zoom'], 9, 0.6, 15, 0.4],
      },
    },
    {
      id: 'vth-line',
      type: 'line',
      source: 'vth',
      'source-layer': layer,
      minzoom: 14,
      layout: { visibility },
      paint: { 'line-color': '#3b2f2a', 'line-opacity': 0.25, 'line-width': 0.5 },
    },
  ]
}
