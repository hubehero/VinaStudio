<script setup lang="ts">
import { Aim, Document, MagicStick, Refresh, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import StatusPill from '@/components/StatusPill.vue'
import MoleculeSelect from '@/components/common/MoleculeSelect.vue'
import { useBoxStore } from '@/stores/box'
import { useMoleculeStore } from '@/stores/molecules'

/**
 * The search box panel.
 *
 * Every derived number — voxels, grid points, whether `write_maps` would accept
 * the box — comes from the backend, because those are Vina's rules and there
 * must be exactly one definition of them.
 */
const box = useBoxStore()
const molecules = useMoleculeStore()
const { t } = useI18n()

const extend = ref(4.0)
const configText = ref('')
const applyBusy = ref(false)

/**
 * Axis descriptors with literal indices, so indexing the centre and size tuples
 * stays typed as `number` rather than `number | undefined`.
 */
const AXES = [
  { key: 'x', index: 0 },
  { key: 'y', index: 1 },
  { key: 'z', index: 2 },
] as const

/** Ligand-ish sources are the ones autobox-from-ligand can use. */
const ligandSource = computed(
  () => molecules.pipelineLigand?.path ?? molecules.pipelineReceptor?.path ?? null,
)
const residueSource = computed(() => molecules.pipelineReceptor?.path ?? null)

onMounted(() => {
  if (!box.metrics) {
    void box.measure()
  }
})

async function autoboxFromLigand(): Promise<void> {
  const path = ligandSource.value
  if (!path) {
    return
  }
  if (await box.autoboxFromLigand(path, extend.value)) {
    ElMessage.success(t('box.autoboxDone', { n: box.autoboxPoints ?? 0 }))
  }
}

async function autoboxFromReceptor(): Promise<void> {
  const path = residueSource.value
  if (!path) {
    return
  }
  // No residue selection yet, so this boxes the whole receptor; the residue
  // picker arrives with the pocket-selection work in a later phase.
  if (await box.autoboxFromResidues(path, [], extend.value)) {
    ElMessage.success(t('box.autoboxDone', { n: box.autoboxPoints ?? 0 }))
  }
}

async function exportConfig(): Promise<void> {
  try {
    configText.value = await box.exportConfig()
    ElMessage.success(t('box.configExported'))
  } catch {
    ElMessage.error(t('box.configExportError'))
  }
}

async function importConfig(): Promise<void> {
  if (!configText.value.trim()) {
    return
  }
  applyBusy.value = true
  try {
    if (await box.importConfig(configText.value)) {
      ElMessage.success(t('box.configImported'))
    }
  } finally {
    applyBusy.value = false
  }
}

function setCenterAxis(axis: 0 | 1 | 2, value: number | undefined): void {
  if (value === undefined || Number.isNaN(value)) {
    return
  }
  box.setCenterAxis(axis, value)
}

function setSizeAxis(axis: 0 | 1 | 2, value: number | undefined): void {
  if (value === undefined || Number.isNaN(value)) {
    return
  }
  box.setSizeAxis(axis, value)
}
</script>

<template>
  <div class="vs-card">
    <div class="vs-card__header">
      <div>
        <div class="vs-card__title">{{ t('box.title') }}</div>
        <div class="vs-card__subtitle">{{ t('box.subtitle') }}</div>
      </div>
      <StatusPill
        v-if="box.metrics"
        :state="box.canWriteMaps ? 'ok' : 'warn'"
        :label="`${box.gridCells.toLocaleString()} ${t('box.voxels')}`"
        :detail="`${box.metrics.volume.toFixed(0)} Å³`"
      />
    </div>

    <div class="vs-card__body">
      <el-alert
        v-if="box.error"
        class="notice"
        type="error"
        :closable="false"
        show-icon
        :title="box.error"
      />

      <!-- Which molecules the box is drawn against; also the autobox sources. -->
      <div class="inputs">
        <div class="inputs__row">
          <span class="inputs__label">{{ t('molecules.typeReceptor') }}</span>
          <MoleculeSelect kind="receptor" />
        </div>
        <div class="inputs__row">
          <span class="inputs__label">{{ t('molecules.typeLigand') }}</span>
          <MoleculeSelect kind="ligand" />
        </div>
      </div>

      <div class="grid">
        <div class="grid__label">{{ t('box.center') }}</div>
        <div class="grid__fields">
          <el-input-number
            v-for="axis in AXES"
            :key="`c-${axis.key}`"
            :model-value="box.center[axis.index]"
            size="small"
            :step="0.5"
            :precision="3"
            :controls="false"
            :data-test="`box-center-${axis.key}`"
            @update:model-value="(value: number | undefined) => setCenterAxis(axis.index, value)"
          />
        </div>
        <div class="grid__label">{{ t('box.size') }}</div>
        <div class="grid__fields">
          <el-input-number
            v-for="axis in AXES"
            :key="`s-${axis.key}`"
            :model-value="box.size[axis.index]"
            size="small"
            :step="1"
            :min="1"
            :precision="3"
            :controls="false"
            :data-test="`box-size-${axis.key}`"
            @update:model-value="(value: number | undefined) => setSizeAxis(axis.index, value)"
          />
        </div>
        <div class="grid__label">{{ t('box.spacing') }}</div>
        <div class="grid__fields grid__fields--single">
          <el-input-number
            v-model="box.spacing"
            size="small"
            :step="0.025"
            :min="0.05"
            :precision="4"
            :controls="false"
            data-test="box-spacing"
          />
          <span class="vs-faint unit">Å</span>
        </div>
      </div>

      <div class="derived">
        <div class="derived__row">
          <span class="vs-muted">{{ t('box.voxelsPerAxis') }}</span>
          <span class="vs-mono">{{ box.voxels.join(' × ') }}</span>
        </div>
        <div class="derived__row">
          <span class="vs-muted">{{ t('box.gridPoints') }}</span>
          <span class="vs-mono">{{ box.metrics?.gridPoints.join(' × ') ?? '—' }}</span>
        </div>
        <div class="derived__row">
          <span class="vs-muted">{{ t('box.writable') }}</span>
          <StatusPill
            :state="box.canWriteMaps ? 'ok' : 'warn'"
            :label="box.canWriteMaps ? t('box.writableYes') : t('box.writableNo')"
          />
        </div>
      </div>

      <el-alert
        v-for="warning in box.warnings"
        :key="warning"
        class="notice"
        type="warning"
        :closable="false"
        show-icon
        :title="warning"
      />

      <el-divider />

      <div class="autobox">
        <div class="autobox__head">
          <span>{{ t('box.autobox') }}</span>
          <div class="autobox__extend">
            <span class="vs-faint">{{ t('box.extend') }}</span>
            <el-input-number
              v-model="extend"
              size="small"
              :step="1"
              :min="0"
              :precision="1"
              :controls="false"
              data-test="box-extend"
            />
          </div>
        </div>
        <p class="vs-faint autobox__note">{{ t('box.extendNote') }}</p>
        <div class="autobox__actions">
          <el-button
            size="small"
            :icon="MagicStick"
            :disabled="!ligandSource"
            :loading="box.measuring"
            data-test="autobox-ligand"
            @click="autoboxFromLigand"
          >
            {{ t('box.fromLigand') }}
          </el-button>
          <el-button
            size="small"
            :icon="MagicStick"
            :disabled="!residueSource"
            :loading="box.measuring"
            data-test="autobox-receptor"
            @click="autoboxFromReceptor"
          >
            {{ t('box.fromReceptor') }}
          </el-button>
        </div>
        <div v-if="box.autoboxSource" class="vs-faint autobox__source">
          <el-icon><WarningFilled /></el-icon>
          {{ t('box.autoboxSource', { points: box.autoboxPoints ?? 0 }) }}
        </div>
      </div>

      <el-divider />

      <div class="config">
        <div class="config__head">
          <span>{{ t('box.config') }}</span>
          <div>
            <el-button size="small" text :icon="Document" @click="exportConfig">
              {{ t('box.export') }}
            </el-button>
            <el-button
              size="small"
              text
              :icon="Refresh"
              :loading="applyBusy"
              @click="importConfig"
            >
              {{ t('box.import') }}
            </el-button>
          </div>
        </div>
        <el-input
          v-model="configText"
          type="textarea"
          :rows="5"
          spellcheck="false"
          :placeholder="t('box.configPlaceholder')"
          class="config__area"
        />
      </div>

      <el-button class="reset" size="small" :icon="Aim" @click="box.reset">
        {{ t('box.reset') }}
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.notice {
  margin-top: 12px;
}

.inputs {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
  margin-bottom: 14px;
}

.inputs__row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.inputs__label {
  flex: none;
  width: 48px;
  font-size: 12px;
  color: var(--vs-text-muted);
}

.grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.grid__label {
  font-size: 12px;
  color: var(--vs-text-muted);
}

.grid__fields {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.grid__fields--single {
  grid-template-columns: 1fr auto;
  align-items: center;
}

.unit {
  font-size: 12px;
}

:deep(.grid__fields .el-input__inner) {
  font-family: var(--vs-font-mono);
  font-size: 12px;
  text-align: center;
}

.derived {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.derived__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 12.5px;
}

.autobox__head,
.config__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--vs-text-muted);
}

.autobox__extend {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 400;
}

.autobox__extend :deep(.el-input) {
  width: 74px;
}

.autobox__note {
  margin: 6px 0 10px;
  font-size: 11.5px;
  line-height: 1.6;
}

.autobox__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.autobox__source {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 8px;
  font-size: 11.5px;
}

.config__area {
  margin-top: 8px;
}

.config__area :deep(.el-textarea__inner) {
  font-family: var(--vs-font-mono);
  font-size: 11.5px;
}

.reset {
  margin-top: 14px;
}

:deep(.el-divider) {
  margin: 16px 0;
}
</style>
