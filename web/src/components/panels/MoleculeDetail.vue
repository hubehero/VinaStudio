<script setup lang="ts">
import { ArrowRight, Delete, InfoFilled, MagicStick, RefreshRight, View, WarningFilled } from '@element-plus/icons-vue'
import { ElAlert, ElButton, ElMessage } from 'element-plus'
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

import MoleculeOptions from '@/components/panels/MoleculeOptions.vue'
import ViewportCanvas from '@/components/viewer/ViewportCanvas.vue'
import { DEFAULT_VIEWER_STYLE } from '@/composables/use3Dmol'
import { isUsable, useMoleculeStore } from '@/stores/molecules'
import { getEffectiveType } from '@/types/molecule'

/** Receptors as cartoons coloured by residue, ligands as sticks. */
const MOLECULE_STYLE = DEFAULT_VIEWER_STYLE

const store = useMoleculeStore()
const { t } = useI18n()

const mol = computed(() => store.activeMolecule)

onMounted(() => {
  if (!store.filters) {
    void store.loadReferenceData()
  }
})

const type = computed(() => (mol.value ? getEffectiveType(mol.value) : 'unknown'))

const typeLabel = computed(() => {
  if (type.value === 'receptor') return t('molecules.typeReceptor')
  if (type.value === 'ligand') return t('molecules.typeLigand')
  return t('molecules.typeUnknown')
})

const statusClass = computed(() => {
  const s = mol.value?.status
  if (s === 'prepared') return 'is-ok'
  if (s === 'error') return 'is-error'
  if (s === 'inspecting' || s === 'preparing') return 'is-warn'
  return 'is-idle'
})

const isBusy = computed(
  () => mol.value?.status === 'inspecting' || mol.value?.status === 'preparing',
)
const hasPreview = computed(() => previewUrl.value !== null)
const previewUrl = computed(() => (mol.value ? store.getPreviewUrl(mol.value) : null))

/** Whether the preview is missing because the file has no 3D coordinates. */
const previewIsFlat = computed(() => {
  const preview = mol.value?.preview
  return Boolean(preview && 'has3dCoordinates' in preview && preview.has3dCoordinates === false)
})

const previewNote = computed(() =>
  previewIsFlat.value ? t('molecules.previewFlat') : t('molecules.previewMissing'),
)

/** The step the user is expected to take next, given where the file is now. */
/** A file that is already a docking input is used as it is. */
const preparable = computed(() => mol.value?.preview?.preparable !== false)

const nextStep = computed(() => {
  const status = mol.value?.status
  if (status === 'uploaded') return t('molecules.hintInspect')
  if (status === 'inspected') {
    return preparable.value ? t('molecules.hintPrepare') : t('molecules.hintAlreadyPdbqt')
  }
  if (status === 'prepared') return t('molecules.hintPrepared')
  return null
})

/** Preparation options and the flexible-residue picker, once the file is understood. */
const showOptions = computed(() => preparable.value && mol.value?.preview != null)

/** Whether this molecule can claim the docking role of its kind. */
const usable = computed(() => (mol.value ? isUsable(mol.value) : false))
const isCurrentPick = computed(() => {
  if (!mol.value) return false
  return type.value === 'receptor'
    ? store.pipelineReceptor?.id === mol.value.id
    : type.value === 'ligand'
      ? store.pipelineLigand?.id === mol.value.id
      : false
})

function handleUseAs(): void {
  if (!mol.value) return
  if (type.value === 'receptor') store.setPipelineReceptor(mol.value.id)
  else if (type.value === 'ligand') store.setPipelineLigand(mol.value.id)
}

/** How the file was identified, which the user can correct. */
const detectedBy = computed(() => {
  const molecule = mol.value
  if (!molecule) return null
  if (molecule.detectionSource === 'user') return t('molecules.detectedByUser')
  if (molecule.detectionReason === 'small molecule') return t('molecules.detectedBySmallMolecule')
  if (molecule.detectionReason === 'polymer residues') return t('molecules.detectedByResidues')
  if (molecule.detectionReason === 'extension') return t('molecules.detectedByExtension')
  return null
})

