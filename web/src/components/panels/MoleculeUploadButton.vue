<script setup lang="ts">
import { ArrowDown, EditPen, FolderOpened, Search, Upload } from '@element-plus/icons-vue'
import {
  ElButton,
  ElDialog,
  ElDropdown,
  ElDropdownItem,
  ElDropdownMenu,
  ElInput,
  ElMessage,
} from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { isDesktopHost, pickFileForUpload, pickFiles } from '@/api/bridge'
import { useMoleculeStore } from '@/stores/molecules'
import type { LoadOutcome } from '@/stores/molecules'
import type { SampleFile } from '@/types/api'

import MoleculeLibraryDialog from './MoleculeLibraryDialog.vue'
import SketcherDialog from '../sketcher/SketcherDialog.vue'

const store = useMoleculeStore()
const { t } = useI18n()
const busy = ref(false)
const desktop = ref(false)
const libraryDialog = ref<InstanceType<typeof MoleculeLibraryDialog> | null>(null)
const sketcherDialog = ref<InstanceType<typeof SketcherDialog> | null>(null)

// -- SMILES paste dialog ----------------------------------------------------
const smilesVisible = ref(false)
const smilesText = ref('')
const smilesName = ref('')
const smilesBusy = ref(false)

function openSmiles(): void {
  smilesText.value = ''
  smilesName.value = ''
  smilesVisible.value = true
}

const smilesLineCount = computed(
  () =>
    smilesText.value
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean).length,
)

async function submitSmiles(): Promise<void> {
  if (smilesBusy.value) return
  const text = smilesText.value
  const hasLine = text.split(/\r?\n/).some((line) => line.trim())
  if (!hasLine) {
    ElMessage.warning(t('molecules.smilesEmpty'))
    return
  }
  smilesBusy.value = true
  try {
    const outcome: LoadOutcome = await store.loadFromSmiles(text, smilesName.value)
    if (outcome.added > 0) {
      ElMessage.success(t('molecules.smilesDone', { n: outcome.added }))
      smilesVisible.value = false
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : String(error))
  } finally {
    smilesBusy.value = false
  }
}

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
    // Check at call time, not at mount time: the QWebChannel handshake may
    // complete after the component mounts, so a cached `desktop` ref can be
    // stale and silently route the upload through the browser fallback.
    if (isDesktopHost()) {
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
        size="small"
        :icon="desktop ? FolderOpened : Upload"
        :loading="busy"
        class="load-actions__choose"
        data-test="molecule-upload"
        @click="choose"
      >
        {{ t('molecules.upload') }}
      </el-button>

      <el-button
        size="small"
        data-test="molecule-smiles"
        :title="t('molecules.smilesTitle')"
        @click="openSmiles"
      >
        {{ t('molecules.smilesButton') }}
      </el-button>

      <el-button
        size="small"
        :icon="EditPen"
        data-test="molecule-draw"
        :title="t('molecules.drawTitle')"
        @click="sketcherDialog?.open()"
      >
        {{ t('molecules.drawButton') }}
      </el-button>

      <el-button
        size="small"
        :icon="Search"
        :title="t('library.buttonHint')"
        @click="libraryDialog?.open()"
      >
        {{ t('library.button') }}
      </el-button>

      <el-dropdown v-if="samples.length > 0" trigger="click" @command="chooseSample">
        <el-button size="small" :icon="ArrowDown" :title="t('molecules.sampleHint')">
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

    <SketcherDialog ref="sketcherDialog" />

    <ElDialog
      v-model="smilesVisible"
      :title="t('molecules.smilesTitle')"
      width="480px"
      class="smiles-dialog"
    >
      <div class="smiles-dialog__body">
        <ElInput
          v-model="smilesText"
          type="textarea"
          :rows="6"
          :placeholder="t('molecules.smilesPlaceholder')"
          data-test="smiles-input"
        />
        <ElInput
          v-if="smilesLineCount <= 1"
          v-model="smilesName"
          :placeholder="t('molecules.smilesName')"
          data-test="smiles-name"
        />
        <p class="smiles-dialog__hint">{{ t('molecules.smilesHint') }}</p>
      </div>
      <template #footer>
        <ElButton @click="smilesVisible = false">{{ t('common.cancel') }}</ElButton>
        <ElButton
          type="primary"
          :loading="smilesBusy"
          data-test="smiles-submit"
          @click="submitSmiles"
        >
          {{ t('molecules.smilesSubmit') }}
        </ElButton>
      </template>
    </ElDialog>

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
  /* The panel column can be as narrow as ~290px; buttons are nowrap, so
     wrapping is the only way the row stays inside the card border. */
  flex-wrap: wrap;
  gap: 6px;
}

/* Element Plus stacks adjacent buttons with a fixed 12px margin; the row gap
   is the single source of spacing here (same 6px as every other action row). */
.load-actions__row .el-button + .el-button {
  margin-left: 0;
}

/* The primary CTA owns its own full-width line; secondaries share line two. */
.load-actions__choose {
  flex: 1 1 100%;
}

.load-actions__row > .el-button:not(.load-actions__choose),
.load-actions__row > .el-dropdown {
  flex: 1 1 auto;
}

.load-actions__row > .el-dropdown {
  display: flex;
}

.load-actions__row > .el-dropdown .el-button {
  width: 100%;
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

.smiles-dialog__body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.smiles-dialog__hint {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--vs-text-faint);
}
</style>
