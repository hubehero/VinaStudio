<script setup lang="ts">
import { Delete, Upload } from '@element-plus/icons-vue'
import { ElAlert, ElButton, ElInput, ElTable, ElTableColumn } from 'element-plus'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api/http'
import { isDesktopHost, pickFileForUpload, pickFiles } from '@/api/bridge'
import { useScreeningStore } from '@/stores/screening'
import type { LibraryImportResult } from '@/types/api'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  /** Fires on close after a successful import — the view reloads the list. */
  (e: 'imported', name: string): void
}>()

const { t } = useI18n()
const screening = useScreeningStore()

const name = ref('')
const paths = ref<string[]>([])
const files = ref<File[]>([])
const submitting = ref(false)
/** Result panel state; null = still on the form. */
const result = ref<LibraryImportResult | null>(null)
/** Form-panel error: duplicate-name 409 gets its own key, others keep detail. */
const duplicate = ref(false)
const formError = ref<string | null>(null)

const hasFiles = computed(() => paths.value.length > 0 || files.value.length > 0)
const canSubmit = computed(() => name.value.trim().length > 0 && hasFiles.value && !submitting.value)

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    name.value = ''
    paths.value = []
    files.value = []
    submitting.value = false
    result.value = null
    duplicate.value = false
    formError.value = null
  },
)

/** One button, two origins — the molecules loadPaths/loadFiles pattern. */
async function pick(): Promise<void> {
  if (isDesktopHost()) {
    const picked = await pickFiles({ title: t('screening.importPick'), filters: 'SDF (*.sdf)' })
    if (picked.length === 0) return
    paths.value = [...paths.value, ...picked]
    return
  }
  const picked = await pickFileForUpload(['.sdf'], true)
  if (picked.length === 0) return
  files.value = [...files.value, ...picked]
}

function dropPath(path: string): void {
  paths.value = paths.value.filter((p) => p !== path)
}

function dropFile(file: File): void {
  files.value = files.value.filter((f) => f !== file)
}

function baseName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path
}

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  duplicate.value = false
  formError.value = null
  submitting.value = true
  try {
    const form = new FormData()
    form.append('name', name.value.trim())
    if (paths.value.length > 0) {
      form.append('paths', JSON.stringify(paths.value))
    }
    for (const file of files.value) {
      form.append('files', file)
    }
    // Success switches to the result panel — the form stays until 完成.
    result.value = await screening.importLibrary(form)
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) {
      duplicate.value = true
    } else {
      formError.value = error instanceof Error ? error.message : String(error)
    }
  } finally {
    submitting.value = false
  }
}

function close(): void {
  const importedName = result.value?.name ?? null
  if (importedName !== null) {
    emit('imported', importedName)
  }
  emit('update:modelValue', false)
}

function reasonText(reason: 'parse' | 'too_large' | 'cap' | 'write'): string {
  const key =
    reason === 'parse'
      ? 'reasonParse'
      : reason === 'too_large'
        ? 'reasonTooLarge'
        : reason === 'cap'
          ? 'reasonCap'
          : 'reasonWrite'
  return t(`screening.${key}`)
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="t('screening.importTitle')"
    width="480px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <!-- Form state -->
    <div v-if="result === null" class="imp-form">
      <div class="imp-field">
        <label class="imp-label">{{ t('screening.libraryName') }}</label>
        <el-input v-model="name" :placeholder="t('screening.namePlaceholder')" size="small" />
        <div v-if="name.trim().length === 0" class="imp-hint imp-hint--warn">
          {{ t('screening.importNoName') }}
        </div>
      </div>

      <div class="imp-field">
        <label class="imp-label">{{ t('screening.importPick') }}</label>
        <el-button size="small" :icon="Upload" @click="pick">
          {{ t('screening.importPick') }}
        </el-button>
        <ul v-if="hasFiles" class="imp-list">
          <li v-for="path in paths" :key="path" class="imp-list__item">
            <span class="imp-list__name">{{ baseName(path) }}</span>
            <el-button text size="small" :icon="Delete" @click="dropPath(path)" />
          </li>
          <li v-for="file in files" :key="file.name" class="imp-list__item">
            <span class="imp-list__name">{{ file.name }}</span>
            <el-button text size="small" :icon="Delete" @click="dropFile(file)" />
          </li>
        </ul>
        <div class="imp-hint">{{ t('screening.importHint') }}</div>
      </div>

      <el-alert
        v-if="duplicate"
        type="error"
        :closable="false"
        show-icon
        :title="t('screening.duplicateName')"
      />
      <el-alert
        v-else-if="formError !== null"
        type="error"
        :closable="false"
        show-icon
        :title="t('screening.importRetryTitle')"
        :description="formError"
      />
    </div>

    <!-- Result state (including a 0-import run: same panel, error tint) -->
    <div v-else class="imp-result">
      <el-alert
        :type="result.imported > 0 ? (result.failedCount > 0 ? 'warning' : 'success') : 'error'"
        :closable="false"
        show-icon
        :title="t('screening.importDone', { n: result.imported })"
        :description="result.failedCount > 0 ? t('screening.importPartial', { n: result.failedCount }) : undefined"
      />
      <template v-if="result.failed.length > 0">
        <div class="imp-listtitle">{{ t('screening.importFailedTitle') }}</div>
        <ElTable :data="result.failed" size="small" max-height="200">
          <ElTableColumn prop="index" :label="t('screening.colIndex')" width="60" />
          <ElTableColumn prop="name" :label="t('screening.colName')" min-width="140" />
          <ElTableColumn :label="t('screening.colReason')" width="140">
            <template #default="{ row }">
              {{ reasonText(row.reason) }}
            </template>
          </ElTableColumn>
        </ElTable>
      </template>
    </div>

    <template #footer>
      <ElButton v-if="result === null" @click="emit('update:modelValue', false)">
        {{ t('common.cancel') }}
      </ElButton>
      <ElButton
        v-if="result === null"
        type="primary"
        :loading="submitting"
        :disabled="!canSubmit"
        @click="submit"
      >
        {{ submitting ? t('screening.importing') : t('screening.importSubmit') }}
      </ElButton>
      <ElButton v-else type="primary" @click="close">
        {{ t('screening.close') }}
      </ElButton>
    </template>
  </el-dialog>
</template>

<style scoped>
.imp-form,
.imp-result {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.imp-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.imp-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--vs-text);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.imp-hint {
  font-size: 11px;
  color: var(--vs-text-faint);
  line-height: 1.4;
}

.imp-hint--warn {
  color: var(--vs-warning);
}

.imp-list {
  list-style: none;
  margin: 4px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.imp-list__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 8px;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius-sm);
  background: var(--vs-bg-sunken);
  font-size: 12px;
}

.imp-list__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.imp-listtitle {
  font-size: 12px;
  font-weight: 600;
  color: var(--vs-text);
}
</style>