const facts = computed(() => {
  const preview = mol.value?.preview
  if (!preview) return []
  const rows: Array<{ label: string; value: string }> = []
  if ('atoms' in preview) rows.push({ label: t('molecules.atoms'), value: String(preview.atoms) })
  if ('residues' in preview) {
    rows.push({ label: t('molecules.residues'), value: String(preview.residues) })
  }
  if ('chains' in preview) rows.push({ label: t('molecules.chains'), value: String(preview.chains) })
  if ('hydrogens' in preview) {
    rows.push({ label: t('molecules.hydrogens'), value: String(preview.hydrogens) })
  }
  if ('rotatableBonds' in preview) {
    rows.push({ label: t('molecules.rotatable'), value: String(preview.rotatableBonds) })
  }
  if ('molecularFormula' in preview) {
    rows.push({ label: t('molecules.formula'), value: preview.molecularFormula ?? '—' })
  }
  if ('molecularWeight' in preview) {
    rows.push({
      label: t('molecules.weight'),
      value: preview.molecularWeight ? `${preview.molecularWeight.toFixed(1)} Da` : '—',
    })
  }
  if ('waters' in preview) {
    rows.push({ label: t('molecules.waters'), value: String(preview.waters.length) })
  }
  if ('hetero' in preview) {
    rows.push({ label: t('molecules.hetero'), value: String(preview.hetero.length) })
  }
  if ('records' in preview && preview.records > 1) {
    rows.push({ label: t('molecules.records'), value: String(preview.records) })
  }
  return rows
})

const notes = computed(() => mol.value?.preview?.notes ?? [])
const smiles = computed(() => {
  const preview = mol.value?.preview
  return preview && 'smiles' in preview ? preview.smiles : null
})

/** camelCase keys from the API, made readable without a translation table. */
function humanise(key: string): string {
  return key
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/^./, (c) => c.toUpperCase())
}

/** Report fields the interface has a name for; the rest fall back to the key. */
const REPORT_LABELS: Record<string, string> = {
  inputFormat: 'molecules.reportInputFormat',
  inputAtoms: 'molecules.reportAtoms',
  outputAtoms: 'molecules.reportOutputAtoms',
  inputResidues: 'molecules.reportInputResidues',
  validResidues: 'molecules.reportValidResidues',
  normalisedAtomOrder: 'molecules.reportNormalised',
  includeHydrogens: 'molecules.reportIncludeHydrogens',
  hydrogensAdded: 'molecules.reportHydrogensAdded',
  conformerGenerated: 'molecules.reportConformer',
  geometryOptimised: 'molecules.reportOptimised',
  outputPolarHydrogens: 'molecules.reportPolarHydrogens',
  nonpolarHydrogensRemoved: 'molecules.reportNonpolarRemoved',
  rotatableBonds: 'molecules.reportRotatable',
  totalCharge: 'molecules.reportCharge',
  deletedWaters: 'molecules.reportWaters',
  deletedHetero: 'molecules.reportHetero',
  ignoredResidues: 'molecules.reportIgnored',
  flexibleResidues: 'molecules.reportFlexible',
}

/** Booleans read as a tick rather than as `true`, which no user parses. */
function reportValue(value: unknown): string {
  if (typeof value === 'boolean') return value ? '✓' : '—'
  return String(value)
}

/**
 * Scalar entries of the preparation report.
 *
 * The report is a deep object of lists and maps; the lists are shown as chips and
 * the scalars as labelled rows. String lists count as a row (waters deleted and
 * friends say how much was taken out). It used to be dumped as JSON, which is
 * not something a user reads, and the labels were the raw camelCase keys, which
 * is not something a Chinese-reading user reads either.
 */
const reportRows = computed(() => {
  const report = mol.value?.report
  if (!report || typeof report !== 'object') return []
  return Object.entries(report as Record<string, unknown>)
    // `source` is the file the panel is already showing; the rest have their
    // own sections (SMILES, chips, the residue picker, warning alerts).
    .filter(([key]) => !['source', 'smiles', 'atomTypes', 'residueList', 'warnings'].includes(key))
    .filter(
      ([, value]) =>
        ['string', 'number', 'boolean'].includes(typeof value) ||
        (Array.isArray(value) && value.every((v) => typeof v === 'string')),
    )
    .map(([key, value]) => {
      const i18nKey = REPORT_LABELS[key]
      return {
        key,
        label: i18nKey ? t(i18nKey) : humanise(key),
        value: Array.isArray(value) ? String(value.length) : reportValue(value),
      }
    })
})

const reportWarnings = computed(() => {
  const report = mol.value?.report
  return report && 'warnings' in report ? report.warnings : []
})

