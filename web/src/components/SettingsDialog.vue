<script setup lang="ts">
import { FolderOpened, Monitor, Moon, Sunny } from '@element-plus/icons-vue'
import { ElButton, ElDialog, ElInput, ElInputNumber, ElMessage, ElRadio, ElRadioGroup, ElSlider, ElSwitch } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '@/api/http'
import { pickDirectory } from '@/api/bridge'
import { useSettingsStore } from '@/stores/settings'
import { useUiStore, type ThemeMode } from '@/stores/ui'
import { useWorkspaceStore } from '@/stores/workspace'

const { t, locale } = useI18n()
const settings = useSettingsStore()
const ui = useUiStore()
const workspace = useWorkspaceStore()

const visible = ref(false)
const uploadLimitMb = ref(100)

// Workspace settings
const workspaceName = ref('')
const migrateTargetPath = ref('')
const isMigrating = ref(false)

onMounted(async () => {
  try {
    const limit = await api.uploadLimit()
    uploadLimitMb.value = limit.megabytes
  } catch {
    // ignore, use default
  }
})

function open(): void {
  visible.value = true
  workspaceName.value = workspace.workspaceName
}

function handleThemeChange(val: string | number | boolean | undefined): void {
  ui.setTheme(String(val) as ThemeMode)
}

function handleLanguageChange(val: string | number | boolean | undefined): void {
  void ui.setLocalePreference(String(val))
}

function handleReset(): void {
  settings.resetViewer()
  void ui.resetPreferences()
}

