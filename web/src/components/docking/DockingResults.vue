<script setup lang="ts">
import { ArrowLeft, ArrowRight, Download, InfoFilled, Search } from '@element-plus/icons-vue'
import { ElButton, ElCheckbox, ElCheckboxGroup, ElDialog, ElIcon, ElMessage, ElOption, ElSelect, ElSlider, ElTooltip } from 'element-plus'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { saveTextFile } from '@/api/bridge'
import { api } from '@/api/http'
import type { Artifact, BundleMember, PoseFinding } from '@/types/api'
import { useDockingStore } from '@/stores/docking'
import { useBoxStore } from '@/stores/box'
import { useMoleculeStore } from '@/stores/molecules'

const { t, te, locale } = useI18n()
const docking = useDockingStore()
const box = useBoxStore()
const molecules = useMoleculeStore()

/** Prepared ligand SDF artifact path used as the geometric reference, if any. */
const referenceSdfPath = computed<string | null>(() => {
  const mol = molecules.pipelineLigand
  if (!mol) return null
  return mol.artifacts.find((a: Artifact) => a.kind === 'sdf')?.path ?? null
})

/** SDF-backed ligands offered as redocking-RMSD references. */
const referenceOptions = computed<{ label: string; value: string }[]>(() => {
  const seen = new Set<string>()
  const options: { label: string; value: string }[] = []
  const add = (label: string, path: string): void => {
    if (seen.has(path)) return
    seen.add(path)
    options.push({ label, value: path })
  }
  for (const mol of molecules.ligands) {
    // The backend accepts PDBQT references (converted through the same
    // poses_to_sdf path the poses use), so the selector filter is the only
    // gate that kept them out. Flexible-residue copies are not references.
    const sdf = mol.artifacts.find((a: Artifact) => a.kind === 'sdf')
    if (sdf) add(mol.name, sdf.path)
    const pdbqt = mol.artifacts.find(
      (a: Artifact) => a.kind === 'pdbqt' && !a.name.endsWith('_flex.pdbqt'),
    )
    if (pdbqt) add(`${mol.name} (PDBQT)`, pdbqt.path)
    if (mol.path.toLowerCase().endsWith('.pdbqt')) add(`${mol.name} (PDBQT)`, mol.path)
  }
  return options
})

/** Selected reference: explicit pick, then the pipeline ligand, then first option. */
const selectedReference = computed<string>({
  get: () =>
    docking.rmsdReferencePath ??
    referenceSdfPath.value ??
    referenceOptions.value[0]?.value ??
    '',
  set: (value: string) => {
    docking.rmsdReferencePath = value
  },
})

/** True when the chosen reference needs the conversion note (PDBQT input). */
const selectedReferenceIsPdbqt = computed(() =>
  selectedReference.value.toLowerCase().endsWith('.pdbqt'),
)

async function downloadCsv(): Promise<void> {
  if (!docking.activeJobId) return
  try {
    // Pass the reference so the export gains an rmsd_vs_ref column.
    const result = await api.exportCsv(
      docking.activeJobId,
      docking.rmsdReferencePath ?? undefined,
    )
    // False only means "desktop dialog cancelled or write failed" — the host
    // reports write errors itself, so there is nothing to toast here.
    await saveTextFile(result.csv, {
      filename: result.filename,
      mime: 'text/csv',
      saveTitle: t('docking.saveFile.title'),
    })
  } catch {
    ElMessage.error(t('docking.errorExportCsv'))
  }
}

async function exportSinglePose(poseIndex: number): Promise<void> {
  if (!docking.activeJobId) return
  try {
    const result = await api.exportPose(docking.activeJobId, poseIndex)
    const saveTitle = t('docking.saveFile.title')
    if (result.sdf) {
      await saveTextFile(result.sdf, {
        filename: `pose_${poseIndex}.sdf`,
        mime: 'chemical/x-mdl-sdfile',
        saveTitle,
      })
    } else if (result.pdbqt) {
      await saveTextFile(result.pdbqt, {
        filename: `pose_${poseIndex}.pdbqt`,
        mime: 'chemical/x-pdbqt',
        saveTitle,
      })
    }
  } catch {
    ElMessage.error(t('docking.errorExportPose'))
  }
}

// -- export bundle (TASK-08) ------------------------------------------------
const bundleVisible = ref(false)
const bundleBusy = ref(false)
const bundleSvgAvailable = ref(false)
const bundleInclude = ref<BundleMember[]>(['sdf', 'csv', 'config', 'html'])