const reportChips = computed(() => {
  const report = mol.value?.report
  if (!report || typeof report !== 'object') return null
  const atomTypes = (report as Record<string, unknown>).atomTypes
  if (!atomTypes || typeof atomTypes !== 'object') return null
  return Object.entries(atomTypes as Record<string, number>)
})

async function handleInspect(): Promise<void> {
  if (!mol.value) return
  await store.inspectMolecule(mol.value.id)
}

async function handlePrepare(): Promise<void> {
  if (!mol.value) return
  await store.prepareMolecule(mol.value.id)
}

async function handleAllowAndRetry(): Promise<void> {
  if (!mol.value) return
  await store.allowRejectedResiduesAndRetry(mol.value.id)
  if (mol.value.status === 'prepared') {
    ElMessage.success(t('molecules.prepareDone'))
  }
}

function handleAssignType(kind: 'receptor' | 'ligand'): void {
  if (mol.value) store.assignType(mol.value.id, kind)
}

function handleRemove(): void {
  if (mol.value) store.removeItem(mol.value.id)
}
</script>

<template>
  <div v-if="mol" class="detail">
    <header class="detail__head">
      <div class="detail__identity">
        <h2 class="detail__name" :title="mol.path">{{ mol.name }}</h2>
        <div class="detail__tags">
          <span class="tag" :class="`tag--${type}`">{{ typeLabel }}</span>
          <span class="tag tag--plain">{{ mol.name.split('.').pop()?.toUpperCase() }}</span>
          <span class="pill" :class="statusClass">
            <span class="pill__dot" />
            {{ t(`molecules.status.${mol.status}`) }}
          </span>
        </div>
      </div>

      <div class="detail__actions">
        <ElButton
          v-if="mol.status === 'uploaded' || (mol.status === 'error' && !mol.preview)"
          type="primary"
          size="small"
          :icon="RefreshRight"
          :loading="isBusy"
          @click="handleInspect"
        >
          {{ mol.status === 'error' ? t('molecules.retry') : t('molecules.inspect') }}
        </ElButton>

        <ElButton
          v-if="preparable && mol.preview && (mol.status === 'inspected' || mol.status === 'error')"
          type="primary"
          size="small"
          :icon="MagicStick"
          :loading="isBusy"
          @click="handlePrepare"
        >
          {{ t('molecules.prepare') }}
        </ElButton>

        <ElButton
          v-if="mol.status === 'prepared' && preparable"
          size="small"
          :icon="RefreshRight"
          :loading="isBusy"
          @click="handlePrepare"
        >
          {{ t('molecules.prepareAgain') }}
        </ElButton>

        <ElButton
          v-if="type !== 'unknown' && usable"
          size="small"
          :type="isCurrentPick ? 'success' : 'default'"
          :plain="!isCurrentPick"
          :disabled="isCurrentPick"
          @click="handleUseAs"
        >
          {{
            isCurrentPick
              ? t(type === 'receptor' ? 'molecules.currentReceptor' : 'molecules.currentLigand')
              : t(type === 'receptor' ? 'molecules.useAsReceptor' : 'molecules.useAsLigand')
          }}
        </ElButton>

        <ElButton size="small" type="danger" plain :icon="Delete" @click="handleRemove">
          {{ t('molecules.remove') }}
        </ElButton>
      </div>
    </header>

    <p v-if="nextStep" class="detail__next">
      <el-icon :size="12"><ArrowRight /></el-icon>
      <span>{{ nextStep }}</span>
    </p>

    <div v-if="type === 'unknown'" class="detail__assign">
      <span class="detail__assign-label">{{ t('molecules.assignPrompt') }}</span>
      <ElButton size="small" @click="handleAssignType('receptor')">
        {{ t('molecules.typeReceptor') }}
      </ElButton>
      <ElButton size="small" @click="handleAssignType('ligand')">
        {{ t('molecules.typeLigand') }}
      </ElButton>
    </div>

    <div class="detail__viewport">
      <ViewportCanvas
        v-if="hasPreview"
        :receptor-url="type === 'receptor' ? previewUrl : null"
        :ligand-url="type === 'ligand' ? previewUrl : null"
        :style="MOLECULE_STYLE"
      />
      <div v-else class="detail__placeholder">
        <el-icon :size="26" class="detail__placeholder-icon">
          <RefreshRight v-if="isBusy" class="detail__spin" /><View v-else />
        </el-icon>
        <span>{{ isBusy ? t('molecules.preparingPreview') : previewNote }}</span>
      </div>
    </div>

    <div v-if="mol.error" class="detail__alert">
      <ElAlert type="error" :closable="false" show-icon :title="mol.error.message">
        <template v-if="mol.error.residues.length" #default>
          <div class="detail__residues">
            <span class="detail__residues-label">{{ t('molecules.rejectedResidues') }}</span>
            <span class="vs-mono">{{ mol.error.residues.join(', ') }}</span>
          </div>
          <div class="detail__residues">
            <ElButton size="small" :icon="WarningFilled" @click="handleAllowAndRetry">
              {{ t('molecules.allowBadResidues') }}
            </ElButton>
          </div>
        </template>
      </ElAlert>
    </div>

    <div v-for="(note, i) in notes" :key="i" class="detail__alert">
      <ElAlert type="info" :closable="false" show-icon :title="note" />
    </div>

    <section v-if="facts.length > 0 || detectedBy" class="detail__section">
      <h3 class="detail__section-title">{{ t('molecules.properties') }}</h3>
      <dl class="facts">
        <div v-if="detectedBy" class="facts__row">
          <dt class="facts__label">{{ t('molecules.detectedBy') }}</dt>
          <dd class="facts__value">{{ detectedBy }}</dd>
        </div>
        <div v-for="row in facts" :key="row.label" class="facts__row">
          <dt class="facts__label">{{ row.label }}</dt>
          <dd class="facts__value vs-mono">{{ row.value }}</dd>
        </div>
      </dl>
    </section>

    <section v-if="smiles" class="detail__section">
      <h3 class="detail__section-title">{{ t('molecules.smiles') }}</h3>
      <p class="detail__smiles vs-mono" :title="smiles">{{ smiles }}</p>
    </section>

    <MoleculeOptions v-if="showOptions" :mol="mol" />

    <div v-for="(warning, i) in reportWarnings" :key="i" class="detail__alert">
      <ElAlert type="warning" :closable="false" show-icon :title="warning" />
    </div>

    <details v-if="mol.report" class="detail__report">
      <summary class="detail__report-summary">
        <span>{{ t('molecules.report') }}</span>
        <span class="detail__report-state">
          <span class="detail__report-open">{{ t('molecules.reportShow') }}</span>
          <span class="detail__report-close">{{ t('molecules.reportHide') }}</span>
        </span>
      </summary>

      <dl v-if="reportRows.length > 0" class="facts facts--tight">
        <div v-for="row in reportRows" :key="row.key" class="facts__row">
          <dt class="facts__label">{{ row.label }}</dt>
          <dd class="facts__value vs-mono">{{ row.value }}</dd>
        </div>
      </dl>

      <div v-if="reportChips" class="chips">
        <span v-for="[atomType, count] in reportChips" :key="atomType" class="chip">
          {{ atomType }} × {{ count }}
        </span>
      </div>
    </details>
  </div>

  <div v-else class="detail detail--empty">
    <div class="detail__empty">
      <el-icon :size="34" class="detail__empty-icon"><InfoFilled /></el-icon>
      <h2 class="detail__empty-title">{{ t('molecules.selectMolecule') }}</h2>
      <p class="detail__empty-hint">{{ t('molecules.selectHint') }}</p>
      <ol class="detail__steps">
        <li>{{ t('molecules.stepLoad') }}</li>
        <li>{{ t('molecules.stepInspect') }}</li>
        <li>{{ t('molecules.stepPrepare') }}</li>
      </ol>
    </div>
  </div>
