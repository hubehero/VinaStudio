import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'

import AboutView from '@/views/AboutView.vue'
import BatchDockingView from '@/views/BatchDockingView.vue'
import BoxView from '@/views/BoxView.vue'
import DockView from '@/views/DockView.vue'
import EnvironmentView from '@/views/EnvironmentView.vue'
import MoleculeManagerView from '@/views/MoleculeManagerView.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'

/**
 * Hash history keeps deep links working no matter how the bundle is served
 * (bundled static files or the Vite dev server) without needing an SPA
 * fallback route on the backend.
 */
const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/workbench' },
  { path: '/workbench', name: 'workbench', component: WorkbenchView },
  { path: '/molecules', name: 'molecules', component: MoleculeManagerView },
  // The per-panel preparation flow lives in the molecule manager now.
  { path: '/prepare', redirect: '/molecules' },
  { path: '/box', name: 'box', component: BoxView },
  { path: '/docking', name: 'docking', component: DockView },
  { path: '/batch', name: 'batch', component: BatchDockingView },
  { path: '/environment', name: 'environment', component: EnvironmentView },
  { path: '/about', name: 'about', component: AboutView },
  { path: '/:pathMatch(.*)*', redirect: '/workbench' },
]

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
})
