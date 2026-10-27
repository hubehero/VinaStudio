<script setup lang="ts">
import { ElButton, ElDialog, ElInput, ElInputNumber, ElMessage, ElSwitch } from 'element-plus'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '@/api/http'
import SequenceView from '@/components/panels/SequenceView.vue'
import { useCatalogStore } from '@/stores/catalog'
import { DEFAULT_LIGAND_OPTIONS, defaultReceptorOptions } from '@/stores/preparation-shared'
import type { CatalogMolecule, LigandOptions, ReceptorOptions, ReceptorSequence } from '@/types/api'

const props = defineProps<{
  modelValue: boolean
  molecule: CatalogMolecule | null
}>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  prepared: []
}>()

const { t } = useI18n()
const store = useCatalogStore()
const busy = ref(false)
const receptor = ref<ReceptorOptions>({ ...defaultReceptorOptions(), keepResidues: [] })
const ligand = ref<LigandOptions>({ ...DEFAULT_LIGAND_OPTIONS })
const keepText = ref('')
const flexibleText = ref('')
const sequence = ref<ReceptorSequence | null>(null)
const sequenceLoading = ref(false)

const open = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})
const isReceptor = computed(() => props.molecule?.kindHint === 'receptor')

watch(
  () => props.modelValue,
  (value) => {
    if (!value) return
    receptor.value = { ...defaultReceptorOptions(), keepResidues: [] }
    ligand.value = { ...DEFAULT_LIGAND_OPTIONS }
    keepText.value = ''
    flexibleText.value = ''
    sequence.value = null
    void loadSequence()
  },
)

const selectedResidues = computed(() => new Set(receptor.value.flexibleResidues))

function toggleResidue(residue: string): void {
  const current = receptor.value.flexibleResidues
  receptor.value.flexibleResidues = current.includes(residue)
    ? current.filter((item) => item !== residue)
    : [...current, residue]
}

function toggleRange(from: string, to: string): void {
  const flat: string[] = []
  for (const chain of sequence.value?.chains ?? []) {
    for (const residue of chain.residues) {
      if (!residue.het) flat.push(`${chain.id}:${residue.seqId}`)
    }
  }
  const start = flat.indexOf(from)
  const end = flat.indexOf(to)
  if (start < 0 || end < 0) return
  const next = new Set(receptor.value.flexibleResidues)
  for (let i = Math.min(start, end); i <= Math.max(start, end); i += 1) {
    const key = flat[i]
    if (key) next.add(key)
  }
  receptor.value.flexibleResidues = [...next]
}

async function loadSequence(): Promise<void> {
  const source = props.molecule?.files.find((file) => file.kind === 'source')?.path
  if (!source || props.molecule?.kindHint !== 'receptor') return
  sequenceLoading.value = true
  try {
    const preview = await api.inspectReceptor(source)
    sequence.value = preview.sequence ?? null
  } catch {
    sequence.value = null
  } finally {
    sequenceLoading.value = false
  }
}

function parseResidues(value: string): string[] {
  return [...new Set(value.split(/[,;\s]+/).map((item) => item.trim()).filter(Boolean))]
}

async function run(): Promise<void> {
  const mol = props.molecule
  if (!mol || busy.value) return
  busy.value = true
  try {
    const receptorOptions = isReceptor.value
      ? {
          ...receptor.value,
          keepResidues: parseResidues(keepText.value),
          flexibleResidues: [
            ...new Set([
              ...receptor.value.flexibleResidues,
              ...parseResidues(flexibleText.value),
            ]),
          ],
        }
      : undefined
    const ligandOptions = isReceptor.value ? undefined : { ...ligand.value }
    await store.prepareMolecule(mol.id, { receptorOptions, ligandOptions })
    ElMessage.success(t('catalog.prepared'))
    emit('prepared')
    open.value = false
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : t('catalog.prepareFailed'))
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <ElDialog v-model="open" :title="t('molecules.options')" width="520px" :close-on-click-modal="false">
    <div v-if="molecule" class="prepare-options">
      <p class="prepare-options__hint">{{ t('catalog.prepareOptionsHint') }}</p>

      <template v-if="isReceptor">
        <label class="prepare-options__row">
          <span>{{ t('molecules.optionWaters') }}</span>
          <ElSwitch v-model="receptor.deleteWaters" size="small" />
        </label>
        <label class="prepare-options__row">
          <span>{{ t('molecules.optionHetero') }}</span>
          <ElSwitch v-model="receptor.deleteHetero" size="small" />
        </label>
        <label class="prepare-options__row">
          <span>{{ t('molecules.optionNormalise') }}</span>
          <ElSwitch v-model="receptor.normaliseAtomOrder" size="small" />
        </label>
        <label class="prepare-options__row">
          <span>{{ t('molecules.optionAllowBad') }}</span>
          <ElSwitch v-model="receptor.allowBadResidues" size="small" />
        </label>
        <label class="prepare-options__row prepare-options__row--stack">
          <span>{{ t('molecules.optionKeep') }}</span>
          <ElInput v-model="keepText" size="small" :placeholder="t('molecules.optionKeepPlaceholder')" />
        </label>
        <label class="prepare-options__row prepare-options__row--stack">
          <span>{{ t('molecules.flexibleResidues') }}</span>
          <ElInput v-model="flexibleText" size="small" :placeholder="t('catalog.flexibleResiduesPlaceholder')" />
        </label>
        <div v-if="sequenceLoading" class="vs-faint">{{ t('common.loading') }}</div>
        <SequenceView
          v-else-if="sequence"
          :chains="sequence.chains"
          :selected="selectedResidues"
          @toggle="toggleResidue"
          @toggle-range="toggleRange"
        />
      </template>

      <template v-else>
        <label class="prepare-options__row">
          <span>{{ t('molecules.optionOptimise') }}</span>
          <ElSwitch v-model="ligand.optimiseGeometry" size="small" />
        </label>
        <label class="prepare-options__row">
          <span>{{ t('molecules.optionAmides') }}</span>
          <ElSwitch v-model="ligand.flexibleAmides" size="small" />
        </label>
        <label class="prepare-options__row">
          <span>{{ t('molecules.optionMacrocycles') }}</span>
          <ElSwitch v-model="ligand.rigidMacrocycles" size="small" />
        </label>
        <label class="prepare-options__row">
          <span>{{ t('molecules.optionHydrate') }}</span>
          <ElSwitch v-model="ligand.hydrate" size="small" />
        </label>
        <label class="prepare-options__row">
          <span>{{ t('molecules.optionSeed') }}</span>
          <ElInputNumber v-model="ligand.embedSeed" :min="0" :max="2147483647" size="small" />
        </label>
      </template>
    </div>

    <template #footer>
      <ElButton @click="open = false">{{ t('common.cancel') }}</ElButton>
      <ElButton type="primary" :loading="busy" @click="run">{{ t('catalog.prepare') }}</ElButton>
    </template>
  </ElDialog>
</template>

<style scoped>
.prepare-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.prepare-options__hint {
  margin: 0 0 4px;
  color: var(--vs-text-faint);
  font-size: 12px;
  line-height: 1.5;
}
.prepare-options__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 12.5px;
}
.prepare-options__row--stack {
  align-items: flex-start;
  flex-direction: column;
  gap: 4px;
}
.prepare-options__row :deep(.el-input),
.prepare-options__row :deep(.el-input-number) {
  width: 180px;
}
.prepare-options__row--stack :deep(.el-input) {
  width: 100%;
}
</style>
