<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { danger } from '../diary/danger'
import { HAZARD_LABELS } from '../diary/db'
import { formatDistance } from '../lib/geo'

const first = computed(() => danger.near[0])
const what = computed(() => {
  const s = first.value?.spot
  if (!s) return ''
  const label = s.hazard ? HAZARD_LABELS[s.hazard] : ''
  return label && label !== s.name && !s.name.startsWith(label) ? `${s.name} (${label.toLowerCase()})` : s.name
})
const coords = computed(() => (first.value?.spot.geom.type === 'Point' ? (first.value.spot.geom.coordinates as [number, number]) : null))
</script>

<template>
  <div v-if="first && !danger.dismissed" class="alert" role="alert" data-testid="danger-alert">
    <div class="text">
      <strong>Pericolo a {{ formatDistance(first.d) }}</strong>: {{ what }}, segnato il {{ new Date(first.spot.createdAt).toLocaleDateString('it-IT') }}.
      <template v-if="danger.near.length > 1"> E altri {{ danger.near.length - 1 }} qui intorno.</template>
      Tieni il cane vicino.
    </div>
    <div class="actions">
      <RouterLink v-if="coords" :to="{ path: '/mappa', query: { spot: first.spot.id, lon: coords[0], lat: coords[1], z: 16 } }">Mappa</RouterLink>
      <RouterLink to="/emergenza">Emergenza</RouterLink>
      <button class="close" aria-label="Chiudi avviso" @click="danger.dismissed = true">✕</button>
    </div>
  </div>
</template>

<style scoped>
.alert {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background: #e65100;
  color: #ffffff;
  font-size: 0.9rem;
}

.text {
  flex: 1;
}

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.actions a {
  color: #ffffff;
  font-weight: 700;
}

.close {
  min-height: 36px;
  padding: 4px 8px;
  background: transparent;
  border-color: rgb(255 255 255 / 0.6);
  color: #ffffff;
}
</style>
