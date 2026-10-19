<script setup lang="ts">
import { computed } from 'vue'
import type { TrackPoint } from '../diary/db'

const props = defineProps<{ track: TrackPoint[]; finds: [number, number][]; spots?: [number, number][] }>()

const W = 320
const H = 200
const PAD = 12

/** Proiezione equirettangolare locale: per pochi km va benissimo. */
const view = computed(() => {
  const pts: [number, number][] = [...props.track.map((p) => [p.lon, p.lat] as [number, number]), ...props.finds, ...(props.spots ?? [])]
  if (!pts.length) return null
  const lons = pts.map((p) => p[0])
  const lats = pts.map((p) => p[1])
  const minLon = Math.min(...lons)
  const maxLon = Math.max(...lons)
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const k = Math.cos((((minLat + maxLat) / 2) * Math.PI) / 180)
  const spanX = Math.max((maxLon - minLon) * k, 1e-5)
  const spanY = Math.max(maxLat - minLat, 1e-5)
  const s = Math.min((W - 2 * PAD) / spanX, (H - 2 * PAD) / spanY)
  const ox = (W - spanX * s) / 2
  const oy = (H - spanY * s) / 2
  const xy = (p: [number, number]) => [ox + (p[0] - minLon) * k * s, H - (oy + (p[1] - minLat) * s)] as const
  return {
    path: props.track.map((p, i) => `${i ? 'L' : 'M'}${xy([p.lon, p.lat]).join(',')}`).join(''),
    finds: props.finds.map(xy),
    spots: (props.spots ?? []).map(xy),
    start: props.track.length ? xy([props.track[0].lon, props.track[0].lat]) : null,
  }
})
</script>

<template>
  <svg v-if="view" :viewBox="`0 0 ${W} ${H}`" class="track" role="img" aria-label="Traccia dell'uscita">
    <path :d="view.path" fill="none" stroke="#7b3fa0" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" />
    <circle v-if="view.start" :cx="view.start[0]" :cy="view.start[1]" r="5" fill="#2e7d32" />
    <circle v-for="(s, i) in view.spots" :key="'s' + i" :cx="s[0]" :cy="s[1]" r="5" fill="#2f6fb3" stroke="#fff" stroke-width="1.5" />
    <circle v-for="(f, i) in view.finds" :key="'f' + i" :cx="f[0]" :cy="f[1]" r="6" fill="#3b2f2a" stroke="#f6f1e7" stroke-width="2" />
  </svg>
  <p v-else class="empty small">Nessun punto di traccia.</p>
</template>

<style scoped>
.track {
  width: 100%;
  height: auto;
  background: var(--surface-2);
  border-radius: 10px;
}
</style>
