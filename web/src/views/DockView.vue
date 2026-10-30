<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import DockingForm from '@/components/docking/DockingForm.vue'
import DockingInteractions from '@/components/docking/DockingInteractions.vue'
import DockingLog from '@/components/docking/DockingLog.vue'
import DockingResults from '@/components/docking/DockingResults.vue'
import DockingWorkbench from '@/components/docking/DockingWorkbench.vue'
import HelpLink from '@/components/HelpLink.vue'
import ViewportCanvas from '@/components/viewer/ViewportCanvas.vue'
import { useBoxStore } from '@/stores/box'
import { useDockingStore } from '@/stores/docking'
import { useDockingFormStore } from '@/stores/docking-form'
import { useMoleculeStore } from '@/stores/molecules'
import type { InteractionData } from '@/types/api'

const { t } = useI18n()
const docking = useDockingStore()
const dockingForm = useDockingFormStore()
const molecules = useMoleculeStore()
const box = useBoxStore()

/** Held here because the viewport draws these as annotations. */
const interactions = ref<InteractionData[]>([])

/**
 * Mirror every beat of the local ref into the store for the sequence view
 * (TASK-12): immediate on mount the ref is empty, so a remount re-states the
 * ref's cleared start rather than resurrecting a previous visit's rows.
 */
watch(
  interactions,
  (rows) => {
    docking.setInteractionSnapshot(rows, molecules.pipelineReceptor?.path ?? null)
  },
  { immediate: true },
)

/**
 * Pose and input ligand share the ligand slot, so the stage shows one or the
 * other: the input complex while the run is still ahead, the docked pose once
 * a result exists.
 */
const ligandUrl = computed(() => (docking.currentPoseSdf ? null : molecules.ligandSdfUrl))

type DockTab = 'results' | 'setup' | 'analysis'
const activeTab = ref<DockTab>(docking.hasResult || docking.isRunning ? 'results' : 'setup')

const pipelineSignature = computed(() => `${molecules.pipelineReceptor?.id ?? ''}|${molecules.pipelineLigand?.id ?? ''}`)

function jobMatchesPipeline(): boolean {
  const params = docking.jobResult?.params
  if (!params) return true
  const receptor = params.receptor_path ?? params.receptorPath
  const ligand = params.ligand_path ?? params.ligandPath
  return (
    (receptor === undefined || receptor === null || receptor === molecules.receptorPdbqtPath)
    && (ligand === undefined || ligand === null || ligand === molecules.ligandPdbqtPath)
  )
}

watch(pipelineSignature, (current, previous) => {
  if (current === previous || docking.isRunning) return
  // The old job's poses belong to the previous molecules. Clear them so the
  // viewport and result table cannot show a result that no longer matches.
  docking.reset()
  interactions.value = []
  activeTab.value = 'setup'
})


watch(
  () => [docking.isRunning, docking.hasResult] as const,
  ([running, hasResult]) => {
    if (running || hasResult) activeTab.value = 'results'
  },
  { immediate: true },
)

const statusLabel = computed(() =>
  docking.status === 'idle' ? t('docking.ready') : t(`docking.status.${docking.status}`),
)
const elapsedLabel = computed(() => {
  if (docking.elapsedMs === null) return null
  if (docking.elapsedMs < 1000) return `${docking.elapsedMs} ms`
  return `${(docking.elapsedMs / 1000).toFixed(1)} s`
})

onMounted(() => {
  if (docking.hasResult && !jobMatchesPipeline()) {
    docking.reset()
    activeTab.value = 'setup'
  }
  void docking.loadDefaults().then(() => {
    if (docking.defaults) dockingForm.applyDefaults(docking.defaults)
  })
})
</script>