/** The rendered diagram as standalone SVG source, or null when 2D is not open. */
function currentSvgSource(): string | null {
  const svg = document.querySelector('svg.interactions2d__svg')
  return svg ? new XMLSerializer().serializeToString(svg) : null
}

function openBundleDialog(): void {
  bundleSvgAvailable.value = currentSvgSource() !== null
  if (!bundleSvgAvailable.value) {
    bundleInclude.value = bundleInclude.value.filter((member) => member !== 'svg2d')
  }
  bundleVisible.value = true
}

async function downloadBundle(artifact: Artifact): Promise<void> {
  const response = await fetch(artifact.url)
  if (!response.ok) {
    throw new Error(`bundle fetch failed: ${response.status}`)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = artifact.name
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

async function exportBundle(): Promise<void> {
  if (!docking.activeJobId || bundleInclude.value.length === 0) return
  bundleBusy.value = true
  try {
    const include = [...bundleInclude.value]
    const artifact = await api.exportBundle(docking.activeJobId, {
      include,
      lang: locale.value === 'en-US' ? 'en-US' : 'zh-CN',
      ...(include.includes('svg2d') ? { svg2d: currentSvgSource() ?? undefined } : {}),
    })
    await downloadBundle(artifact)
    bundleVisible.value = false
    ElMessage.success(t('docking.exportBundle.success', { path: artifact.path }))
  } catch {
    ElMessage.error(t('docking.exportBundle.error'))
  } finally {
    bundleBusy.value = false
  }
}

async function runValidation(): Promise<void> {
  await docking.runValidation({
    center: box.center,
    size: box.size,
    referenceSdfPath: referenceSdfPath.value,
  })
  if (docking.validationError) {
    ElMessage.error(t('docking.errorValidateFailed'))
  }
}

/** ✓ / ⚠ / ✗ glyph for a pose's worst severity (null before validation). */
function statusGlyph(poseIndex: number): string {
  const item = docking.validation?.poses.find((p) => p.poseIndex === poseIndex)
  if (!item) return ''
  if (item.worstSeverity === 'error') return '✗'
  if (item.worstSeverity === 'warning') return '⚠'
  return '✓'
}

function statusClass(poseIndex: number): string {
  const item = docking.validation?.poses.find((p) => p.poseIndex === poseIndex)
  if (!item) return ''
  if (item.worstSeverity === 'error') return 'status--error'
  if (item.worstSeverity === 'warning') return 'status--warning'
  return 'status--ok'
}

/** Resolve a finding's messageKey to a locale string; fall back to the code. */
function findingMessage(finding: PoseFinding): string {
  if (te(finding.messageKey)) return t(finding.messageKey)
  return finding.code
}

/** Threshold value for a finding, when the backend echoed one. */
function findingThreshold(finding: PoseFinding): string | null {
  const value = finding.detail['threshold']
  if (typeof value === 'number') return String(value)
  return null
}

const selectedFindings = computed<PoseFinding[]>(
  () => docking.currentPoseValidation?.findings ?? [],
)

async function runRmsd(): Promise<void> {
  if (!selectedReference.value) return
  await docking.runRmsd(selectedReference.value)
  if (docking.rmsdError) {
    ElMessage.error(t('docking.rmsd.error'))
  }
}

/** RMSD-vs-reference value for a pose (1-based index), or '—' before/without it. */
function rmsdText(poseIndex: number): string {
  const value = docking.rmsd?.values[poseIndex - 1]
  return typeof value === 'number' ? value.toFixed(2) : '—'
}

function rmsdClass(poseIndex: number): string {
  const result = docking.rmsd
  if (!result) return ''
  const value = result.values[poseIndex - 1]
  if (typeof value !== 'number') return ''
  return value < result.threshold ? 'rmsd--ok' : 'rmsd--bad'
}

/** Poses shown in the table — filtered to cluster representatives when asked. */
const displayedPoses = computed(() => {
  const result = docking.clusters
  if (!docking.representativesOnly || !result) return docking.poses
  const representatives = new Set(result.clusters.map((c) => c.centroid))
  return docking.poses.filter((pose) => representatives.has(pose.index - 1))
})

/** C1/C2/… badge for a pose (1-based index), or '' before clustering. */
function clusterBadge(poseIndex: number): string {
  const result = docking.clusters
  if (!result) return ''
  const ordinal = result.clusters.findIndex((c) => c.members.includes(poseIndex - 1))
  return ordinal >= 0 ? `C${ordinal + 1}` : ''
}

function isRepresentative(poseIndex: number): boolean {
  const result = docking.clusters
  if (!result) return false
  return result.clusters.some((c) => c.centroid === poseIndex - 1)
}

async function runCluster(): Promise<void> {
  await docking.runCluster()
  if (docking.clusterError) {
    ElMessage.error(t('docking.cluster.error'))
  }
}
</script>

<template>
  <div v-if="docking.hasResult && docking.poses.length > 0" class="vs-card results-card">
    <div class="vs-card__header">
      <div><div class="vs-card__title">{{ t('docking.results') }}</div></div>
      <div class="header-actions">
        <ElButton
          size="small"
          :icon="Search"
          :loading="docking.validating"
          @click="runValidation"
        >
          {{ t('docking.validate.run') }}
        </ElButton>
        <ElSelect
          v-if="referenceOptions.length > 0"
          v-model="selectedReference"
          size="small"
          class="rmsd-reference"
          :placeholder="t('docking.rmsd.reference')"
        >
          <ElOption
            v-for="opt in referenceOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </ElSelect>
        <ElTooltip
          v-if="selectedReferenceIsPdbqt"
          :content="t('docking.rmsd.pdbqtHint')"
          placement="bottom"
        >
          <span class="rmsd-reference-hint" role="img" :aria-label="t('docking.rmsd.pdbqtHint')">
            <ElIcon :size="14"><InfoFilled /></ElIcon>
          </span>
        </ElTooltip>
        <ElButton
          size="small"
          :loading="docking.rmsding"
          :disabled="!selectedReference"
          @click="runRmsd"
        >
          {{ t('docking.rmsd.run') }}
        </ElButton>
        <span class="cluster-controls">
          <ElButton
            size="small"
            :loading="docking.clustering"
            :disabled="docking.poses.length < 2"
            @click="runCluster"
          >
            {{ t('docking.cluster.run') }}
          </ElButton>
          <span class="cluster-cutoff">
            <span class="cluster-cutoff__label">{{ t('docking.cluster.cutoff') }}</span>
            <ElSlider
              v-model="docking.clusterCutoff"
              :min="1"
              :max="3"
              :step="0.1"
              size="small"
              class="cluster-cutoff__slider"
            />
          </span>
          <ElCheckbox v-if="docking.clusters" v-model="docking.representativesOnly" size="small">
            {{ t('docking.cluster.onlyRepresentatives') }}
          </ElCheckbox>
          <ElButton
            size="small"
            :disabled="!docking.clusters || docking.clusters.clusters.length === 0"
            @click="docking.jumpToNextRepresentative()"
          >
            {{ t('docking.cluster.nextRepresentative') }}
          </ElButton>
        </span>
        <ElButton size="small" :icon="Download" @click="downloadCsv">
          {{ t('docking.exportCsv') }}
        </ElButton>
        <ElButton size="small" :icon="Download" @click="openBundleDialog">
          {{ t('docking.exportBundle.button') }}
        </ElButton>
      </div>
    </div>
    <div class="vs-card__body">
      <!-- Pose Navigator -->
      <div class="pose-nav">
        <ElButton
          size="small"
          :icon="ArrowLeft"
          :disabled="docking.currentPoseIndex === 0"
          @click="docking.prevPose()"
        />
        <div class="pose-nav__info">
          <span class="pose-nav__label">{{ t('docking.poseNavigator.pose') }}</span>
          <span class="pose-nav__index">
            {{ docking.currentPoseIndex + 1 }} / {{ docking.poses.length }}
          </span>
          <span v-if="docking.currentPose" class="pose-nav__energy">
            {{ docking.currentPose.affinity.toFixed(2) }} kcal/mol
          </span>
        </div>
        <ElButton
          size="small"
          :icon="ArrowRight"
          :disabled="docking.currentPoseIndex >= docking.poses.length - 1"
          @click="docking.nextPose()"
        />
      </div>

      <p v-if="docking.validation" class="validate-note">
        {{ t('docking.validate.note') }}
      </p>
      <p v-if="docking.validationError" class="validate-error">
        {{ t('docking.errorValidateFailed') }}
      </p>

      <p v-if="docking.rmsd" class="rmsd-note">
        {{
          t('docking.rmsd.note', {
            threshold: docking.rmsd.threshold,
            rate: Math.round(docking.rmsd.successRate * 100),
          })
        }}
      </p>
      <p v-if="docking.rmsd?.structureMatch === false" class="rmsd-warn">
        {{ t('docking.rmsd.mismatch') }}
      </p>
      <p v-if="docking.rmsdError" class="rmsd-error">
        {{ t('docking.rmsd.error') }}
      </p>

      <p v-if="docking.clusters" class="cluster-note">
        {{
          t('docking.cluster.note', {
            n: docking.clusters.nClusters,
            cutoff: docking.clusters.cutoff,
          })
        }}
      </p>
      <p v-if="docking.clusterError" class="cluster-error">
        {{ t('docking.cluster.error') }}
      </p>

      <div class="pose-table-wrap">
        <table class="pose-table">
          <thead>
            <tr>
              <th>{{ t('docking.poseTable.pose') }}</th>
              <th>{{ t('docking.poseTable.affinity') }}</th>
              <th>
                <ElTooltip :content="t('docking.poseTable.rmsdHint')" placement="top">
                  <span class="th-tip">{{ t('docking.poseTable.rmsdLb') }}</span>
                </ElTooltip>
              </th>
              <th>
                <ElTooltip :content="t('docking.poseTable.rmsdHint')" placement="top">
                  <span class="th-tip">{{ t('docking.poseTable.rmsdUb') }}</span>
                </ElTooltip>
              </th>
              <th v-if="docking.rmsd">{{ t('docking.poseTable.rmsdRef') }}</th>
              <th v-if="docking.clusters">{{ t('docking.poseTable.cluster') }}</th>
              <th v-if="docking.validation">{{ t('docking.poseTable.status') }}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="pose in displayedPoses"
              :key="pose.index"
              :class="{ 'pose-row--active': pose.index === docking.currentPose?.index }"
              @click="docking.selectPose(pose.index - 1)"
            >
              <td>{{ pose.index }}</td>
              <td :class="{ 'is-best': docking.bestAffinity !== null && pose.affinity === docking.bestAffinity }">
                {{ pose.affinity.toFixed(2) }}
              </td>
              <td>{{ pose.rmsdLower.toFixed(2) }}</td>
              <td>{{ pose.rmsdUpper.toFixed(2) }}</td>
              <td v-if="docking.rmsd" :class="rmsdClass(pose.index)">
                {{ rmsdText(pose.index) }}
              </td>
              <td v-if="docking.clusters">
                <span
                  class="cluster-badge"
                  :class="{ 'cluster-badge--rep': isRepresentative(pose.index) }"
                >
                  {{ clusterBadge(pose.index) }}
                </span>
              </td>
              <td v-if="docking.validation" class="status-cell">
                <span :class="statusClass(pose.index)">{{ statusGlyph(pose.index) }}</span>
              </td>
              <td>
                <ElButton size="small" link @click.stop="exportSinglePose(pose.index)">
                  {{ t('docking.exportPose') }}
                </ElButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Findings detail for the selected pose -->
      <div v-if="docking.validation" class="findings">
        <div class="findings__title">
          {{ t('docking.validate.detailTitle', { pose: docking.currentPoseIndex + 1 }) }}
        </div>
        <ul v-if="selectedFindings.length > 0" class="findings__list">
          <li
            v-for="(finding, i) in selectedFindings"
            :key="`${finding.code}-${i}`"
            :class="finding.severity === 'error' ? 'status--error' : 'status--warning'"
          >
            <span class="findings__glyph">
              {{ finding.severity === 'error' ? '✗' : '⚠' }}
            </span>
            <span class="findings__text">{{ findingMessage(finding) }}</span>
            <span v-if="findingThreshold(finding)" class="findings__threshold">
              {{ t('docking.validate.threshold', { value: findingThreshold(finding) }) }}
            </span>
          </li>
        </ul>
        <p v-else class="findings__empty">{{ t('docking.validate.noFindings') }}</p>
      </div>
    </div>

    <ElDialog
      v-model="bundleVisible"
      :title="t('docking.exportBundle.title')"
      width="26rem"
    >
      <div class="bundle-options">
        <ElCheckboxGroup v-model="bundleInclude">
          <ElCheckbox value="sdf">
            {{ t('docking.exportBundle.sdf') }}
          </ElCheckbox>
          <ElCheckbox value="csv">
            {{ t('docking.exportBundle.csv') }}
          </ElCheckbox>
          <ElCheckbox value="config">
            {{ t('docking.exportBundle.config') }}
          </ElCheckbox>
          <ElCheckbox value="html">
            {{ t('docking.exportBundle.html') }}
          </ElCheckbox>
          <ElCheckbox value="svg2d" :disabled="!bundleSvgAvailable">
            {{ t('docking.exportBundle.svg2d') }}
          </ElCheckbox>
        </ElCheckboxGroup>
        <p v-if="!bundleSvgAvailable" class="bundle-options__hint">
          {{ t('docking.exportBundle.svgMissing') }}
        </p>
      </div>
      <template #footer>
        <ElButton @click="bundleVisible = false">{{ t('docking.exportBundle.cancel') }}</ElButton>
        <ElButton
          type="primary"
          :loading="bundleBusy"
          :disabled="bundleInclude.length === 0"
          @click="exportBundle"
        >
          {{ t('docking.exportBundle.confirm') }}
        </ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<style scoped>
.results-card :deep(.vs-card__header) {
  flex-wrap: wrap;
  align-items: flex-start;
}

.header-actions {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  align-items: center;
}

.pose-table-wrap {
  overflow: auto;
  max-height: 300px;
}

.pose-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}

.pose-table th,
.pose-table td {
  padding: 6px 10px;
  text-align: left;
  border-bottom: 1px solid var(--vs-border);
}

.pose-table th {
  font-weight: 600;
  color: var(--vs-text-muted);
  position: sticky;
  top: 0;
  background: var(--vs-bg-surface);
}

.is-best {
  color: var(--vs-accent);
  font-weight: 600;
}

.pose-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 8px 0;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--vs-border);
}

