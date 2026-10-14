import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'

import AboutView from '@/views/AboutView.vue'
import BatchDockingView from '@/views/BatchDockingView.vue'
import BoxView from '@/views/BoxView.vue'
import DockView from '@/views/DockView.vue'
import EnvironmentView from '@/views/EnvironmentView.vue'
import HelpView from '@/views/HelpView.vue'
import MoleculeManagerView from '@/views/MoleculeManagerView.vue'
import ReportView from '@/views/ReportView.vue'
import ResultsSearchView from '@/views/ResultsSearchView.vue'
import ScreeningView from '@/views/ScreeningView.vue'
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
  // Dedicated report & analysis page; the docking view keeps its contextual
  // summary card, this route deep-links straight to the analysis.
  { path: '/report', name: 'report', component: ReportView },
  { path: '/batch', name: 'batch', component: BatchDockingView },
  { path: '/screening', name: 'screening', component: ScreeningView },
  { path: '/results', name: 'results', component: ResultsSearchView },
  { path: '/environment', name: 'environment', component: EnvironmentView },
  { path: '/help', name: 'help', component: HelpView },
  { path: '/about', name: 'about', component: AboutView },
  { path: '/:pathMatch(.*)*', redirect: '/workbench' },
]

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
})