</template>

<style scoped>
.detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  height: 100%;
  padding: 14px 16px;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius-lg);
  background: var(--vs-bg-surface);
  overflow-y: auto;
}

.detail--empty {
  align-items: center;
  justify-content: center;
}

.detail__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}

.detail__identity {
  min-width: 0;
}

.detail__name {
  margin: 0 0 5px;
  font-size: 15px;
  font-weight: 600;
  color: var(--vs-text);
  word-break: break-all;
}

.detail__tags {
  display: flex;
  align-items: center;
  gap: 6px;
}

.tag {
  padding: 1px 7px;
  border-radius: 999px;
  border: 1px solid var(--vs-border);
  background: var(--vs-bg-sunken);
  font-size: 10.5px;
  color: var(--vs-text-muted);
}

.tag--receptor {
  color: var(--vs-accent);
  border-color: color-mix(in srgb, var(--vs-accent) 40%, var(--vs-border));
}

.tag--ligand {
  color: var(--vs-warning);
  border-color: color-mix(in srgb, var(--vs-warning) 40%, var(--vs-border));
}

.tag--plain {
  font-family: var(--vs-font-mono);
  font-size: 10px;
}

.detail__actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.detail__next {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: 12px;
  color: var(--vs-text-muted);
}

.detail__assign {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 8px 10px;
  border-radius: var(--vs-radius-sm);
  border: 1px dashed var(--vs-border);
  background: var(--vs-bg-sunken);
}

