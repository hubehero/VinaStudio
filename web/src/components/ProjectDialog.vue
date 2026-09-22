<script setup lang="ts">
import { FolderOpened, Document } from '@element-plus/icons-vue'
import { ElButton, ElDialog, ElInput, ElMessage, ElTable, ElTableColumn } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { useProjectStore } from '@/stores/project'

const { t } = useI18n()
const project = useProjectStore()

const visible = ref(false)
const projectNameInput = ref('')
const searchQuery = ref('')
const loadPathInput = ref('')

const filteredProjects = computed(() => {
  if (!searchQuery.value) return project.savedProjects
  const q = searchQuery.value.toLowerCase()
  return project.savedProjects.filter(p =>
    p.name.toLowerCase().includes(q) || p.filename.toLowerCase().includes(q),
  )
})

defineExpose({ open })

function open(): void {
  project.refreshProjectList()
  visible.value = true
}

async function handleSave(): Promise<void> {
  const name = projectNameInput.value.trim() || project.projectName
  const path = await project.saveProject(name)
  if (path) {
    ElMessage.success(t('project.savedSuccess'))
    projectNameInput.value = ''
  } else {
    ElMessage.error(t('project.savedFailed'))
  }
}

async function handleLoad(path: string): Promise<void> {
  const success = await project.loadProject(path)
  if (success) {
    ElMessage.success(t('project.loadedSuccess'))
    visible.value = false
  } else {
    ElMessage.error(t('project.loadedFailed'))
  }
}

async function handleDelete(filename: string): Promise<void> {
  const success = await project.deleteProject(filename)
  if (success) {
    ElMessage.success(t('project.deletedSuccess'))
  } else {
    ElMessage.error(t('project.deletedFailed'))
  }
}

async function handleLoadFromPath(): Promise<void> {
  const path = loadPathInput.value.trim()
  if (!path) return
  await handleLoad(path)
  loadPathInput.value = ''
}

function formatDate(iso: string): string {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleDateString()
  } catch {
    return iso
  }
}

onMounted(() => {
  project.refreshProjectList()
})
</script>

<template>
  <ElDialog
    v-model="visible"
    :title="t('project.title')"
    width="640px"
    :close-on-click-modal="false"
  >
    <div class="project-dialog">
      <!-- Save section -->
      <div class="project-section">
        <h3 class="project-section__title">{{ t('project.save') }}</h3>
        <div class="project-save">
          <ElInput
            v-model="projectNameInput"
            :placeholder="project.projectName"
            size="small"
          >
            <template #append>
              <ElButton :icon="Document" @click="handleSave">
                {{ t('project.save') }}
              </ElButton>
            </template>
          </ElInput>
        </div>
      </div>

      <!-- Load from path -->
      <div class="project-section">
        <h3 class="project-section__title">{{ t('project.loadFromPath') }}</h3>
        <div class="project-load-path">
          <ElInput
            v-model="loadPathInput"
            :placeholder="t('project.pathPlaceholder')"
            size="small"
          >
            <template #append>
              <ElButton :icon="FolderOpened" @click="handleLoadFromPath">
                {{ t('project.load') }}
              </ElButton>
            </template>
          </ElInput>
        </div>
      </div>

      <!-- Saved projects list -->
      <div class="project-section">
        <div class="project-section__header">
          <h3 class="project-section__title">{{ t('project.savedProjects') }}</h3>
          <ElInput
            v-model="searchQuery"
            :placeholder="t('common.search')"
            size="small"
            clearable
            style="width: 200px"
          />
        </div>

        <div v-if="filteredProjects.length === 0" class="project-empty">
          {{ t('project.noProjects') }}
        </div>

        <ElTable v-else :data="filteredProjects" size="small" max-height="300">
          <ElTableColumn prop="name" :label="t('project.name')" min-width="150" />
          <ElTableColumn prop="updatedAt" :label="t('project.modified')" width="120">
            <template #default="{ row }">
              {{ formatDate(row.updatedAt) }}
            </template>
          </ElTableColumn>
          <ElTableColumn :label="''" width="120">
            <template #default="{ row }">
              <ElButton size="small" text @click="handleLoad(row.path)">
                {{ t('project.load') }}
              </ElButton>
              <ElButton size="small" text type="danger" @click="handleDelete(row.filename)">
                {{ t('common.delete') }}
              </ElButton>
            </template>
          </ElTableColumn>
        </ElTable>
      </div>
    </div>
  </ElDialog>
</template>

<style scoped>
.project-dialog {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.project-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.project-section__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.project-section__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--vs-text);
  margin: 0;
}

.project-save,
.project-load-path {
  display: flex;
  gap: 8px;
}

.project-empty {
  padding: 24px;
  text-align: center;
  color: var(--vs-text-faint);
  font-size: 13px;
}
</style>
