<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  LigandRepresentation,
  ReceptorColourScheme,
  ReceptorRepresentation,
  SurfaceKind,
} from '@/composables/use3Dmol'
import { useBoxStore } from '@/stores/box'
import { useMoleculeStore } from '@/stores/molecules'
import { useSettingsStore } from '@/stores/settings'

/**
 * Appearance controls for the two molecules.
 *
 * Everything offered here is a 3Dmol built-in, and the labels say exactly what
 * it is. In particular there is no "hydrophobicity" or "electrostatic potential"
 * surface, because 3Dmol computes neither: claiming one would be the kind of
 * scientific overstatement this application must not make.
 *
 * Surface kind and opacity are owned by the settings store so this panel and
 * the settings dialog always agree; ``ViewportCanvas`` reads them directly
 * and merges them into the applied style.
 */
const box = useBoxStore()
const molecules = useMoleculeStore()
const settings = useSettingsStore()
const { t } = useI18n()

const RECEPTOR_REPRESENTATIONS: ReceptorRepresentation[] = [
  'cartoon',
  'trace',
  'stick',
  'line',
  'sphere',
]
const COLOUR_SCHEMES: ReceptorColourScheme[] = ['spectrum', 'chain', 'ss', 'element']
const LIGAND_REPRESENTATIONS: LigandRepresentation[] = ['stick', 'sphere', 'line']
const SURFACES: SurfaceKind[] = ['VDW', 'SAS', 'SES']

const hasReceptor = computed(() => molecules.hasReceptor)
const hasLigand = computed(() => molecules.hasLigand)

function setSurface(kind: SurfaceKind): void {
  // Clicking the active surface turns it off, so the control doubles as a toggle.
  settings.viewer.surfaceKind = settings.viewer.surfaceKind === kind ? null : kind
}
</script>

<template>
  <div class="vs-card">
    <div class="vs-card__header">
      <div>
        <div class="vs-card__title">{{ t('view.title') }}</div>
        <div class="vs-card__subtitle">{{ t('view.subtitle') }}</div>
      </div>
    </div>

    <div class="vs-card__body">
      <div class="field">
        <div class="field__label">
          {{ t('view.receptorStyle') }}
          <span v-if="!hasReceptor" class="vs-faint">· {{ t('view.noReceptor') }}</span>
        </div>
        <el-radio-group
          v-model="box.style.receptor"
          size="small"
          :disabled="!hasReceptor"
          data-test="receptor-style"
        >
          <el-radio-button
            v-for="kind in RECEPTOR_REPRESENTATIONS"
            :key="kind"
            :value="kind"
          >
            {{ t(`view.receptor.${kind}`) }}
          </el-radio-button>
        </el-radio-group>
      </div>

      <div class="field">
        <div class="field__label">{{ t('view.receptorColour') }}</div>
        <el-radio-group
          v-model="box.style.receptorColour"
          size="small"
          :disabled="!hasReceptor"
        >
          <el-radio-button v-for="scheme in COLOUR_SCHEMES" :key="scheme" :value="scheme">
            {{ t(`view.colour.${scheme}`) }}
          </el-radio-button>
        </el-radio-group>
      </div>

      <div class="field">
        <div class="field__label">
          {{ t('view.ligandStyle') }}
          <span v-if="!hasLigand" class="vs-faint">· {{ t('view.noLigand') }}</span>
        </div>
        <el-radio-group
          v-model="box.style.ligand"
          size="small"
          :disabled="!hasLigand"
          data-test="ligand-style"
        >
          <el-radio-button
            v-for="kind in LIGAND_REPRESENTATIONS"
            :key="kind"
            :value="kind"
          >
            {{ t(`view.ligand.${kind}`) }}
          </el-radio-button>
        </el-radio-group>
      </div>

      <div class="field">
        <div class="field__label">{{ t('view.surface') }}</div>
        <el-radio-group size="small" :disabled="!hasReceptor" data-test="surface">
          <el-radio-button
            v-for="kind in SURFACES"
            :key="kind"
            :value="kind"
            :class="{ 'is-active': settings.viewer.surfaceKind === kind }"
            @click="setSurface(kind)"
          >
            {{ kind }}
          </el-radio-button>
        </el-radio-group>
        <p class="vs-faint note">{{ t('view.surfaceNote') }}</p>
        <div v-if="settings.viewer.surfaceKind" class="opacity">
          <span class="vs-muted">{{ t('view.opacity') }}</span>
          <el-slider
            v-model="settings.viewer.surfaceOpacity"
            :min="0.15"
            :max="1"
            :step="0.05"
            size="small"
          />
        </div>
      </div>

      <el-divider />

      <div class="field field--row">
        <span class="vs-muted">{{ t('view.orthographic') }}</span>
        <el-switch v-model="box.orthographic" size="small" data-test="orthographic" />
      </div>
      <p class="vs-faint note">{{ t('view.orthographicNote') }}</p>
    </div>
  </div>
</template>

<style scoped>
.field + .field {
  margin-top: 16px;
}

.field__label {
  margin-bottom: 7px;
  font-size: 12.5px;
  color: var(--vs-text-muted);
}

.field--row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.note {
  margin: 7px 0 0;
  font-size: 11.5px;
  line-height: 1.6;
}

.opacity {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 6px;
  font-size: 12px;
}

.opacity :deep(.el-slider) {
  flex: 1;
}

:deep(.el-radio-group) {
  flex-wrap: wrap;
  gap: 4px;
}

:deep(.el-radio-button__inner) {
  font-size: 12px;
  padding: 5px 11px;
}

/* Surfaces toggle rather than behave as a radio group, so the active one is
   marked explicitly instead of relying on the group's own state. */
:deep(.el-radio-button.is-active .el-radio-button__inner) {
  background: var(--vs-accent);
  border-color: var(--vs-accent);
  color: #0d1526;
}

:deep(.el-divider) {
  margin: 16px 0;
}
</style>
