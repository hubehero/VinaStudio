<script setup lang="ts">
import { ref } from 'vue'
import { ElIcon, ElMessage, ElMessageBox, ElPopover } from 'element-plus'
import { RefreshLeft, RefreshRight } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'

import { api } from '@/api/http'

import { HETEROCYCLE_TEMPLATES, PERIODIC_TABLE, type HeteroTemplate } from './periodic-table'
import { ELEMENT_PANEL, injectSketcher, type SketchTool } from './state'

const state = injectSketcher()
const { t } = useI18n()
const tableVisible = ref(false)

const TOOLS: { id: SketchTool; label: string; test: string }[] = [
  { id: 'select', label: 'sketcher.toolSelect', test: 'tool-select' },
  { id: 'atom', label: 'sketcher.toolAtom', test: 'tool-atom' },
  { id: 'bond', label: 'sketcher.toolBond', test: 'tool-bond' },
  { id: 'erase', label: 'sketcher.toolErase', test: 'tool-erase' },
  { id: 'charge+', label: 'sketcher.toolChargeAdd', test: 'tool-charge-add' },
  { id: 'charge-', label: 'sketcher.toolChargeSub', test: 'tool-charge-sub' },
  { id: 'template', label: 'sketcher.toolTemplate', test: 'tool-template' },
  { id: 'chain', label: 'sketcher.toolChain', test: 'tool-chain' },
  { id: 'radical', label: 'sketcher.toolRadical', test: 'tool-radical' },
]

/** Template ring sizes (task book 4.4); benzene is offered at size 6 only. */
const RING_SIZES = [3, 4, 5, 6, 7, 8, 9]

const ORDERS: { id: 1 | 2 | 3; glyph: string; label: string; test: string }[] = [
  { id: 1, glyph: '—', label: 'sketcher.bondSingle', test: 'bond-order-1' },
  { id: 2, glyph: '═', label: 'sketcher.bondDouble', test: 'bond-order-2' },
  { id: 3, glyph: '≡', label: 'sketcher.bondTriple', test: 'bond-order-3' },
]

function pickTool(tool: SketchTool): void {
  state.tool.value = tool
}

function pickElement(symbol: string): void {
  state.symbol.value = symbol
  state.tool.value = 'atom'
}

function pickFromTable(symbol: string): void {
  pickElement(symbol)
  tableVisible.value = false
}

function pickOrder(order: 1 | 2 | 3): void {
  state.bondOrder.value = order
  state.bondStereo.value = 0
  state.tool.value = 'bond'
}

function pickRing(size: number, benzene: boolean): void {
  state.templateSize.value = size
  state.templateBenzene.value = benzene
  state.templateId.value = null
  state.templateSymbols.value = null
  state.tool.value = 'template'
}

function isRingActive(size: number, benzene: boolean): boolean {
  return (
    state.tool.value === 'template' &&
    state.templateId.value === null &&
    state.templateSize.value === size &&
    state.templateBenzene.value === benzene
  )
}

/** Hetero palette: same template tool, vertex symbols carried into the plan. */
function pickHetero(template: HeteroTemplate): void {
  state.templateSize.value = template.size
  state.templateBenzene.value = template.benzene
  state.templateId.value = template.id
  state.templateSymbols.value = [...template.symbols]
  state.tool.value = 'template'
}

function isHeteroActive(template: HeteroTemplate): boolean {
  return (
    state.tool.value === 'template' && state.templateId.value === template.id
  )
}

/** W/D are toggles: clicking the active marker again returns to a plain bond. */
function pickStereo(stereo: 1 | 2): void {
  state.bondStereo.value = state.bondStereo.value === stereo ? 0 : stereo
  if (state.bondStereo.value !== 0) state.bondOrder.value = 1
  state.tool.value = 'bond'
}

async function handleCleanup(): Promise<void> {
  if (!(await state.cleanup())) ElMessage.error(t('sketcher.cleanupFailed'))
}

/** Paste a SMILES and replace the whole canvas (task book C5). */
async function handleImport(): Promise<void> {
  if (state.hasStructure.value) {
    // Replacing a drawing the user spent time on needs a conscious yes;
    // the single-commit undo is the safety net after that.
    try {
      await ElMessageBox.confirm(t('sketcher.importConfirm'), {
        type: 'warning',
        confirmButtonText: t('common.yes'),
        cancelButtonText: t('common.cancel'),
      })
    } catch {
      return
    }
  }
  let smiles: string
  try {
    const outcome = await ElMessageBox.prompt(t('sketcher.import'), {
      inputPlaceholder: t('sketcher.importPlaceholder'),
      inputValidator: (value: string) => value.trim().length > 0 || t('sketcher.importEmpty'),
      confirmButtonText: t('sketcher.import'),
      cancelButtonText: t('common.cancel'),
    })
    smiles = outcome.value.trim()
  } catch {
    return
  }
  try {
    const layout = await api.layoutSketch(smiles)
    state.importLayout(layout.atoms, layout.bonds)
  } catch (error) {
    // ApiError carries the backend's human reason (422 detail) verbatim.
    ElMessage.error(error instanceof Error ? error.message : String(error))
  }
}
</script>

