<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ReceptorSequence } from '@/types/api'

const props = defineProps<{
  chains: ReceptorSequence['chains']
  selected: Set<string>
  readonly?: boolean
  contactResidues?: Set<string>
}>()

const emit = defineEmits<{
  toggle: [chainSeqId: string]
  toggleRange: [from: string, to: string]
  hover: [chainSeqId: string | null]
}>()

const { t } = useI18n()

const ROW_SIZE = 60
const INITIAL_ROWS = 8
const PAGE_ROWS = 8

/** Display only: 20 standard residues + SEC/PYL; HIS stays H because
 * protonation inference belongs to receptor preparation, not this view. */
const ONE_LETTER: Record<string, string> = {
  ALA: 'A',
  ARG: 'R',
  ASN: 'N',
  ASP: 'D',
  CYS: 'C',
  GLN: 'Q',
  GLU: 'E',
  GLY: 'G',
  HIS: 'H',
  ILE: 'I',
  LEU: 'L',
  LYS: 'K',
  MET: 'M',
  PHE: 'F',
  PRO: 'P',
  SER: 'S',
  THR: 'T',
  TRP: 'W',
  TYR: 'Y',
  VAL: 'V',
  SEC: 'U',
  PYL: 'O',
}

interface ViewCell {
  key: string
  seqId: number
  flat: number
  letter: string
  /** Displayed next to the cell: repeats within a chain read `42*`. */
  num: string
  title: string
  het: boolean
  ss: '' | 'H' | 'E'
}

interface ViewRow {
  num: string
  cells: ViewCell[]
  /** gaps[i] marks a numbering break directly before cells[i]. */
  gaps: boolean[]
}

interface ViewChain {
  id: string
  label: string
  hasSS: boolean
  cells: ViewCell[]
  rows: ViewRow[]
  total: number
}

function isGap(before: ViewCell, after: ViewCell): boolean {
  // icode pairs repeat the same number and are contiguous; anything else
  // that is not n → n+1 is a numbering break the view marks with `·`.
  return after.seqId !== before.seqId && after.seqId !== before.seqId + 1
}

const chainBlocks = computed<ViewChain[]>(() =>
  props.chains.map((chain) => {
    const seen = new Set<number>()
    const cells: ViewCell[] = chain.residues.map((res, flat) => {
      const repeat = seen.has(res.seqId)
      seen.add(res.seqId)
      const shown = repeat ? `${res.seqId}*` : String(res.seqId)
      return {
        key: `${chain.id}:${res.seqId}`,
        seqId: res.seqId,
        flat,
        letter: ONE_LETTER[res.name] ?? 'X',
        num: shown,
        title: t('molecules.sequence.hoverTip', {
          chain: chain.id,
          seqId: shown,
          name: res.name,
        }),
        het: res.het,
        ss: res.ss === 'H' || res.ss === 'E' ? res.ss : '',
      }
    })
    const rows: ViewRow[] = []
    for (let start = 0; start < cells.length; start += ROW_SIZE) {
      const slice = cells.slice(start, start + ROW_SIZE)
      rows.push({
        num: slice[0]!.num,
        cells: slice,
        gaps: slice.map((cell, i) => i > 0 && isGap(slice[i - 1]!, cell)),
      })
    }
    return {
      id: chain.id,
      label: t('molecules.sequence.chainLabel', { id: chain.id, n: chain.residues.length }),
      hasSS: cells.some((c) => c.ss !== ''),
      cells,
      rows,
      total: chain.residues.length,
    }
  }),
)

const chainById = (id: string): ViewChain | undefined => chainBlocks.value.find((c) => c.id === id)

// -- per-chain pagination ---------------------------------------------------

const visibleRowCounts = ref<Record<string, number>>({})

function visibleRows(chain: ViewChain): ViewRow[] {
  return chain.rows.slice(0, visibleRowCounts.value[chain.id] ?? INITIAL_ROWS)
}

function hasMore(chain: ViewChain): boolean {
  return chain.rows.length > (visibleRowCounts.value[chain.id] ?? INITIAL_ROWS)
}

function showMore(chain: ViewChain): void {
  visibleRowCounts.value[chain.id] = (visibleRowCounts.value[chain.id] ?? INITIAL_ROWS) + PAGE_ROWS
}

// -- selection / focus / drag state ----------------------------------------

const focusIndex = ref<Record<string, number>>({})
const cellEls = new Map<string, HTMLElement>()

const dragging = ref<{ chainId: string; anchor: number; current: number } | null>(null)
const shiftAnchor = ref<string | null>(null)
let shiftSession = false
/** A committed band drag swallows the click the mouseup would otherwise fire. */
let suppressClick = false

