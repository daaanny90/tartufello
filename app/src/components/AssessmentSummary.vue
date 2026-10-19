<script setup lang="ts">
import { model } from '../field/model'
import type { Assessment } from '../field/vth'

defineProps<{ a: Assessment; compact?: boolean }>()
</script>

<template>
  <div class="summary">
    <div class="row spread">
      <div class="row">
        <span v-if="a.vthClass && a.provisional" class="pill provisional" :style="{ borderColor: a.vthClass.color }">{{ a.vthClass.label }}?</span>
        <span v-else-if="a.vthClass" class="pill" :style="{ background: a.vthClass.color, color: '#1b1714' }">{{ a.vthClass.label }}</span>
        <span v-else class="pill neutral">Nessun dato</span>
        <strong v-if="a.score36 !== null">{{ a.score36.toFixed(1) }} / 36</strong>
      </div>
      <span class="small muted">{{ a.pts }}/{{ a.max }} punti</span>
    </div>
    <div class="small muted" style="margin-top: 4px">
      {{ a.observed }} osservati sul posto · {{ a.estimated }} stimati dalla mappa · {{ a.missing }} mancanti
    </div>
    <div v-if="a.vthClass && a.provisional" class="small provisional-note">
      Classe provvisoria: servono almeno {{ model.field.minParamsForClass }} parametri, ne hai {{ a.observed + a.estimated }}.
    </div>
    <table v-if="!compact" class="small" style="margin-top: 8px">
      <tbody>
        <tr v-for="p in a.params" :key="p.id">
          <td>{{ p.label }}</td>
          <td class="muted">{{ p.origin === 'escluso' ? 'escluso' : p.detail ?? '' }}</td>
          <td style="text-align: right; white-space: nowrap">
            <template v-if="p.points !== null">{{ p.points }}/{{ p.max }}</template>
            <span v-else class="muted">-</span>
          </td>
          <td style="width: 1%">
            <span class="pill" :class="p.origin === 'campo' ? 'ok' : p.origin === 'mappa' ? 'warn' : 'neutral'">{{ p.origin }}</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.provisional {
  border: 2px dashed;
  background: transparent;
  color: var(--ink);
}

.provisional-note {
  color: var(--warn);
  margin-top: 4px;
}
</style>
