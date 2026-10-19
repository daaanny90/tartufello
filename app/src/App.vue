<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { tracking } from './diary/outings'

const route = useRoute()
const fullscreen = computed(() => route.name === 'mappa')

const tabs = [
  { to: '/', label: 'Oggi', icon: 'M12 3v2M12 19v2M5 12H3M21 12h-2M6.3 6.3 4.9 4.9M19.1 19.1l-1.4-1.4M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4 1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z' },
  { to: '/mappa', label: 'Mappa', icon: 'M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14' },
  { to: '/campo', label: 'Campo', icon: 'M9 5h10M9 12h10M9 19h10M4 5l1 1 2-2M4 12l1 1 2-2M4 19l1 1 2-2' },
  { to: '/diario', label: 'Diario', icon: 'M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3V4zM5 17a3 3 0 0 1 3-3h11' },
  { to: '/impostazioni', label: 'Altro', icon: 'M4 7h16M4 12h16M4 17h16' },
]
</script>

<template>
  <div class="shell" :class="{ fullscreen }">
    <RouterLink v-if="tracking.outingId" :to="`/diario/uscita/${tracking.outingId}`" class="recording">
      <span class="dot" /> Uscita in corso · {{ tracking.points }} punti traccia
    </RouterLink>
    <main class="content">
      <RouterView v-slot="{ Component }">
        <KeepAlive include="MapView">
          <component :is="Component" />
        </KeepAlive>
      </RouterView>
    </main>
    <nav class="tabs" aria-label="Sezioni">
      <RouterLink v-for="t in tabs" :key="t.to" :to="t.to" class="tab" :class="{ active: t.to === '/' ? route.path === '/' : route.path.startsWith(t.to) || (t.to === '/impostazioni' && route.path === '/regole') }">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path :d="t.icon" />
        </svg>
        <span>{{ t.label }}</span>
      </RouterLink>
    </nav>
  </div>
</template>

<style scoped>
.shell {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.content {
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

.fullscreen .content {
  overflow: hidden;
}

.recording {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  padding-top: calc(8px + env(safe-area-inset-top, 0px));
  background: var(--accent);
  color: var(--accent-ink);
  font-size: 0.9rem;
  font-weight: 600;
  text-decoration: none;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #ff5a4e;
  animation: pulse 1.6s infinite;
}

@keyframes pulse {
  50% {
    opacity: 0.3;
  }
}

.tabs {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  height: calc(var(--nav-h) + var(--safe-b));
  padding-bottom: var(--safe-b);
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  background: var(--surface);
  border-top: 1px solid var(--line);
  z-index: 20;
}

.tab {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  color: var(--muted);
  text-decoration: none;
  font-size: 0.72rem;
}

.tab.active {
  color: var(--accent);
  font-weight: 600;
}
</style>
