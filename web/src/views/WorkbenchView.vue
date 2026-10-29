<script setup lang="ts">
import { ElButton, ElMessage } from 'element-plus'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import GlossaryDialog from '@/components/common/GlossaryDialog.vue'
import ViewportCanvas from '@/components/viewer/ViewportCanvas.vue'
import { useExampleSetup } from '@/composables/useExampleSetup'
import { useBoxStore } from '@/stores/box'
import { useDockingStore } from '@/stores/docking'
import { useMoleculeStore } from '@/stores/molecules'

const { t } = useI18n()
const router = useRouter()
const molecules = useMoleculeStore()
const box = useBoxStore()
const docking = useDockingStore()

const glossaryOpen = ref(false)
const { available: exampleAvailable, running: exampleRunning, setupExample } = useExampleSetup()

/** The example card retires once the setup chain is done — the steps take over. */
const showExample = computed(
  () => exampleAvailable.value && !(molecules.hasReceptor && molecules.hasLigand && box.metrics),
)

async function runExample(): Promise<void> {
  const result = await setupExample()
  if (!result.ok) {
    ElMessage.error(
      result.reason === 'missing-samples'
        ? t('workbench.example.missing')
        : t('workbench.example.failed'),
    )
    return
  }
  ElMessage.success(t('workbench.example.done'))
  void router.push('/docking')
}

/**
 * Pose and input ligand share the ligand slot, so the stage shows one or the
 * other: the input complex while the run is still ahead, the docked pose once
 * a result exists.
 */
const ligandUrl = computed(() => (docking.currentPoseSdf ? null : molecules.ligandSdfUrl))

interface PipelineStep {
  key: string
  title: string
  description: string
  ready: boolean
  summary: string | null
  route: string
}

const steps = computed<PipelineStep[]>(() => [
  {
    key: 'receptor',
    title: t('workbench.steps.receptor'),
    description: t('workbench.steps.receptorDesc'),
    ready: molecules.hasReceptor,
    summary: molecules.pipelineReceptor
      ? molecules.receptorReport
        ? t('workbench.summaries.receptor', {
            name: molecules.pipelineReceptor.name,
            atoms: molecules.receptorReport.outputAtoms,
            residues: molecules.receptorReport.validResidues,
          })
        : molecules.pipelineReceptor.name
      : null,
    route: '/molecules',
  },
  {
    key: 'ligand',
    title: t('workbench.steps.ligand'),
    description: t('workbench.steps.ligandDesc'),
    ready: molecules.hasLigand,
    summary: molecules.pipelineLigand
      ? molecules.ligandReport
        ? t('workbench.summaries.ligand', {
            name: molecules.pipelineLigand.name,
            atoms: molecules.ligandReport.outputAtoms,
          })
        : molecules.pipelineLigand.name
      : null,
    route: '/molecules',
  },
  {
    key: 'box',
    title: t('workbench.steps.box'),
    description: t('workbench.steps.boxDesc'),
    ready: molecules.hasReceptor && box.touched && box.metrics !== null,
    summary: molecules.hasReceptor && box.touched && box.metrics
      ? t('workbench.summaries.box', {
          x: box.center[0].toFixed(1),
          y: box.center[1].toFixed(1),
          z: box.center[2].toFixed(1),
          size: box.size[0].toFixed(0),
        })
      : null,
    route: '/box',
  },
  {
    key: 'docking',
    title: t('workbench.steps.docking'),
    description: t('workbench.steps.dockingDesc'),
    ready: docking.isCompleted,
    summary: docking.bestAffinity !== null
      ? t('workbench.summaries.docking', {
          affinity: docking.bestAffinity.toFixed(2),
          poses: docking.poses.length,
        })
      : null,
    route: '/docking',
  },
  {
    key: 'results',
    title: t('workbench.steps.results'),
    description: t('workbench.steps.resultsDesc'),
    ready: docking.hasResult && docking.poses.length > 0,
    summary: docking.hasResult
      ? t('workbench.summaries.results', {
          best: docking.bestAffinity?.toFixed(2) ?? '—',
          count: docking.poses.length,
        })
      : null,
    route: '/docking',
  },
])

function goToStep(step: PipelineStep): void {
  void router.push(step.route)
}

/** The first step not done yet — the only one worth pointing at. */
const nextKey = computed(() => steps.value.find((step) => !step.ready)?.key ?? null)
</script>

