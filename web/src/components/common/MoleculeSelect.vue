<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useMoleculeStore } from '@/stores/molecules'
import type { MoleculeItem } from '@/types/molecule'

/**
 * Pick the molecule a downstream step acts on.
 *
 * Only usable molecules are offered — ones still preparing belong to the
 * molecule manager — and the empty state links straight there.
 */
const props = defineProps<{ kind: 'receptor' | 'ligand'; disabled?: boolean }>()

const store = useMoleculeStore()
const { t } = useI18n()

const options = computed<MoleculeItem[]>(() =>
  props.kind === 'receptor' ? store.usableReceptors : store.usableLigands,
)

/** The effective pick: the explicit choice while it still counts, else the fallback. */
const selectedId = computed({
  get: () =>
    (props.kind === 'receptor' ? store.pipelineReceptor?.id : store.pipelineLigand?.id) ?? '',
  set: (id: string) => {
    if (props.kind === 'receptor') {
      store.setPipelineReceptor(id)
    } else {
      store.setPipelineLigand(id)
    }
  },
})
</script>

<template>
  <el-select
    v-if="options.length > 0"
    v-model="selectedId"
    :disabled="disabled"
    :placeholder="kind === 'receptor' ? t('molecules.pickReceptor') : t('molecules.pickLigand')"
    size="small"
    class="mol-select"
  >
    <el-option v-for="mol in options" :key="mol.id" :value="mol.id" :label="mol.name" />
  </el-select>
  <span v-else class="mol-select__empty">
    {{ t('molecules.noUsable') }}
    <router-link to="/molecules">{{ t('nav.molecules') }}</router-link>
  </span>
</template>

<style scoped>
.mol-select {
  width: 100%;
}

.mol-select__empty {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--vs-text-faint);
}
</style>
