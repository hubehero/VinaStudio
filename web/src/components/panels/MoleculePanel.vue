<script setup lang="ts">
import { Delete, Document, Search, Upload } from '@element-plus/icons-vue'
import { ElInput, ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { useMoleculeStore } from '@/stores/molecules'

import MoleculeListSection from './MoleculeListSection.vue'
import MoleculeUploadButton from './MoleculeUploadButton.vue'

const store = useMoleculeStore()
const { t } = useI18n()

const dragDepth = ref(0)
const dragOver = computed(() => dragDepth.value > 0)

/** Expanded group IDs in the grouped view. */
const expandedGroups = ref<Set<string>>(new Set())

onMounted(() => {
  if (!store.filters) {
    void store.loadReferenceData()
  }
  // Expand all groups by default
  for (const g of store.groupedMolecules) {
    if (g.receptor) expandedGroups.value.add(g.id)
  }
})

function handleSelect(id: string): void {
  store.setActive(id)
}

function handleRemove(id: string): void {
  store.removeItem(id)
}

async function handleClear(): Promise<void> {
  if (store.molecules.length === 0) return
  try {
    await ElMessageBox.confirm(t('molecules.clearConfirm'), {
      type: 'warning',
      confirmButtonText: t('molecules.clearAll'),
      cancelButtonText: t('common.cancel'),
    })
  } catch {
    return
  }
  store.clearAll()
}

function handleDragEnter(event: DragEvent): void {
  if (!event.dataTransfer?.types.includes('Files')) return
  dragDepth.value += 1
}

function handleDragLeave(): void {
  dragDepth.value = Math.max(0, dragDepth.value - 1)
}

async function handleDrop(event: DragEvent): Promise<void> {
  dragDepth.value = 0
  const files = event.dataTransfer?.files
  if (!files || files.length === 0) return
  const outcome = await store.loadFiles(Array.from(files))
  if (outcome.failed > 0) {
    ElMessage.warning(t('molecules.loadFailed', { n: outcome.failed }))
  }
}

function toggleGroup(id: string): void {
  if (expandedGroups.value.has(id)) {
    expandedGroups.value.delete(id)
  } else {
    expandedGroups.value.add(id)
  }
}

/** Molecules that belong to a group, shown in grouped view. */
const hasGroups = computed(() => store.groupedMolecules.some((g) => g.id !== '_ungrouped'))

/** Ungrouped molecules shown in the flat section view. */
const ungroupedReceptors = computed(() =>
  store.visibleReceptors.filter((m) => !m.groupId),
)
const ungroupedLigands = computed(() =>
  store.visibleLigands.filter((m) => !m.groupId),
)
const ungroupedUnknowns = computed(() =>
  store.visibleUnknowns.filter((m) => !m.groupId),
)
const ungroupedCount = computed(
  () => ungroupedReceptors.value.length + ungroupedLigands.value.length + ungroupedUnknowns.value.length,
)

const totalSize = computed(() => {
  const bytes = store.totalBytes
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
})

const nothingVisible = computed(
  () => store.molecules.length > 0 && store.visibleCount === 0,
)
</script>

<template>
  <div
    class="mol-panel"
    :class="{ 'mol-panel--drag': dragOver }"
    @dragenter.prevent="handleDragEnter"
    @dragover.prevent
    @dragleave="handleDragLeave"
    @drop.prevent="handleDrop"
  >
    <header class="mol-panel__head">
      <div class="mol-panel__heading">
        <h2 class="mol-panel__title">{{ t('molecules.panelTitle') }}</h2>
        <span v-if="store.molecules.length > 0" class="mol-panel__count">
          {{ t('molecules.fileCount', { n: store.molecules.length }) }}
        </span>
      </div>
      <button
        v-if="store.molecules.length > 0"
        type="button"
        class="mol-panel__clear"
        :title="t('molecules.clearAll')"
        @click="handleClear"
      >
        <el-icon :size="13"><Delete /></el-icon>
      </button>
    </header>

    <MoleculeUploadButton />

    <div v-if="store.molecules.length > 0" class="mol-panel__search">
      <ElInput
        v-model="store.query"
        size="small"
        clearable
        :prefix-icon="Search"
        :placeholder="t('molecules.search')"
      />
    </div>

    <div class="mol-panel__list">
      <!-- Grouped view: receptor + ligands per PDB entry -->
      <template v-if="hasGroups">
        <div
          v-for="group in store.groupedMolecules.filter((g) => g.id !== '_ungrouped')"
          :key="group.id"
          class="mol-group"
        >
          <div
            class="mol-group__header"
            @click="toggleGroup(group.id)"
          >
            <span class="mol-group__arrow">{{ expandedGroups.has(group.id) ? '▾' : '▸' }}</span>
            <span class="mol-group__icon">🧬</span>
            <span class="mol-group__name">{{ group.name || group.id }}</span>
            <span class="mol-group__count">{{ group.ligands.length + (group.receptor ? 1 : 0) }}</span>
          </div>
          <div v-if="expandedGroups.has(group.id)" class="mol-group__items">
            <MoleculeListSection
              v-if="group.receptor"
              :title="t('molecules.sectionReceptors')"
              :items="[group.receptor]"
              :active-id="store.activeId"
              @select="handleSelect"
              @remove="handleRemove"
            />
            <MoleculeListSection
              v-if="group.ligands.length > 0"
              :title="t('molecules.sectionLigands')"
              :items="group.ligands"
              :active-id="store.activeId"
              @select="handleSelect"
              @remove="handleRemove"
            />
          </div>
        </div>
      </template>

      <!-- Flat sections for ungrouped molecules -->
      <template v-if="ungroupedCount > 0">
        <div v-if="hasGroups" class="mol-panel__divider">
          <span>{{ t('molecules.sectionUnknowns') }}</span>
        </div>
        <MoleculeListSection
          :title="t('molecules.sectionReceptors')"
          :items="ungroupedReceptors"
          :active-id="store.activeId"
          @select="handleSelect"
          @remove="handleRemove"
        />
        <MoleculeListSection
          :title="t('molecules.sectionLigands')"
          :items="ungroupedLigands"
          :active-id="store.activeId"
          @select="handleSelect"
          @remove="handleRemove"
        />
        <MoleculeListSection
          :title="t('molecules.sectionUnknowns')"
          :items="ungroupedUnknowns"
          :active-id="store.activeId"
          @select="handleSelect"
          @remove="handleRemove"
        />
      </template>

      <div v-if="store.molecules.length === 0" class="mol-panel__empty">
        <el-icon :size="30" class="mol-panel__empty-icon"><Document /></el-icon>
        <p class="mol-panel__empty-title">{{ t('molecules.emptyTitle') }}</p>
        <p class="mol-panel__empty-hint">{{ t('molecules.emptyHint') }}</p>
        <p class="mol-panel__empty-formats">{{ t('molecules.formatsHint') }}</p>
      </div>

      <div v-else-if="nothingVisible" class="mol-panel__empty">
        <p class="mol-panel__empty-title">{{ t('molecules.noMatch') }}</p>
        <p class="mol-panel__empty-hint">{{ store.query }}</p>
      </div>
    </div>

    <footer v-if="store.molecules.length > 0" class="mol-panel__foot">
      <span>{{ t('molecules.sectionReceptors') }} {{ store.receptors.length }}</span>
      <span class="vs-sep">·</span>
      <span>{{ t('molecules.sectionLigands') }} {{ store.ligands.length }}</span>
      <span v-if="store.unknowns.length > 0">
        <span class="vs-sep">·</span>
        {{ t('molecules.sectionUnknowns') }} {{ store.unknowns.length }}
      </span>
      <span class="mol-panel__foot-size">{{ totalSize }}</span>
    </footer>

    <div v-if="dragOver" class="mol-panel__overlay" aria-hidden="true">
      <el-icon :size="30"><Upload /></el-icon>
      <span>{{ t('molecules.dropHere') }}</span>
    </div>
  </div>
</template>

<style scoped>
.mol-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  padding: 14px 14px 10px;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius-lg);
  background: var(--vs-bg-surface);
}