function setCellRef(refKey: string, el: unknown): void {
  if (el instanceof HTMLElement) cellEls.set(refKey, el)
  else cellEls.delete(refKey)
}

function focusCell(chain: ViewChain, flat: number): void {
  focusIndex.value[chain.id] = flat
  cellEls.get(`${chain.id}:${flat}`)?.focus()
}

const isSelected = (key: string): boolean => props.selected.has(key)

/** Row-major interval preview while a band drag is in progress. */
const previewKeys = computed<Set<string>>(() => {
  const drag = dragging.value
  if (!drag) return new Set()
  const chain = chainById(drag.chainId)
  if (!chain) return new Set()
  const lo = Math.min(drag.anchor, drag.current)
  const hi = Math.max(drag.anchor, drag.current)
  return new Set(chain.cells.slice(lo, hi + 1).map((c) => c.key))
})

function cellClasses(cell: ViewCell): Record<string, boolean> {
  const selected = !cell.het && isSelected(cell.key)
  return {
    'is-selected': selected,
    'is-het': cell.het,
    'is-helix': cell.ss === 'H',
    'is-sheet': cell.ss === 'E',
    'is-contact': !selected && (props.contactResidues?.has(cell.key) ?? false),
    'is-preview': !selected && previewKeys.value.has(cell.key),
  }
}

function onCellClick(event: MouseEvent, cell: ViewCell): void {
  if (suppressClick) {
    suppressClick = false
    return
  }
  if (props.readonly || cell.het) return
  if (event.shiftKey && shiftAnchor.value) {
    emit('toggleRange', shiftAnchor.value, cell.key)
  } else {
    emit('toggle', cell.key)
  }
  shiftAnchor.value = cell.key
  shiftSession = false
}

function onCellMousedown(event: MouseEvent, cell: ViewCell, chain: ViewChain): void {
  if (props.readonly || cell.het || event.button !== 0) return
  suppressClick = false
  dragging.value = { chainId: chain.id, anchor: cell.flat, current: cell.flat }
  shiftAnchor.value = cell.key
  shiftSession = false
}

function onCellEnter(cell: ViewCell, chain: ViewChain): void {
  if (!cell.het) emit('hover', cell.key)
  const drag = dragging.value
  // A band only extends through its own chain; other chains are ignored
  // and the interval is clipped to where the drag actually travelled.
  if (drag && drag.chainId === chain.id && drag.current !== cell.flat) {
    drag.current = cell.flat
  }
}

function onRootMouseup(): void {
  const drag = dragging.value
  if (!drag) return
  dragging.value = null
  const chain = chainById(drag.chainId)
  if (!chain || drag.current === drag.anchor) return
  emit('toggleRange', chain.cells[drag.anchor]!.key, chain.cells[drag.current]!.key)
  suppressClick = true
}

function onRootMouseleave(): void {
  // Leaving the component mid-drag cancels the band without committing.
  dragging.value = null
  emit('hover', null)
}

const ARROW_DELTA: Record<string, number> = {
  ArrowLeft: -1,
  ArrowRight: 1,
  ArrowUp: -ROW_SIZE,
  ArrowDown: ROW_SIZE,
}

function onCellKeydown(event: KeyboardEvent, cell: ViewCell, chain: ViewChain): void {
  const delta = ARROW_DELTA[event.key]
  if (delta === undefined) return
  event.preventDefault()
  const target = Math.min(Math.max(cell.flat + delta, 0), chain.cells.length - 1)
  if (target !== cell.flat && event.shiftKey && !props.readonly) {
    if (!shiftSession || !shiftAnchor.value) {
      shiftAnchor.value = cell.key
      shiftSession = true
    }
    emit('toggleRange', shiftAnchor.value, chain.cells[target]!.key)
  } else if (!event.shiftKey) {
    shiftSession = false
  }
  focusCell(chain, target)
}
</script>