<template>
  <aside class="sketch-toolbar" data-test="sketch-toolbar">
    <div class="sketch-toolbar__section">
      <button
        v-for="tool in TOOLS"
        :key="tool.id"
        type="button"
        class="sk-tool"
        :class="{ 'is-active': state.tool.value === tool.id }"
        :data-test="tool.test"
        :title="t(tool.label)"
        @click="pickTool(tool.id)"
      >
        {{ t(tool.label) }}
      </button>
    </div>

    <div class="sketch-toolbar__section sketch-toolbar__elements">
      <button
        v-for="el in ELEMENT_PANEL"
        :key="el"
        type="button"
        class="sk-element"
        :class="{ 'is-active': state.tool.value === 'atom' && state.symbol.value === el }"
        :data-test="`element-${el}`"
        :title="el"
        @click="pickElement(el)"
      >
        {{ el }}
      </button>
      <el-popover v-model:visible="tableVisible" placement="right-start" :width="400" trigger="click">
        <template #reference>
          <button
            type="button"
            class="sk-pt-open"
            data-test="open-periodic-table"
            :title="t('sketcher.periodicTable')"
          >
            {{ t('sketcher.periodicTable') }}
          </button>
        </template>
        <div class="pt-grid" data-test="periodic-table">
          <div class="pt-cell pt-marker" :style="{ gridRow: 6, gridColumn: 3 }">57-71</div>
          <div class="pt-cell pt-marker" :style="{ gridRow: 7, gridColumn: 3 }">89-103</div>
          <div class="pt-label" :style="{ gridRow: 9, gridColumn: '1 / 3' }">
            {{ t('sketcher.lanthanides') }}
          </div>
          <div class="pt-label" :style="{ gridRow: 10, gridColumn: '1 / 3' }">
            {{ t('sketcher.actinides') }}
          </div>
          <button
            v-for="el in PERIODIC_TABLE"
            :key="el.z"
            type="button"
            class="pt-cell"
            :style="{ gridRow: el.row, gridColumn: el.col }"
            :data-test="`pt-${el.symbol}`"
            :title="`${el.symbol} (${el.z})`"
            @click="pickFromTable(el.symbol)"
          >
            {{ el.symbol }}
          </button>
        </div>
      </el-popover>
    </div>

    <div class="sketch-toolbar__section">
      <button
        v-for="order in ORDERS"
        :key="order.id"
        type="button"
        class="sk-glyph"
        :class="{ 'is-active': state.tool.value === 'bond' && state.bondOrder.value === order.id && state.bondStereo.value === 0 }"
        :data-test="order.test"
        :title="t(order.label)"
        @click="pickOrder(order.id)"
      >
        {{ order.glyph }}
      </button>
      <button
        type="button"
        class="sk-glyph"
        :class="{ 'is-active': state.bondStereo.value === 1 }"
        data-test="bond-wedge"
        :title="t('sketcher.wedge')"
        @click="pickStereo(1)"
      >
        W
      </button>
      <button
        type="button"
        class="sk-glyph"
        :class="{ 'is-active': state.bondStereo.value === 2 }"
        data-test="bond-dash"
        :title="t('sketcher.hash')"
        @click="pickStereo(2)"
      >
        D
      </button>
    </div>

    <div class="sketch-toolbar__section sketch-toolbar__rings">
      <button
        v-for="n in RING_SIZES"
        :key="n"
        type="button"
        class="sk-ring"
        :class="{ 'is-active': isRingActive(n, false) }"
        :data-test="`sketcher-ring-${n}`"
        :title="String(n)"
        @click="pickRing(n, false)"
      >
        {{ n }}
      </button>
      <button
        type="button"
        class="sk-ring"
        :class="{ 'is-active': isRingActive(6, true) }"
        data-test="sketcher-ring-benzene"
        :title="t('sketcher.ringBenzene')"
        @click="pickRing(6, true)"
      >
        Bz
      </button>
    </div>

    <div class="sketch-toolbar__section sketch-toolbar__hetero">
      <div class="sk-section-label">{{ t('sketcher.heterocycles') }}</div>
      <div class="sk-hetero-grid">
        <button
          v-for="h in HETEROCYCLE_TEMPLATES"
          :key="h.id"
          type="button"
          class="sk-ring sk-hetero"
          :class="{ 'is-active': isHeteroActive(h) }"
          :data-test="`sketcher-ring-${h.id}`"
          :title="t(h.labelKey)"
          @click="pickHetero(h)"
        >
          {{ t(h.labelKey) }}
        </button>
      </div>
    </div>

    <div class="sketch-toolbar__section sketch-toolbar__history">
      <button
        type="button"
        class="sk-icon"
        :disabled="!state.canUndo.value"
        data-test="sketcher-undo"
        :title="t('sketcher.undo')"
        @click="state.undo()"
      >
        <ElIcon><RefreshLeft /></ElIcon>
      </button>
      <button
        type="button"
        class="sk-icon"
        :disabled="!state.canRedo.value"
        data-test="sketcher-redo"
        :title="t('sketcher.redo')"
        @click="state.redo()"
      >
        <ElIcon><RefreshRight /></ElIcon>
      </button>
    </div>
    <div class="sketch-toolbar__section">
      <button
        type="button"
        class="sk-cleanup"
        data-test="sketcher-import"
        :title="t('sketcher.import')"
        @click="handleImport"
      >
        {{ t('sketcher.import') }}
      </button>
      <button
        type="button"
        class="sk-cleanup"
        :disabled="!state.hasStructure.value"
        data-test="sketcher-cleanup"
        :title="t('sketcher.cleanup')"
        @click="handleCleanup"
      >
        {{ t('sketcher.cleanup') }}
      </button>
    </div>
  </aside>