<template>
  <div class="docking-view">
    <section class="docking-view__stage">
      <ViewportCanvas
        :receptor-url="molecules.receptorPdbUrl"
        :ligand-url="ligandUrl"
        :pose-sdf-content="docking.currentPoseSdf"
        :overlay-sdf-contents="docking.overlayPoseSdfs"
        :interactions="interactions"
        :box="box.geometry"
        :style="box.style"
        :orthographic="box.orthographic"
      />
    </section>

    <aside class="docking-view__side">
      <div class="dock-inspector">
        <header class="dock-inspector__head">
          <div class="dock-inspector__status">
            <span class="dock-status-dot" :class="`is-${docking.status}`" />
            <span>{{ statusLabel }}</span>
            <span v-if="docking.hasResult && docking.bestAffinity !== null" class="dock-status-meta">
              {{ docking.bestAffinity.toFixed(2) }} kcal/mol
            </span>
            <span v-if="elapsedLabel" class="dock-status-meta">{{ elapsedLabel }}</span>
          </div>
          <div class="dock-inspector__tabs" role="tablist" :aria-label="t('docking.title')">
            <button
              v-for="tab in (['setup', 'analysis', 'results'] as const)"
              :key="tab"
              type="button"
              role="tab"
              class="dock-tab"
              :class="{ 'is-active': activeTab === tab }"
              :aria-selected="activeTab === tab"
              @click="activeTab = tab"
            >
              {{ t(`docking.tabs.${tab}`) }}
              <span v-if="tab === 'results' && docking.poses.length" class="dock-tab__count">
                {{ docking.poses.length }}
              </span>
            </button>
          </div>
        </header>
        <div class="dock-inspector__body">
          <div v-if="docking.status === 'failed'" class="docking-failure">
            <div class="docking-failure__title">{{ t('docking.status.failed') }}</div>
            <p>{{ docking.error || t('docking.errorStartFailed') }}</p>
            <HelpLink topic="dockingFailed" />
          </div>
          <template v-if="activeTab === 'results'">
            <DockingResults />
            <DockingLog />
          </template>
          <DockingForm v-else-if="activeTab === 'setup'" />
          <template v-else>
            <DockingInteractions v-model="interactions" />
            <DockingWorkbench />
          </template>
        </div>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.docking-view {
  display: grid;
  /* The stage keeps the majority of the width; the operating panel scales with
     the window instead of a fixed 380px, which left its five cards cramped on
     wide screens. */
  grid-template-columns: minmax(0, 1fr) clamp(380px, 30vw, 520px);
  gap: 16px;
  padding: 16px 18px;
  height: 100%;
  min-height: 0;
}

.docking-view__stage {
  min-width: 0;
  min-height: 0;
}

.docking-failure {
  padding: 10px 12px;
  border: 1px solid var(--vs-danger);
  border-radius: var(--vs-radius);
  background: color-mix(in srgb, var(--vs-danger) 10%, transparent);
  color: var(--vs-text);
  font-size: 12px;
}
.docking-failure__title { font-weight: 600; margin-bottom: 4px; color: var(--vs-danger); }
.docking-failure p { margin: 0 0 6px; overflow-wrap: anywhere; }
.docking-view__side {
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

@media (max-width: 1180px) {
  .docking-view {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) auto;
  }
}

/* Dock inspector: one working column with tabs, not five stacked cards. */
.docking-view {
  grid-template-columns: minmax(0, 1fr) clamp(390px, 29vw, 470px);
  gap: 14px;
  padding: 14px 16px;
}
.docking-view__stage { min-width: 0; min-height: 0; }
.docking-view__side {
  overflow: hidden;
  min-height: 0;
}
.dock-inspector {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius);
  background: var(--vs-bg-surface);
}
.dock-inspector__head {
  flex: 0 0 auto;
  padding: 12px 14px 0;
  border-bottom: 1px solid var(--vs-border);
}
.dock-inspector__status {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  color: var(--vs-text-muted);
  font-size: 11.5px;
}
.dock-status-dot {
  width: 7px;
  height: 7px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: var(--vs-text-faint);
}
.dock-status-dot.is-running, .dock-status-dot.is-queued { background: var(--vs-warning); }
.dock-status-dot.is-completed { background: var(--vs-success); }
.dock-status-dot.is-failed { background: var(--vs-danger); }
.dock-status-meta { color: var(--vs-text-faint); }
.dock-status-meta::before { content: '·'; padding-right: 7px; color: var(--vs-border-strong); }
.dock-inspector__tabs {
  display: flex;
  gap: 2px;
  margin-top: 10px;
}
.dock-tab {
  position: relative;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--vs-text-faint);
  padding: 7px 10px 8px;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.dock-tab:hover { color: var(--vs-text); }
.dock-tab.is-active { border-bottom-color: var(--vs-accent); color: var(--vs-accent); }
.dock-tab__count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  margin-left: 4px;
  border-radius: 999px;
  background: var(--vs-bg-sunken);
  color: var(--vs-text-faint);
  font-size: 10px;
}
.dock-tab.is-active .dock-tab__count { background: var(--vs-accent-soft); color: var(--vs-accent); }
.dock-inspector__body {
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
}
.dock-inspector__body > .vs-card { border: 0; border-radius: 0; background: transparent; }
.dock-inspector__body > .vs-card + .vs-card { border-top: 1px solid var(--vs-border); padding-top: 10px; }
@media (max-width: 1180px) {
  .docking-view { grid-template-columns: minmax(0, 1fr); grid-template-rows: minmax(0, 1fr) minmax(280px, 44vh); }
  .docking-view__side { min-height: 0; }
}
@media (max-width: 620px) {
  .docking-view { padding: 10px; gap: 10px; }
  .dock-inspector__body { padding: 8px; }
}
</style>