.detail__assign-label {
  font-size: 12px;
  color: var(--vs-text-muted);
}

.detail__viewport {
  flex: 1;
  min-height: 320px;
  border-radius: var(--vs-radius);
  border: 1px solid var(--vs-border);
  overflow: hidden;
  background: var(--vs-bg-app);
}

.detail__placeholder {
  height: 100%;
  min-height: 320px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 20px;
  text-align: center;
  font-size: 12px;
  color: var(--vs-text-faint);
}

.detail__spin {
  animation: detail-spin 1.1s linear infinite;
}

@keyframes detail-spin {
  to { transform: rotate(360deg); }
}

.detail__alert {
  flex: none;
}

.detail__residues {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 4px;
  font-size: 11.5px;
}

.detail__residues-label {
  color: var(--vs-text-muted);
}

.detail__section {
  flex: none;
}

.detail__section-title {
  margin: 0 0 6px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--vs-text-faint);
}

.facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 2px 18px;
  margin: 0;
}

.facts--tight {
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  margin-top: 10px;
}

.facts__row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  padding: 3px 0;
  border-bottom: 1px solid color-mix(in srgb, var(--vs-border) 50%, transparent);
  font-size: 12px;
}

.facts__label {
  color: var(--vs-text-muted);
}

.facts__value {
  margin: 0;
  font-size: 11.5px;
  color: var(--vs-text);
}

.detail__smiles {
  margin: 0;
  padding: 7px 9px;
  border-radius: var(--vs-radius-sm);
  background: var(--vs-bg-sunken);
  font-size: 11px;
  line-height: 1.5;
  word-break: break-all;
  color: var(--vs-text-muted);
}

.detail__report {
  flex: none;
  border-top: 1px solid var(--vs-border);
  padding-top: 10px;
}

.detail__report-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--vs-text-muted);
}

.detail__report-summary:focus-visible {
  outline: 2px solid var(--vs-accent);
  outline-offset: 2px;
}

.detail__report-state {
  font-weight: 400;
  text-transform: none;
  letter-spacing: 0;
  color: var(--vs-text-faint);
}

.detail__report-open {
  display: inline;
}

.detail__report-close {
  display: none;
}

.detail__report[open] .detail__report-open {
  display: none;
}

.detail__report[open] .detail__report-close {
  display: inline;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 10px;
}

.chip {
  padding: 1px 8px;
  border-radius: 999px;
  border: 1px solid var(--vs-border);
  background: var(--vs-bg-sunken);
  font-family: var(--vs-font-mono);
  font-size: 10.5px;
  color: var(--vs-text-muted);
}

.detail__empty {
  max-width: 420px;
  text-align: center;
}

.detail__empty-icon {
  color: var(--vs-text-faint);
}

.detail__empty-title {
  margin: 10px 0 4px;
  font-size: 14px;
  font-weight: 600;
  color: var(--vs-text-muted);
}

.detail__empty-hint {
  margin: 0 0 14px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--vs-text-faint);
}

.detail__steps {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
  text-align: left;
}

.detail__steps li {
  position: relative;
  padding-left: 22px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--vs-text-muted);
  counter-increment: step;
}

.detail__steps li::before {
  content: counter(step);
  position: absolute;
  left: 0;
  top: 0;
  width: 16px;
  height: 16px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  border: 1px solid var(--vs-border);
  background: var(--vs-bg-sunken);
  font-size: 10px;
  color: var(--vs-text-faint);
}

.detail__steps {
  counter-reset: step;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 1px 9px 1px 7px;
  border-radius: 999px;
  border: 1px solid var(--vs-border);
  background: var(--vs-bg-sunken);
  font-size: 10.5px;
  color: var(--vs-text-muted);
}

.pill__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--vs-text-faint);
  flex: none;
}

.pill.is-ok .pill__dot {
  background: var(--vs-success);
}

.pill.is-error .pill__dot {
  background: var(--vs-danger);
}

.pill.is-warn .pill__dot {
  background: var(--vs-warning);
  animation: detail-pulse 1.6s ease-in-out infinite;
}

@keyframes detail-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>
