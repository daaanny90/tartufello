<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { model } from '../field/model'
import { calendar, formatMmdd, seasonLabel } from '../rules/calendar'
</script>

<template>
  <div class="page">
    <RouterLink to="/impostazioni" class="small">← Altro</RouterLink>
    <h1 style="margin-top: 8px">Regole</h1>

    <div class="banner small" :class="calendar.verified ? 'ok' : 'warn'">
      {{ calendar.verificationNote }} Fonte: <a :href="calendar.source" target="_blank" rel="noopener">calendario ufficiale</a>.
    </div>

    <section class="card">
      <h2>{{ calendar.title }}</h2>
      <p class="small muted">{{ calendar.legalBasis }}</p>
      <table>
        <thead>
          <tr><th>Specie</th><th>Periodo</th></tr>
        </thead>
        <tbody>
          <tr v-for="s in calendar.species" :key="s.id">
            <td>
              <strong>{{ s.common }}</strong>
              <div class="small muted"><i>{{ s.latin }}</i></div>
            </td>
            <td class="small">{{ seasonLabel(s) }}</td>
          </tr>
        </tbody>
      </table>
      <h3 style="margin-top: 14px">Sospensione totale</h3>
      <ul>
        <li v-for="s in calendar.suspensions" :key="s.from">{{ formatMmdd(s.from) }} - {{ formatMmdd(s.to) }}</li>
      </ul>
      <p class="small muted">{{ calendar.zonesNote }}</p>
    </section>

    <section class="card">
      <h2>Come si cerca</h2>
      <p><strong>{{ calendar.collectionRules.night.text }}</strong> L'orario di oggi è nella pagina Oggi.</p>
      <ul>
        <li v-for="n in calendar.collectionRules.notes" :key="n">{{ n }}</li>
        <li>Al massimo {{ calendar.collectionRules.dailyLimitGrams / 1000 }} kg al giorno. {{ calendar.collectionRules.dailyLimitNote }}</li>
      </ul>
      <p class="small muted">{{ calendar.collectionRules.ref }}</p>
    </section>

    <section class="card">
      <h2>Aree di tutela della fauna</h2>
      <p>In {{ calendar.faunaAreas.what }}:</p>
      <ul>
        <li v-for="c in calendar.faunaAreas.closed" :key="c.from">
          vietato dal {{ formatMmdd(c.from) }} al {{ formatMmdd(c.to) }} in {{ c.zones?.join(', ') }};
        </li>
        <li v-for="n in calendar.faunaAreas.notes" :key="n">{{ n }}</li>
      </ul>
      <p class="small muted">{{ calendar.faunaAreas.ref }}. {{ calendar.faunaAreas.layerNote }}</p>
    </section>

    <section class="card">
      <h2>Cosa serve</h2>
      <div v-for="r in calendar.requirements" :key="r.id" style="margin-bottom: 10px">
        <strong>{{ r.title }}</strong>
        <div>{{ r.text }}</div>
        <div class="small muted">{{ r.ref }}</div>
      </div>
      <p class="small muted">
        <a :href="calendar.lawSource" target="_blank" rel="noopener">L.R. 24/1991</a>: {{ calendar.lawNote }}
      </p>
    </section>

    <section class="card">
      <h2>Il modello</h2>
      <p>{{ model.title }}.</p>
      <p class="small">
        {{ model.source.citation }},
        <a :href="`https://doi.org/${model.source.doi}`" target="_blank" rel="noopener">doi:{{ model.source.doi }}</a> ({{ model.source.license }}).
      </p>
      <p class="small">
        12 parametri da 0 a 3 punti, massimo 36. Classi:
        <span v-for="c in model.classes" :key="c.id" class="row" style="display: inline-flex; gap: 4px; margin-right: 8px">
          <span class="swatch" :style="{ background: c.color }" />{{ c.label }} da {{ c.min36 }}
        </span>
      </p>
      <p class="small muted">
        Lo score remoto usa solo i parametri leggibili da dati regionali, normalizzati sul massimo ottenibile. Sotto
        {{ model.remote.minParams }} parametri disponibili non viene calcolato. La mappa restringe le zone, l'ultimo metro lo fa il cane.
      </p>
    </section>
  </div>
</template>
