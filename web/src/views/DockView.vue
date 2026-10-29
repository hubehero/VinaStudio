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

onMounted(() => {
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
      <!-- Results first: after a run completes this is the card the user came
           for.  It renders nothing while no result exists, so the form still
           occupies the top of the sidebar before the first run. -->
      <DockingResults />
      <div v-if="docking.status === 'failed'" class="docking-failure">
        <div class="docking-failure__title">{{ t('docking.status.failed') }}</div>
        <p>{{ docking.error || t('docking.errorStartFailed') }}</p>
        <HelpLink topic="dockingFailed" />
      </div>
      <DockingForm />
      <DockingLog />
      <DockingInteractions v-model="interactions" />
      <DockingWorkbench />
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
</style>
