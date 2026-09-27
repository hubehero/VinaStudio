<script setup lang="ts">
import { ElButton, ElDialog, ElMessage, ElMessageBox } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { useMoleculeStore } from '@/stores/molecules'

import { SNAP_PX, atomNear, nextPlacement } from './geometry'
import { addAtom, addBond, atomById, findBond, removeAtom, removeBond } from './model'
import SketcherCanvas from './SketcherCanvas.vue'
import SketcherToolbar from './SketcherToolbar.vue'
import { provideSketcher, useSketcher } from './state'

const state = useSketcher()
provideSketcher(state)

const store = useMoleculeStore()
const { t } = useI18n()

const visible = ref(false)
const busy = ref(false)
// Set after a successful export so the discard confirm cannot nag a user
// whose structure already landed in the molecule library.
const exported = ref(false)

const statusText = computed(() => {
  if (state.analyzeState.value === 'pending') return t('sketcher.analyzing')
  if (state.analyzeState.value === 'error') return t('sketcher.analyzeFailed')
  const analysis = state.analysis.value
  if (analysis?.error) return analysis.error
  if (!state.hasStructure.value) return t('sketcher.emptyCanvas')
  if (analysis?.smiles) return t('sketcher.valid')
  return t('sketcher.analyzing')
})

const statusError = computed(
  () =>
    state.analyzeState.value === 'error' ||
    !!state.analysis.value?.error ||
    (state.analyzeState.value === 'ok' && !state.analysis.value?.smiles),
)

async function confirmDiscard(): Promise<boolean> {
  if (!state.hasStructure.value || exported.value) return true
  try {
    await ElMessageBox.confirm(t('sketcher.confirmCloseMessage'), {
      type: 'warning',
      confirmButtonText: t('common.close'),
      cancelButtonText: t('common.cancel'),
    })
    return true
  } catch {
    return false
  }
}

async function handleBeforeClose(done: () => void): Promise<void> {
  if (await confirmDiscard()) done()
}

async function requestClose(): Promise<void> {
  if (await confirmDiscard()) visible.value = false
}

async function useStructure(): Promise<void> {
  if (busy.value || !state.exportable.value) return
  const smiles = state.analysis.value?.smiles
  if (!smiles) return
  busy.value = true
  try {
    const outcome = await store.loadFromSmiles(smiles)
    if (outcome.added > 0) {
      ElMessage.success(t('molecules.smilesDone', { n: outcome.added }))
      exported.value = true
      visible.value = false
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : String(error))
  } finally {
    busy.value = false
  }
}

async function copySmiles(): Promise<void> {
  const smiles = state.analysis.value?.smiles
  if (!smiles) return
  try {
    await navigator.clipboard.writeText(smiles)
    ElMessage.success(t('common.copied'))
  } catch {
    ElMessage.error(t('common.copiedFailed'))
  }
}

// -- keyboard shortcuts (MoleditPy keyPressEvent order) ---------------------

const ELEMENT_KEYS = 'cnospfbih'
// Shifted letters that mean something: the rest are deliberate no-ops.
const SHIFT_ELEMENTS: Record<string, string> = { c: 'Cl', b: 'Br', s: 'Si' }

/** Zigzag side for digit placement; toggles after each placement so digit
    sequences walk a chain the way chemists draw it.  Module-level so the
    alternation survives pointer moves; `open()` re-seeds it. */
let placementClockwise = true

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return (
    target.tagName === 'INPUT' ||
    target.tagName === 'TEXTAREA' ||
    target.tagName === 'SELECT' ||
    target.isContentEditable
  )
}

/** Radical/charge key targets: the selected atoms, else the cursor atom. */
function keyboardTargets(): number[] {
  if (state.selection.value.length > 0) return state.selection.value
  const atomId = state.pointer.value.atomId
  return atomId !== null ? [atomId] : []
}

