import { layers as protomapsLayers, namedFlavor } from '@protomaps/basemaps'
import type { ExpressionSpecification, LayerSpecification, StyleSpecification } from 'maplibre-gl'
import { model } from '../field/model'
import type { BasemapId } from '../settings/settings'
import { isFiutoBasemap, sourceUrl, type FileInfo } from './mapFiles'

export const FONT = ['Noto Sans Regular']

/** URL assoluto degli asset in public/, anche quando l'app sta in una sottocartella. */
const assets = () => (typeof location !== 'undefined' ? location.origin : '') + import.meta.env.BASE_URL

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

export interface OfflineFiles {
  basemap: FileInfo | null
  rilievo: FileInfo | null
}

const RILIEVO_LAYER = (): LayerSpecification => ({
  id: 'rilievo',
  type: 'raster',
  source: 'rilievo',
  paint: { 'raster-opacity': 0.55, 'raster-fade-duration': 0 },
})

/** Stile per la basemap regionale della pipeline: layer contours, trails, roads, water, places. */
export function fiutoBaseLayers(source: string): LayerSpecification[] {
  const label = { 'text-color': '#4a3b30', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5 }
  return [
    { id: 'base-water', type: 'line', source, 'source-layer': 'water', paint: { 'line-color': '#4a90c2', 'line-width': ['interpolate', ['linear'], ['zoom'], 10, 0.6, 16, 2] } },
    {
      id: 'base-contours-minor',
      type: 'line',
      source,
      'source-layer': 'contours',
      minzoom: 13,
      filter: ['!', ['to-boolean', ['get', 'major']]],
      paint: { 'line-color': '#a8825c', 'line-opacity': 0.45, 'line-width': 0.5 },
    },
    {
      id: 'base-contours-major',
      type: 'line',
      source,
      'source-layer': 'contours',
      filter: ['to-boolean', ['get', 'major']],
      paint: { 'line-color': '#8f6a45', 'line-opacity': 0.7, 'line-width': ['interpolate', ['linear'], ['zoom'], 10, 0.5, 15, 1.2] },
    },
    {
      id: 'base-roads',
      type: 'line',
      source,
      'source-layer': 'roads',
      paint: { 'line-color': '#6e6258', 'line-width': ['interpolate', ['linear'], ['zoom'], 10, 0.5, 16, 2.5] },
    },
    {
      id: 'base-trails',
      type: 'line',
      source,
      'source-layer': 'trails',
      paint: { 'line-color': '#c0392b', 'line-width': ['interpolate', ['linear'], ['zoom'], 11, 1, 16, 2.2], 'line-dasharray': [2, 1.5] },
    },
    {
      id: 'base-contours-label',
      type: 'symbol',
      source,
      'source-layer': 'contours',
      minzoom: 14,
      filter: ['to-boolean', ['get', 'major']],
      layout: { 'symbol-placement': 'line', 'text-field': ['concat', ['to-string', ['get', 'ele']], ' m'], 'text-font': FONT, 'text-size': 10 },
      paint: { 'text-color': '#8f6a45', 'text-halo-color': '#ffffff', 'text-halo-width': 1 },
    },
    {
      id: 'base-trails-label',
      type: 'symbol',
      source,
      'source-layer': 'trails',
      minzoom: 14,
      layout: { 'symbol-placement': 'line', 'text-field': ['coalesce', ['get', 'ref'], ['get', 'name'], ''], 'text-font': FONT, 'text-size': 11 },
      paint: { 'text-color': '#c0392b', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5 },
    },
    {
      id: 'base-water-label',
      type: 'symbol',
      source,
      'source-layer': 'water',
      minzoom: 13,
      layout: { 'symbol-placement': 'line', 'text-field': ['coalesce', ['get', 'name'], ''], 'text-font': FONT, 'text-size': 11 },
      paint: { 'text-color': '#2f6fa0', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5 },
    },
    {
      id: 'base-places',
      type: 'symbol',
      source,
      'source-layer': 'places',
      layout: { 'text-field': ['coalesce', ['get', 'name'], ''], 'text-font': FONT, 'text-size': ['interpolate', ['linear'], ['zoom'], 11, 10, 15, 13] },
      paint: label,
    },
  ]
}

/**
 * Stile di base. Le sovrapposizioni (score, spot, tracce) si aggiungono dopo.
 * "offline" usa i file nel telefono: basemap vettoriale (regionale fiuto o Protomaps) e/o rilievo.
 * Senza nessuno dei due ripiega su OpenTopoMap.
 */
export function baseStyle(basemap: BasemapId, files: OfflineFiles): StyleSpecification {
  const common = {
    version: 8 as const,
    glyphs: `${assets()}basemap/fonts/{fontstack}/{range}.pbf`,
  }
  if (basemap === 'offline' && (files.basemap || files.rilievo)) {
    const sources: StyleSpecification['sources'] = {}
    const layers: LayerSpecification[] = [{ id: 'bg', type: 'background', paint: { 'background-color': '#f3efe6' } }]
    const fiuto = isFiutoBasemap(files.basemap)
    if (files.basemap && !fiuto) {
      sources.protomaps = {
        type: 'vector',
        url: sourceUrl('basemap'),
        attribution: '© <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>, <a href="https://protomaps.com">Protomaps</a>',
      }
      layers.push(...protomapsLayers('protomaps', namedFlavor('light'), { lang: 'it' }))
    }
    if (files.rilievo) {
      sources.rilievo = { type: 'raster', url: sourceUrl('rilievo'), tileSize: 256 }
      // Sopra lo sfondo di Protomaps ma sotto strade ed etichette: subito dopo i layer "fill" di base.
      const firstLine = layers.findIndex((l) => l.type === 'line' || l.type === 'symbol')
      layers.splice(firstLine === -1 ? layers.length : firstLine, 0, RILIEVO_LAYER())
    }
    if (fiuto) {
      sources.base = { type: 'vector', url: sourceUrl('basemap') }
      layers.push(...fiutoBaseLayers('base'))
    }
    return { ...common, sprite: `${assets()}basemap/sprites/light`, sources, layers }
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
        // Da lontano serve vedere le zone, da vicino il terreno sotto.
        'fill-opacity': ['interpolate', ['linear'], ['zoom'], 9, 0.6, 13, 0.45, 16, 0.25],
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