.mol-panel--drag {
  border-color: var(--vs-accent);
}

.mol-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}

.mol-panel__heading {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}

.mol-panel__title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--vs-text);
}

.mol-panel__count {
  font-size: 11.5px;
  color: var(--vs-text-faint);
  font-variant-numeric: tabular-nums;
}

.mol-panel__clear {
  flex: none;
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius-sm);
  background: none;
  color: var(--vs-text-muted);
  cursor: pointer;
}

.mol-panel__clear:hover {
  color: var(--vs-danger);
  border-color: var(--vs-danger);
}

.mol-panel__clear:focus-visible {
  outline: 2px solid var(--vs-accent);
  outline-offset: 1px;
}

.mol-panel__search {
  margin-top: 10px;
}

.mol-panel__list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  margin-top: 8px;
  padding-right: 2px;
  scrollbar-width: thin;
}

.mol-panel__empty {
  padding: 26px 14px;
  text-align: center;
}

.mol-panel__empty-icon {
  color: var(--vs-text-faint);
}

.mol-panel__empty-title {
  margin: 8px 0 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--vs-text-muted);
}

.mol-panel__empty-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--vs-text-faint);
}

.mol-panel__empty-formats {
  margin: 6px 0 0;
  font-family: var(--vs-font-mono);
  font-size: 10.5px;
  color: var(--vs-text-faint);
}

.mol-panel__foot {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--vs-border);
  font-size: 11px;
  color: var(--vs-text-faint);
}

.mol-panel__foot-size {
  margin-left: auto;
  font-family: var(--vs-font-mono);
}

.mol-panel__overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: color-mix(in srgb, var(--vs-accent) 10%, var(--vs-bg-surface));
  border: 2px dashed var(--vs-accent);
  border-radius: var(--vs-radius-lg);
  color: var(--vs-accent);
  font-size: 13px;
  font-weight: 600;
  pointer-events: none;
}

/* -- Grouped view ----------------------------------------------------------- */

.mol-group {
  margin-bottom: 4px;
}

.mol-group__header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 6px;
  border-radius: var(--vs-radius-sm);
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  color: var(--vs-text);
  user-select: none;
}

.mol-group__header:hover {
  background: var(--vs-bg-elevated);
}

.mol-group__arrow {
  font-size: 10px;
  color: var(--vs-text-faint);
  width: 10px;
}

.mol-group__icon {
  font-size: 13px;
}

.mol-group__name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mol-group__count {
  font-size: 10px;
  font-weight: 500;
  color: var(--vs-text-faint);
  background: var(--vs-bg-elevated);
  padding: 1px 5px;
  border-radius: 8px;
}

.mol-group__items {
  padding-left: 12px;
}

.mol-panel__divider {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0 4px;
  font-size: 10px;
  font-weight: 600;
  color: var(--vs-text-faint);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.mol-panel__divider::before,
.mol-panel__divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--vs-border);
}
</style>