function handleKeyDown(e: KeyboardEvent): void {
  if (!visible.value || isTypingTarget(e.target)) return

  const key = e.key
  const lower = key.toLowerCase()
  const command = e.ctrlKey || e.metaKey

  if (command && !e.altKey) {
    if (lower === 'z' && !e.shiftKey) {
      e.preventDefault()
      state.undo()
      return
    }
    if (lower === 'y' || (lower === 'z' && e.shiftKey)) {
      e.preventDefault()
      state.redo()
      return
    }
    if (lower === 'a') {
      // After isTypingTarget (inputs keep their native select-all) and
      // alongside undo/redo — never inside the plain-key element shortcuts.
      e.preventDefault()
      state.selection.value = state.snapshot.value.atoms.map((atom) => atom.id)
      state.selectedBond.value = null
      return
    }
    return
  }
  if (e.ctrlKey || e.metaKey || e.altKey) return

  if (key === 'Escape') {
    // Ours, kept from the task book: Escape always hands control back to
    // the selection tool and drops any selection.
    state.tool.value = 'select'
    state.clearSelection()
    return
  }

  if (key === 'Delete' || key === 'Backspace') {
    // Selection ∪ cursor item — one commit, so one undo restores it all.
    const cursor = state.pointer.value
    const ids = new Set(state.selection.value)
    if (cursor.atomId !== null) ids.add(cursor.atomId)
    const bond = state.selectedBond.value ?? cursor.bond
    if (ids.size === 0 && !bond) return
    e.preventDefault()
    state.commit((s) => {
      for (const id of ids) removeAtom(s, id)
      if (bond) removeBond(s, bond[0], bond[1])
    })
    return
  }

  if (key === '4') {
    // Benzene one-shot: on a cursor item it fuses immediately; on empty
    // canvas it arms the template tool so the next click places (MoleditPy
    // always consumes the key).
    e.preventDefault()
    const cursor = state.pointer.value
    const scene = cursor.scene
    if (cursor.atomId !== null) {
      state.placeRing(
        { kind: 'atom', atomId: cursor.atomId, ...(scene ? { cursor: scene } : {}) },
        { size: 6, benzene: true },
      )
      return
    }
    if (cursor.bond) {
      state.placeRing(
        { kind: 'bond', a1: cursor.bond[0], a2: cursor.bond[1], ...(scene ? { cursor: scene } : {}) },
        { size: 6, benzene: true },
      )
      return
    }
    state.templateSize.value = 6
    state.templateBenzene.value = true
    state.templateId.value = null
    state.templateSymbols.value = null
    state.tool.value = 'template'
    return
  }

  if (key === '.') {
    e.preventDefault()
    const ids = keyboardTargets()
    if (ids.length === 0) return
    state.commit((s) => {
      for (const id of ids) {
        const atom = atomById(s, id)
        if (atom) atom.radical = (atom.radical + 1) % 3
      }
    })
    return
  }

  if (key === '+' || key === '-') {
    e.preventDefault()
    const step = key === '+' ? 1 : -1
    const ids = keyboardTargets()
    if (ids.length === 0) return
    state.commit((s) => {
      for (const id of ids) {
        const atom = atomById(s, id)
        if (atom) atom.charge = Math.max(-9, Math.min(9, atom.charge + step))
      }
    })
    return
  }

  if (key.length === 1 && /[a-z]/i.test(key)) {
    let symbol: string
    if (e.shiftKey) {
      const mapped = SHIFT_ELEMENTS[lower]
      if (!mapped) return
      symbol = mapped
    } else {
      if (!ELEMENT_KEYS.includes(lower)) return
      symbol = key.toUpperCase()
    }
    // Cursor over a different element → rename in place; otherwise arm the
    // atom tool with that element (MoleditPy element-letter semantics).
    const cursorAtomId = state.pointer.value.atomId
    if (cursorAtomId !== null) {
      const atom = atomById(state.snapshot.value, cursorAtomId)
      if (atom && atom.symbol !== symbol) {
        state.commit((s) => {
          const target = atomById(s, cursorAtomId)
          if (target) target.symbol = symbol
        })
        return
      }
    }
    state.symbol.value = symbol
    state.tool.value = 'atom'
    return
  }

  if (lower === 'w' || lower === 'd') {
    const stereo = lower === 'w' ? 1 : 2
    const cursor = state.pointer.value
    const bondTarget = cursor.bond ?? state.selectedBond.value
    if (bondTarget) {
      const [a1, a2] = bondTarget
      state.commit((s) => {
        const bond = findBond(s, a1, a2)
        if (!bond) return
        if (bond.stereo === stereo) {
          // Same marker again flips the wedge/hash direction.
          const swapped = bond.a1
          bond.a1 = bond.a2
          bond.a2 = swapped
          return
        }
        bond.order = 1
        bond.stereo = stereo
      })
      return
    }
    // No bond target: arm the tool instead of silently doing nothing
    // (deviation from MoleditPy, disclosed in §12.8).
    state.bondOrder.value = 1
    state.bondStereo.value = stereo
    state.tool.value = 'bond'
    return
  }

  if (key === '1' || key === '2' || key === '3') {
    e.preventDefault()
    const order = Number(key) as 1 | 2 | 3
    const cursor = state.pointer.value
    const bondTarget = cursor.bond ?? state.selectedBond.value
    if (bondTarget) {
      // Digit on a bond writes the order directly — never cycles.
      const [a1, a2] = bondTarget
      state.commit((s) => {
        const bond = findBond(s, a1, a2)
        if (!bond) return
        bond.order = order
        bond.stereo = 0
      })
      return
    }
    // No bond target → placement: one bond out of the cursor atom (else the
    // single selected atom), snapping within 14 screen px or creating a
    // fresh carbon (MoleditPy digit placement).
    const selectedId =
      state.selection.value.length === 1 ? state.selection.value[0] : undefined
    const startId = cursor.atomId ?? selectedId ?? null
    if (startId === null) {
      state.bondOrder.value = order
      state.bondStereo.value = 0
      state.tool.value = 'bond'
      return
    }
    const snapshot = state.snapshot.value
    const start = atomById(snapshot, startId)
    if (!start) return
    const dest = nextPlacement(snapshot, startId, {
      targetOrder: order,
      clockwise: placementClockwise,
    })
    if (!dest) return
    const radius = SNAP_PX / state.view.value.zoom
    const snapId = atomNear(snapshot, dest, radius, startId)
    const placed = state.commit((s) => {
      const secondId = snapId !== null ? snapId : addAtom(s, 'C', dest.x, dest.y).id
      addBond(s, startId, secondId, order, 0)
    })
    // Triple bonds continue straight, so the side never matters then.
    if (placed && order !== 3) placementClockwise = !placementClockwise
    state.clearSelection()
    return
  }

  if (key === '5') {
    // Hash-bond arm is unconditional — digits 1-3 already returned above.
    e.preventDefault()
    state.bondOrder.value = 1
    state.bondStereo.value = 2
    state.tool.value = 'bond'
    return
  }

  if (key === ' ') {
    e.preventDefault()
    if (state.tool.value !== 'select') {
      state.tool.value = 'select'
      return
    }
    state.selection.value = state.snapshot.value.atoms.map((atom) => atom.id)
    state.selectedBond.value = null
  }
}

