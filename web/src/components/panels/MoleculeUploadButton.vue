<script setup lang="ts">
import { ArrowDown, FolderOpened, Search, Upload } from '@element-plus/icons-vue'
import { ElDropdown, ElDropdownItem, ElDropdownMenu, ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { isDesktopHost, pickFileForUpload, pickFiles } from '@/api/bridge'
import { useMoleculeStore } from '@/stores/molecules'
import type { LoadOutcome } from '@/stores/molecules'
import type { SampleFile } from '@/types/api'

import MoleculeLibraryDialog from './MoleculeLibraryDialog.vue'

const store = useMoleculeStore()
const { t } = useI18n()
const busy = ref(false)
const desktop = ref(false)
const libraryDialog = ref<InstanceType<typeof MoleculeLibraryDialog> | null>(null)

onMounted(() => {
  desktop.value = isDesktopHost()
  if (!store.filters) {
    void store.loadReferenceData()
  }
})

const accept = computed(() => {
  const f = store.filters
  if (!f) return []
  return [...new Set([...f.ligandSuffixes, ...f.receptorSuffixes])].map((s) => s.toLowerCase())
})

/** One message for the whole batch, rather than one per file. */
function report(outcome: LoadOutcome): void {
  if (outcome.failed > 0) {
    ElMessage.error(t('molecules.loadFailed', { n: outcome.failed }))
  } else if (outcome.added > 0) {
    ElMessage.success(t('molecules.loadDone', { n: outcome.added }))
  }
}

async function choose(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    if (desktop.value) {
      const combined = store.filters
        ? `${store.filters.ligand};;${store.filters.receptor}`
        : ''
      const paths = await pickFiles({ title: t('molecules.uploadTitle'), filters: combined })
      // An empty result means the dialog was dismissed; do not open a second one.
      if (paths.length === 0) return
      report(await store.loadPaths(paths))
      return
    }

    const files = await pickFileForUpload(accept.value, true)
    if (files.length === 0) return
    report(await store.loadFiles(files))
  } catch (error) {
    ElMessage.error(
      `${t('molecules.uploadFailed')}: ${error instanceof Error ? error.message : String(error)}`,
    )
  } finally {
    busy.value = false
  }
}

async function chooseSample(sample: SampleFile): Promise<void> {
  await store.loadSample(sample)
}

const samples = computed(() => store.samples)
</script>

<template>
  <div class="load-actions">
    <div class="load-actions__row">
      <el-button
        type="primary"
        size="default"
        :icon="desktop ? FolderOpened : Upload"
        :loading="busy"
        class="load-actions__choose"
        data-test="molecule-upload"
        @click="choose"
      >
        {{ t('molecules.upload') }}
      </el-button>

      <el-button
        size="default"
        :icon="Search"
        :title="t('library.buttonHint')"
        @click="libraryDialog?.open()"
      >
        {{ t('library.button') }}
      </el-button>

      <el-dropdown v-if="samples.length > 0" trigger="click" @command="chooseSample">
        <el-button size="default" :icon="ArrowDown" :title="t('molecules.sampleHint')">
          {{ t('molecules.samples') }}
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item
              v-for="sample in samples"
              :key="sample.path"
              :command="sample"
              :title="sample.description"
            >
              <span class="load-actions__sample-name">{{ sample.name }}</span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <MoleculeLibraryDialog ref="libraryDialog" />

    <p class="load-actions__hint">
      {{ desktop ? t('molecules.desktopHint') : t('molecules.browserHint') }}
      <span class="load-actions__formats">{{ t('molecules.formatsHint') }}</span>
    </p>
  </div>
</template>

<style scoped>
.load-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.load-actions__row {
  display: flex;
  gap: 6px;
}

.load-actions__choose {
  flex: 1;
}

.load-actions__sample-name {
  font-family: var(--vs-font-mono);
  font-size: 12px;
}

.load-actions__hint {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--vs-text-faint);
}

.load-actions__formats {
  display: block;
  font-family: var(--vs-font-mono);
  font-size: 10.5px;
}
</style>
