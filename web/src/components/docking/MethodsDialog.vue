<script setup lang="ts">
/**
 * "Methods" text dialog: a ready-to-paste Methods section built from the
 * parameters the active job actually ran with.
 *
 * The generator is a pure module (``utils/methods-paragraph.ts``); this file
 * only gathers the inputs from the stores and offers language + copy.
 */
import { ElButton, ElDialog, ElMessage } from 'element-plus'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { useDockingStore } from '@/stores/docking'
import { useMoleculeStore } from '@/stores/molecules'
import { useSystemStore } from '@/stores/system'
import { useUiStore } from '@/stores/ui'
import { buildMethodsText, type MethodsLang } from '@/utils/methods-paragraph'

const open = defineModel<boolean>({ required: true })

const { t } = useI18n()
const docking = useDockingStore()
const molecules = useMoleculeStore()
const system = useSystemStore()
const ui = useUiStore()

const lang = ref<MethodsLang>(ui.locale === 'en-US' ? 'en' : 'zh')

function baseName(path: string): string {
  const parts = path.split(/[\\/]/)
  return parts[parts.length - 1] || path
}

const params = computed(() => docking.jobResult?.params ?? null)

/** Prefer the name recorded in the run itself; fall back to the pipeline pick. */
const receptorName = computed(() => {
  const path = params.value?.['receptor_path']
  if (typeof path === 'string' && path.length > 0) return baseName(path)
  return molecules.pipelineReceptor?.name ?? null
})

const ligandName = computed(() => {
  const path = params.value?.['ligand_path']
  if (typeof path === 'string' && path.length > 0) return baseName(path)
  return molecules.pipelineLigand?.name ?? docking.activeJobLabel ?? null
})

const validationCounts = computed(() => {
  const result = docking.validation
  if (!result) return null
  const counts = { ok: 0, warning: 0, error: 0 }
  for (const pose of result.poses) {
    if (pose.worstSeverity === 'error') counts.error += 1
    else if (pose.worstSeverity === 'warning') counts.warning += 1
    else counts.ok += 1
  }
  return counts
})

const text = computed(() =>
  buildMethodsText(
    {
      params: params.value,
      receptorName: receptorName.value,
      ligandName: ligandName.value,
      versions: {
        app: system.info?.app.version ?? null,
        vina: system.info?.packages?.['vina'] ?? null,
        meeko: system.info?.packages?.['meeko'] ?? null,
        rdkit: system.info?.packages?.['rdkit'] ?? null,
      },
      nPoses: docking.poses.length,
      bestAffinity: docking.bestAffinity,
      elapsedMs: docking.elapsedMs,
      validation: validationCounts.value,
      rmsd: docking.rmsd
        ? { threshold: docking.rmsd.threshold, successRate: docking.rmsd.successRate }
        : null,
      clusters: docking.clusters
        ? { nClusters: docking.clusters.nClusters, cutoff: docking.clusters.cutoff }
        : null,
    },
    lang.value,
  ),
)

async function copy(withCaveat: boolean): Promise<void> {
  const payload = withCaveat ? `${text.value.body}\n\n${text.value.caveat}` : text.value.body
  try {
    await navigator.clipboard.writeText(payload)
    ElMessage.success(t('docking.methods.copied'))
  } catch {
    // Clipboard access can be refused; the text stays selectable as a fallback.
    ElMessage.warning(t('docking.methods.copyFailed'))
  }
}
</script>

<template>
  <ElDialog v-model="open" :title="t('docking.methods.title')" width="min(760px, 92vw)">
    <div class="methods">
      <div class="methods__bar">
        <div class="methods__switch" role="group">
          <button
            type="button"
            class="methods__switch-btn"
            :class="{ 'is-active': lang === 'zh' }"
            @click="lang = 'zh'"
          >
            中文
          </button>
          <button
            type="button"
            class="methods__switch-btn"
            :class="{ 'is-active': lang === 'en' }"
            @click="lang = 'en'"
          >
            English
          </button>
        </div>
        <div class="methods__actions">
          <ElButton size="small" @click="copy(false)">{{ t('docking.methods.copy') }}</ElButton>
          <ElButton size="small" type="primary" @click="copy(true)">
            {{ t('docking.methods.copyWithCaveat') }}
          </ElButton>
        </div>
      </div>

      <p class="methods__hint">{{ t('docking.methods.subtitle') }}</p>

      <pre class="methods__text">{{ text.body }}</pre>

      <p class="methods__caveat-label">{{ t('docking.methods.caveatLabel') }}</p>
      <pre class="methods__text methods__text--caveat">{{ text.caveat }}</pre>

      <p v-if="!params" class="methods__warn">{{ t('docking.methods.noParams') }}</p>
      <p class="methods__note">{{ t('docking.methods.note') }}</p>
    </div>
  </ElDialog>
</template>

<style scoped>
.methods {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.methods__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.methods__switch {
  display: inline-flex;
  padding: 2px;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius-sm);
  background: var(--vs-bg-sunken);
}

.methods__switch-btn {
  padding: 3px 12px;
  border: none;
  border-radius: calc(var(--vs-radius-sm) - 2px);
  background: none;
  font: inherit;
  font-size: 12px;
  color: var(--vs-text-muted);
  cursor: pointer;
}

.methods__switch-btn.is-active {
  background: var(--vs-accent-soft);
  color: var(--vs-accent);
  font-weight: 600;
}

.methods__actions {
  display: flex;
  gap: 8px;
}

.methods__hint,
.methods__note {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--vs-text-faint);
}

.methods__text {
  margin: 0;
  padding: 12px 14px;
  max-height: 320px;
  overflow: auto;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius);
  background: var(--vs-bg-sunken);
  font-family: var(--vs-font-mono);
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--vs-text);
}

.methods__text--caveat {
  max-height: 140px;
  color: var(--vs-text-muted);
}

.methods__caveat-label {
  margin: 0;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--vs-text-faint);
}

.methods__warn {
  margin: 0;
  font-size: 12px;
  color: var(--vs-warning);
}
</style>