onMounted(() => window.addEventListener('keydown', handleKeyDown))
onBeforeUnmount(() => window.removeEventListener('keydown', handleKeyDown))

function handleClosed(): void {
  state.reset()
  exported.value = false
}

function open(): void {
  placementClockwise = true
  visible.value = true
}

defineExpose({ open })
</script>

<template>
  <ElDialog
    v-model="visible"
    fullscreen
    :title="t('molecules.drawTitle')"
    class="sketcher-dialog"
    :before-close="handleBeforeClose"
    @closed="handleClosed"
  >
    <div class="sketcher-dialog__main" data-test="sketcher-main">
      <SketcherToolbar />
      <SketcherCanvas />
    </div>
    <template #footer>
      <div class="sketcher-dialog__footer">
        <div class="sketcher-dialog__status">
          <span
            class="sketcher-dialog__state"
            :class="{
              'is-error': statusError,
              'is-pending': state.analyzeState.value === 'pending',
            }"
            data-test="sketcher-status"
          >
            {{ statusText }}
          </span>
          <code class="sketcher-dialog__smiles" data-test="sketcher-smiles">
            {{ state.analysis.value?.smiles ?? '—' }}
          </code>
          <ElButton
            size="small"
            :disabled="!state.analysis.value?.smiles"
            data-test="sketcher-copy-smiles"
            :title="t('common.copy')"
            @click="copySmiles"
          >
            {{ t('common.copy') }}
          </ElButton>
        </div>
        <ElButton data-test="sketcher-close" @click="requestClose">
          {{ t('common.cancel') }}
        </ElButton>
        <ElButton
          type="primary"
          :disabled="!state.exportable.value"
          :loading="busy"
          data-test="sketcher-use"
          @click="useStructure"
        >
          {{ t('molecules.drawUse') }}
        </ElButton>
      </div>
    </template>
  </ElDialog>
</template>

<style scoped>
/* Fullscreen dialog: header + footer only; the editor owns the rest. */
.sketcher-dialog__main {
  display: flex;
  height: calc(100vh - 150px);
  min-height: 480px;
  width: 100%;
}

.sketcher-dialog__footer {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.sketcher-dialog__footer .el-button + .el-button {
  margin-left: 0;
}

.sketcher-dialog__status {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 12px;
  min-width: 0;
  text-align: left;
}

.sketcher-dialog__state {
  flex: 0 0 auto;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.sketcher-dialog__state.is-pending {
  color: var(--el-color-warning);
}

.sketcher-dialog__state.is-error {
  color: var(--el-color-danger);
}

.sketcher-dialog__smiles {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-family: var(--vs-font-mono, monospace);
  font-size: 12px;
  color: var(--el-text-color-regular);
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