<template>
  <div class="workbench">
    <section class="workbench__stage">
      <ViewportCanvas
        :receptor-url="molecules.receptorPdbUrl"
        :ligand-url="ligandUrl"
        :pose-sdf-content="docking.currentPoseSdf"
        :box="box.geometry"
        :style="box.style"
        :orthographic="box.orthographic"
      />
    </section>

    <aside class="workbench__side">
      <div v-if="showExample" class="vs-card">
        <div class="vs-card__header">
          <div>
            <div class="vs-card__title">{{ t('workbench.example.title') }}</div>
            <div class="vs-card__subtitle">{{ t('workbench.example.subtitle') }}</div>
          </div>
        </div>
        <div class="vs-card__body">
          <p class="example__desc">{{ t('workbench.example.desc') }}</p>
          <ElButton type="primary" size="small" :loading="exampleRunning" @click="runExample">
            {{ t('workbench.example.button') }}
          </ElButton>
        </div>
      </div>

      <div class="vs-card">
        <div class="vs-card__header">
          <div>
            <div class="vs-card__title">{{ t('workbench.pipeline.title') }}</div>
            <div class="vs-card__subtitle">{{ t('workbench.pipeline.subtitle') }}</div>
          </div>
          <ElButton text size="small" @click="glossaryOpen = true">
            {{ t('glossary.button') }}
          </ElButton>
        </div>
        <div class="vs-card__body">
          <ol class="steps">
            <li
              v-for="(step, index) in steps"
              :key="step.key"
              class="steps__item"
              :class="{
                'steps__item--ready': step.ready,
                'steps__item--next': step.key === nextKey,
              }"
              @click="goToStep(step)"
            >
              <span class="steps__index" :class="{ 'is-ready': step.ready }">
                <template v-if="step.ready">✓</template>
                <template v-else>{{ index + 1 }}</template>
              </span>
              <div class="steps__content">
                <div class="steps__title">
                  {{ step.title }}
                  <span
                    class="steps__tag"
                    :class="{ 'is-ready': step.ready, 'is-next': step.key === nextKey }"
                  >
                    {{
                      step.ready
                        ? t('workbench.stage.ready')
                        : step.key === nextKey
                          ? t('workbench.stage.next')
                          : t('workbench.stage.planned')
                    }}
                  </span>
                </div>
                <div class="steps__desc">{{ step.description }}</div>
                <div v-if="step.summary" class="steps__summary">
                  {{ step.summary }}
                </div>
              </div>
            </li>
          </ol>
        </div>
      </div>
    </aside>

    <GlossaryDialog v-model="glossaryOpen" />
  </div>
</template>

<style scoped>
.workbench {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 344px;
  gap: 16px;
  padding: 16px 18px;
  height: 100%;
  min-height: 0;
}

.workbench__stage {
  min-width: 0;
  min-height: 0;
}

.workbench__side {
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.example__desc {
  margin: 0 0 10px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--vs-text-muted);
}

.steps {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.steps__item {
  display: flex;
  gap: 11px;
  padding: 10px 8px;
  border-radius: var(--vs-radius);
  cursor: pointer;
  transition: background 0.15s;
}

.steps__item:hover {
  background: var(--vs-bg-sunken);
}

.steps__item--ready {
  opacity: 1;
}

/* The one step worth doing next: a quiet accent frame, not a second CTA. */
.steps__item--next {
  background: var(--vs-bg-sunken);
  box-shadow: inset 2px 0 0 var(--vs-accent);
}

.steps__index {
  flex: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: var(--vs-bg-sunken);
  border: 1px solid var(--vs-border);
  color: var(--vs-text-faint);
  font-size: 11.5px;
  font-weight: 600;
}

.steps__index.is-ready {
  background: var(--vs-accent-soft);
  border-color: transparent;
  color: var(--vs-accent);
}

.steps__content {
  min-width: 0;
}

.steps__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  font-weight: 600;
}

.steps__tag {
  padding: 0 7px;
  border-radius: 999px;
  background: var(--vs-bg-sunken);
  border: 1px solid var(--vs-border);
  color: var(--vs-text-faint);
  font-size: 10.5px;
  font-weight: 500;
  line-height: 1.7;
}

.steps__tag.is-ready {
  background: var(--vs-accent-soft);
  border-color: transparent;
  color: var(--vs-accent);
}

.steps__tag.is-next {
  background: var(--vs-accent-soft);
  border-color: transparent;
  color: var(--vs-accent);
  font-weight: 600;
}

.steps__desc {
  margin-top: 3px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--vs-text-muted);
}

.steps__summary {
  margin-top: 4px;
  font-size: 11.5px;
  color: var(--vs-accent);
  font-weight: 500;
}

@media (max-width: 1240px) {
  .workbench {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) auto;
  }
}
</style>