.pose-nav__info {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 160px;
  justify-content: center;
}

.pose-nav__label {
  font-size: 12px;
  color: var(--vs-text-muted);
}

.pose-nav__index {
  font-size: 14px;
  font-weight: 600;
  color: var(--vs-text);
}

.pose-nav__energy {
  font-size: 12px;
  color: var(--vs-accent);
  font-weight: 500;
}

.pose-row--active td {
  background: var(--vs-bg-sunken);
}

.pose-table tbody tr {
  cursor: pointer;
}

.pose-table tbody tr:hover td {
  background: var(--vs-bg-sunken);
}

.status-cell {
  text-align: center;
  font-size: 14px;
}

.status--ok {
  color: var(--vs-success, #67c23a);
  font-weight: 600;
}

.status--warning {
  color: var(--vs-warning, #e6a23c);
  font-weight: 600;
}

.status--error {
  color: var(--vs-danger, #f56c6c);
  font-weight: 600;
}

.validate-note {
  margin: 4px 0 8px;
  font-size: 12px;
  color: var(--vs-text-muted);
}

.validate-error {
  margin: 4px 0 8px;
  font-size: 12px;
  color: var(--vs-danger, #f56c6c);
}

.rmsd-reference {
  width: 160px;
}

.rmsd-note {
  margin: 4px 0 8px;
  font-size: 12px;
  color: var(--vs-text-muted);
}

.rmsd-warn {
  margin: 4px 0 8px;
  font-size: 12px;
  color: var(--vs-warning, #e6a23c);
}

.rmsd-error {
  margin: 4px 0 8px;
  font-size: 12px;
  color: var(--vs-danger, #f56c6c);
}

.rmsd--ok {
  color: var(--vs-success, #67c23a);
  font-weight: 600;
}

.rmsd--bad {
  color: var(--vs-danger, #f56c6c);
  font-weight: 600;
}

.th-tip {
  border-bottom: 1px dotted var(--vs-text-muted);
  cursor: help;
}

.cluster-controls {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.cluster-cutoff {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.cluster-cutoff__label {
  font-size: 12px;
  color: var(--vs-text-muted);
  white-space: nowrap;
}

.cluster-cutoff__slider {
  width: 100px;
}

.cluster-note {
  margin: 4px 0 8px;
  font-size: 12px;
  color: var(--vs-text-muted);
}

.cluster-error {
  margin: 4px 0 8px;
  font-size: 12px;
  color: var(--vs-danger, #f56c6c);
}

.cluster-badge {
  display: inline-block;
  min-width: 26px;
  padding: 1px 6px;
  border: 1px solid var(--vs-border);
  border-radius: 10px;
  font-size: 11.5px;
  font-weight: 600;
  text-align: center;
  color: var(--vs-text-muted);
}

.cluster-badge--rep {
  border-color: var(--vs-accent);
  color: var(--vs-accent);
}

.findings {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--vs-border);
}

.findings__title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--vs-text-muted);
  margin-bottom: 6px;
}

.findings__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12.5px;
}

.findings__list li {
  display: flex;
  gap: 6px;
  align-items: baseline;
}

.findings__glyph {
  flex-shrink: 0;
}

.findings__threshold {
  color: var(--vs-text-muted);
  font-size: 11.5px;
}

.findings__empty {
  margin: 0;
  font-size: 12.5px;
  color: var(--vs-text-muted);
}

.bundle-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bundle-options :deep(.el-checkbox-group) {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bundle-options__hint {
  margin: 0;
  font-size: 12px;
  color: var(--vs-text-muted);
}
</style>