<template>
  <div class="sequence-view" @mouseleave="onRootMouseleave" @mouseup="onRootMouseup">
    <p v-if="chainBlocks.length === 0" class="sequence-view__missing">
      {{ t('molecules.sequence.missing') }}
    </p>
    <section v-for="chain in chainBlocks" :key="chain.id" class="sequence-view__chain">
      <div class="sequence-view__head">
        <span class="sequence-view__label">{{ chain.label }}</span>
        <span v-if="chain.hasSS" class="sequence-view__legend">
          <span class="sequence-view__legend-item">
            <span class="sequence-view__swatch sequence-view__swatch--helix" />
            {{ t('molecules.sequence.ssHelix') }}
          </span>
          <span class="sequence-view__legend-item">
            <span class="sequence-view__swatch sequence-view__swatch--sheet" />
            {{ t('molecules.sequence.ssSheet') }}
          </span>
        </span>
      </div>
      <div class="sequence-view__rows" :class="{ 'is-dragging': dragging }">
        <div v-for="(row, ri) in visibleRows(chain)" :key="ri" class="sequence-view__row">
          <span class="sequence-view__rownum">{{ row.num }}</span>
          <template v-for="(cell, ci) in row.cells" :key="cell.flat">
            <span
              v-if="ci > 0 && row.gaps[ci]"
              class="sequence-view__gap"
              :title="t('molecules.sequence.gap')"
              >·</span
            >
            <button
              type="button"
              class="sequence-view__cell"
              :class="cellClasses(cell)"
              :ref="(el) => setCellRef(`${chain.id}:${cell.flat}`, el)"
              :tabindex="(focusIndex[chain.id] ?? 0) === cell.flat ? 0 : -1"
              :title="cell.title"
              :aria-label="cell.title"
              :aria-pressed="!cell.het && isSelected(cell.key)"
              :disabled="cell.het"
              @click="onCellClick($event, cell)"
              @mousedown="onCellMousedown($event, cell, chain)"
              @mouseenter="onCellEnter(cell, chain)"
              @mouseleave="emit('hover', null)"
              @focus="focusIndex[chain.id] = cell.flat"
              @keydown="onCellKeydown($event, cell, chain)"
              >{{ cell.letter }}</button
            >
          </template>
        </div>
      </div>
      <el-button
        v-if="hasMore(chain)"
        class="sequence-view__more"
        size="small"
        quaternary
        @click="showMore(chain)"
        >{{ t('molecules.sequence.moreRows') }}</el-button
      >
    </section>
  </div>
</template>

<style scoped>
.sequence-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: auto;
}

.sequence-view__missing {
  margin: 0;
  color: var(--vs-text-faint);
  font-size: 13px;
}

.sequence-view__chain {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sequence-view__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.sequence-view__label {
  font-size: 13px;
  font-weight: 600;
}

.sequence-view__legend {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--vs-text-faint);
}

.sequence-view__legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.sequence-view__swatch {
  width: 10px;
  height: 10px;
  border-radius: 2px;
}

.sequence-view__swatch--helix {
  background: color-mix(in srgb, var(--vs-info) 16%, transparent);
}

.sequence-view__swatch--sheet {
  background: color-mix(in srgb, var(--vs-accent) 14%, transparent);
}

.sequence-view__rows {
  line-height: 0;
}

.sequence-view__rows.is-dragging {
  user-select: none;
}

.sequence-view__row {
  display: flex;
  align-items: center;
}

.sequence-view__rownum {
  flex: 0 0 32px;
  width: 32px;
  color: var(--vs-text-faint);
  font-family: var(--vs-font-mono);
  font-size: 12px;
  line-height: 24px;
}

.sequence-view__gap {
  flex: 0 0 auto;
  width: 12px;
  text-align: center;
  color: var(--vs-text-faint);
  line-height: 24px;
  user-select: none;
}

.sequence-view__cell {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 24px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--vs-text);
  font-family: var(--vs-font-mono);
  font-size: 12px;
  line-height: 1;
}

.sequence-view__cell:hover:not(:disabled) {
  background: var(--vs-border);
  cursor: pointer;
}

.sequence-view__cell.is-het {
  color: var(--vs-text-faint);
}

.sequence-view__cell.is-helix {
  background: color-mix(in srgb, var(--vs-info) 16%, transparent);
}

.sequence-view__cell.is-sheet {
  background: color-mix(in srgb, var(--vs-accent) 14%, transparent);
}

.sequence-view__cell.is-contact {
  box-shadow: inset 0 -2px 0 var(--vs-warning);
}

.sequence-view__cell.is-selected,
.sequence-view__cell.is-selected:hover:not(:disabled) {
  background: var(--vs-accent-soft);
  box-shadow: inset 0 -2px 0 var(--vs-accent);
  color: var(--vs-text);
}

.sequence-view__cell.is-preview,
.sequence-view__cell.is-preview:hover:not(:disabled) {
  background: var(--vs-accent-soft);
  box-shadow: inset 0 -2px 0 var(--vs-accent);
  outline: 1px dashed var(--vs-accent);
  color: var(--vs-text);
}

.sequence-view__more {
  align-self: flex-start;
}
</style>