</template>

<style scoped>
.sketch-toolbar {
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  gap: 10px;
  width: 150px;
  padding: 12px 10px;
  overflow-y: auto;
  border-right: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color-overlay);
}

.sketch-toolbar__section {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.sk-tool,
.sk-element,
.sk-glyph,
.sk-icon {
  box-sizing: border-box;
  margin: 0;
  font: inherit;
  font-size: 12px;
  color: var(--el-text-color-regular);
  cursor: pointer;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
}

.sk-tool {
  flex: 1 1 calc(50% - 6px);
  padding: 5px 4px;
}

.sk-element {
  flex: 0 0 calc(33.333% - 4px);
  padding: 5px 0;
  font-weight: 600;
}

.sk-pt-open {
  box-sizing: border-box;
  flex: 0 0 100%;
  margin: 0;
  font: inherit;
  font-size: 12px;
  color: var(--el-text-color-regular);
  cursor: pointer;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 5px 4px;
}

.sk-pt-open:hover {
  border-color: var(--el-color-primary-light-5);
}

.pt-grid {
  display: grid;
  grid-template-columns: repeat(18, 1fr);
  gap: 2px;
}

.pt-cell {
  box-sizing: border-box;
  margin: 0;
  padding: 3px 0;
  overflow: hidden;
  font-family: inherit;
  font-size: 10px;
  line-height: 1.1;
  color: var(--el-text-color-regular);
  text-align: center;
  cursor: pointer;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 2px;
}

.pt-cell:hover {
  border-color: var(--el-color-primary);
}

.pt-marker {
  font-size: 8px;
  color: var(--el-text-color-placeholder);
  cursor: default;
  background: transparent;
  border-color: transparent;
}

.pt-marker:hover {
  border-color: transparent;
}

.pt-label {
  align-self: center;
  padding-right: 4px;
  overflow: hidden;
  font-size: 10px;
  color: var(--el-text-color-secondary);
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sk-glyph {
  flex: 0 0 calc(33.333% - 4px);
  padding: 5px 0;
  font-size: 14px;
}

.sk-ring {
  flex: 0 0 calc(33.333% - 4px);
  padding: 5px 0;
  font-weight: 600;
}

.sk-section-label {
  flex: 0 0 100%;
  margin-top: 2px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.sk-hetero-grid {
  display: flex;
  flex-wrap: wrap;
  flex: 0 0 100%;
  gap: 4px;
}

.sk-hetero {
  flex: 0 0 calc(33.333% - 3px);
  font-size: 10px;
  overflow: hidden;
  white-space: nowrap;
}

.sk-icon {
  display: inline-flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  padding: 5px 0;
}

.sk-tool:hover,
.sk-element:hover,
.sk-glyph:hover,
.sk-ring:hover,
.sk-icon:hover:not(:disabled) {
  border-color: var(--el-color-primary-light-5);
}

.sk-tool.is-active,
.sk-element.is-active,
.sk-glyph.is-active,
.sk-ring.is-active {
  color: var(--el-color-white);
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
}

.sk-icon:disabled {
  cursor: not-allowed;
  opacity: 0.4;
}

.sk-cleanup {
  box-sizing: border-box;
  width: 100%;
  margin: 0;
  font: inherit;
  font-size: 12px;
  color: var(--el-text-color-regular);
  cursor: pointer;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 5px 4px;
}

.sk-cleanup:hover:not(:disabled) {
  border-color: var(--el-color-primary-light-5);
}

.sk-cleanup:disabled {
  cursor: not-allowed;
  opacity: 0.4;
}
</style>
