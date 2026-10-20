import { createRouter, createWebHistory } from 'vue-router'
import TodayView from './views/TodayView.vue'

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'oggi', component: TodayView },
    { path: '/mappa', name: 'mappa', component: () => import('./views/MapView.vue') },
    { path: '/campo', name: 'campo', component: () => import('./views/FieldView.vue') },
    { path: '/diario', name: 'diario', component: () => import('./views/DiaryView.vue') },
    { path: '/diario/uscita/:id', name: 'uscita', component: () => import('./views/OutingView.vue'), props: true },
    { path: '/diario/spot/:id', name: 'spot', component: () => import('./views/SpotView.vue'), props: true },
    { path: '/regole', name: 'regole', component: () => import('./views/RulesView.vue') },
    { path: '/impostazioni', name: 'impostazioni', component: () => import('./views/SettingsView.vue') },
  ],
})