async function handleWorkspaceNameSave() {
  if (!workspaceName.value.trim()) return
  try {
    await workspace.renameWorkspace(workspaceName.value.trim())
    ElMessage.success(t('common.success'))
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function browseWorkspace() {
  try {
    const dir = await pickDirectory(t('workspace.settings.migrateBrowseTitle'))
    if (dir) {
      migrateTargetPath.value = dir
    }
  } catch {
    // User cancelled
  }
}

async function handleMigrate() {
  if (!migrateTargetPath.value.trim()) {
    ElMessage.warning(t('workspace.error.pathRequired'))
    return
  }

  isMigrating.value = true
  try {
    await workspace.migrateWorkspace(migrateTargetPath.value.trim())
    ElMessage.success(t('common.success'))
    migrateTargetPath.value = ''
    // Reload to apply changes
    window.location.reload()
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    isMigrating.value = false
  }
}

defineExpose({ open })
</script>

<template>
  <ElDialog
    v-model="visible"
    :title="t('settings.title')"
    width="520px"
    :close-on-click-modal="false"
  >
    <div class="settings-dialog">
      <!-- General Settings -->
      <div class="settings-section">
        <h3 class="settings-section__title">{{ t('settings.general') }}</h3>

        <div class="settings-item">
          <div class="settings-item__info">
            <span class="settings-item__label">{{ t('settings.language') }}</span>
          </div>
          <ElRadioGroup :model-value="locale" size="small" @update:model-value="handleLanguageChange">
            <ElRadio value="zh-CN">中文</ElRadio>
            <ElRadio value="en-US">English</ElRadio>
          </ElRadioGroup>
        </div>

        <div class="settings-item">
          <div class="settings-item__info">
            <span class="settings-item__label">{{ t('settings.theme') }}</span>
          </div>
          <ElRadioGroup :model-value="ui.theme" size="small" @update:model-value="handleThemeChange">
            <ElRadio value="dark">
              <el-icon><Moon /></el-icon> {{ t('header.themeDark') }}
            </ElRadio>
            <ElRadio value="light">
              <el-icon><Sunny /></el-icon> {{ t('header.themeLight') }}
            </ElRadio>
            <ElRadio value="system">
              <el-icon><Monitor /></el-icon> {{ t('header.themeSystem') }}
            </ElRadio>
          </ElRadioGroup>
        </div>

        <div class="settings-item">
          <div class="settings-item__info">
            <span class="settings-item__label">{{ t('settings.uploadLimit') }}</span>
            <span class="settings-item__desc">{{ t('settings.uploadLimitDesc') }}</span>
          </div>
          <span class="settings-item__value">{{ uploadLimitMb }} MB</span>
        </div>
      </div>

      <!-- Workspace Settings -->
      <div class="settings-section">
        <h3 class="settings-section__title">{{ t('workspace.settings.title') }}</h3>

        <div class="settings-item">
          <div class="settings-item__info">
            <span class="settings-item__label">{{ t('workspace.settings.currentPath') }}</span>
          </div>
          <span class="settings-item__value workspace-path">{{ workspace.workspacePath }}</span>
        </div>

        <div class="settings-item">
          <div class="settings-item__info">
            <span class="settings-item__label">{{ t('workspace.settings.name') }}</span>
          </div>
          <div class="workspace-name-group">
            <ElInput
              v-model="workspaceName"
              size="small"
              style="width: 200px"
              @keyup.enter="handleWorkspaceNameSave"
            />
            <ElButton size="small" type="primary" @click="handleWorkspaceNameSave">
              {{ t('common.done') }}
            </ElButton>
          </div>
        </div>

        <div class="settings-item settings-item--block">
          <div class="settings-item__info">
            <span class="settings-item__label">{{ t('workspace.settings.migrate') }}</span>
            <span class="settings-item__desc">{{ t('workspace.settings.migrateDescription') }}</span>
          </div>
          <div class="workspace-migrate">
            <div class="workspace-migrate__input">
              <ElInput
                v-model="migrateTargetPath"
                size="small"
                :placeholder="t('workspace.settings.migrateTarget')"
              />
              <ElButton size="small" @click="browseWorkspace">
                <el-icon><FolderOpened /></el-icon>
              </ElButton>
            </div>
            <ElButton
              size="small"
              type="warning"
              :loading="isMigrating"
              :disabled="!migrateTargetPath.trim() || isMigrating"
              @click="handleMigrate"
            >
              {{ isMigrating ? t('workspace.settings.migrating') : t('workspace.settings.migrateButton') }}
            </ElButton>
          </div>
        </div>
      </div>

      <!-- Viewer Settings -->
      <div class="settings-section">
        <h3 class="settings-section__title">{{ t('settings.viewer') }}</h3>

        <label class="settings-item">
          <div class="settings-item__info">
            <span class="settings-item__label">{{ t('settings.invertZoom') }}</span>
            <span class="settings-item__desc">{{ t('settings.invertZoomDesc') }}</span>
          </div>
          <ElSwitch v-model="settings.viewer.invertZoom" size="small" />
        </label>

        <label class="settings-item">
          <div class="settings-item__info">
            <span class="settings-item__label">{{ t('settings.showAxes') }}</span>
            <span class="settings-item__desc">{{ t('settings.showAxesDesc') }}</span>
          </div>
          <ElSwitch v-model="settings.viewer.showAxes" size="small" />
        </label>

        <div v-if="settings.viewer.showAxes" class="settings-item settings-item--sub">
          <div class="settings-item__info">
            <span class="settings-item__label">{{ t('settings.axesSize') }}</span>
          </div>
          <ElInputNumber
            v-model="settings.viewer.axesSize"
            :min="0.5"
            :max="5"
            :step="0.5"
            size="small"
            style="width: 120px"
          />
        </div>

        <label class="settings-item">
          <div class="settings-item__info">
            <span class="settings-item__label">{{ t('settings.autoRotate') }}</span>
            <span class="settings-item__desc">{{ t('settings.autoRotateDesc') }}</span>
          </div>
          <ElSwitch v-model="settings.viewer.autoRotate" size="small" />
        </label>

        <div v-if="settings.viewer.autoRotate" class="settings-item settings-item--sub">
          <div class="settings-item__info">
            <span class="settings-item__label">{{ t('settings.autoRotateSpeed') }}</span>
          </div>
          <ElSlider
            v-model="settings.viewer.autoRotateSpeed"
            :min="0.1"
            :max="5"
            :step="0.1"
            style="width: 160px"
          />
        </div>
      </div>

      <!-- Surface Settings -->
      <div class="settings-section">
        <h3 class="settings-section__title">{{ t('settings.surface') }}</h3>

        <label class="settings-item">
          <div class="settings-item__info">
            <span class="settings-item__label">{{ t('settings.showSurface') }}</span>
            <span class="settings-item__desc">{{ t('settings.showSurfaceDesc') }}</span>
          </div>
          <ElSwitch
            :model-value="settings.viewer.surfaceKind !== null"
            size="small"
            @update:model-value="(v: string | number | boolean) => { settings.viewer.surfaceKind = v ? 'SES' : null }"
          />
        </label>

        <div v-if="settings.viewer.surfaceKind !== null" class="settings-item settings-item--sub">
          <div class="settings-item__info">
            <span class="settings-item__label">{{ t('settings.surfaceKind') }}</span>
          </div>
          <ElRadioGroup
            :model-value="settings.viewer.surfaceKind"
            size="small"
            @update:model-value="(v: string | number | boolean | undefined) => { settings.viewer.surfaceKind = String(v) as 'VDW' | 'SAS' | 'SES' }"
          >
            <ElRadio v-for="kind in ['VDW', 'SAS', 'SES']" :key="kind" :value="kind">
              {{ kind }}
            </ElRadio>
          </ElRadioGroup>
        </div>

        <div v-if="settings.viewer.surfaceKind !== null" class="settings-item settings-item--sub">
          <div class="settings-item__info">
            <span class="settings-item__label">{{ t('settings.surfaceOpacity') }}</span>
          </div>
          <ElSlider
            v-model="settings.viewer.surfaceOpacity"
            :min="0.1"
            :max="1"
            :step="0.05"
            style="width: 160px"
          />
        </div>
      </div>
    </div>

    <template #footer>
      <ElButton @click="handleReset">{{ t('settings.resetDefaults') }}</ElButton>
      <ElButton type="primary" @click="visible = false">{{ t('common.done') }}</ElButton>
    </template>
  </ElDialog>
</template>

<style scoped>
.settings-dialog {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.settings-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.settings-section__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--vs-text);
  margin: 0 0 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--vs-border);
}

.settings-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0;
}

.settings-item--sub {
  padding-left: 20px;
}

.settings-item--block {
  flex-direction: column;
  align-items: stretch;
}

.settings-item__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.settings-item__label {
  font-size: 13px;
  color: var(--vs-text);
}

.settings-item__desc {
  font-size: 11.5px;
  color: var(--vs-text-faint);
  line-height: 1.4;
}

.settings-item__value {
  font-size: 13px;
  font-weight: 500;
  color: var(--vs-text);
  padding: 4px 10px;
  background: var(--vs-bg-sunken);
  border-radius: var(--vs-radius-sm);
}

.workspace-path {
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-name-group {
  display: flex;
  gap: 8px;
}

.workspace-migrate {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

.workspace-migrate__input {
  display: flex;
  gap: 8px;
}

:deep(.el-radio-group) {
  display: flex;
  gap: 4px;
}

:deep(.el-radio) {
  margin-right: 0;
  padding: 4px 10px;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius-sm);
  height: auto;
}

:deep(.el-radio.is-bordered) {
  border-color: var(--vs-border);
}

:deep(.el-radio__input) {
  display: none;
}

:deep(.el-radio__label) {
  padding: 0;
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
