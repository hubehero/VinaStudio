<script setup lang="ts">
import {
  FolderOpened,
  Grid,
  Monitor,
  Moon,
  Setting,
  Sunny,
  View,
} from '@element-plus/icons-vue'
import { ElAlert, ElButton, ElDialog, ElInput, ElInputNumber, ElMessage, ElRadio, ElRadioGroup, ElSlider, ElSwitch } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '@/api/http'
import { openInBrowser, pickDirectory } from '@/api/bridge'
import { rendererInfo } from '@/composables/use3Dmol'
import { useSettingsStore } from '@/stores/settings'
import type { UpdateCheck } from '@/types/api'
import { useUiStore, type ThemeMode } from '@/stores/ui'
import { useWorkspaceStore } from '@/stores/workspace'

const { t, locale, te } = useI18n()
const settings = useSettingsStore()
const ui = useUiStore()
const workspace = useWorkspaceStore()

const visible = ref(false)
const uploadLimitMb = ref(100)
const currentVersion = ref('')
const updateChecking = ref(false)
const updateResult = ref<UpdateCheck | null>(null)

// Workspace settings
const workspaceName = ref('')
const migrateTargetPath = ref('')
const isMigrating = ref(false)

// Tab navigation
type TabKey = 'general' | 'workspace' | 'viewer' | 'render' | 'surface'
const activeTab = ref<TabKey>('general')

const tabs = computed<{ key: TabKey; label: string; icon: typeof Setting }[]>(() => [
  { key: 'general', label: t('settings.general'), icon: Setting },
  { key: 'workspace', label: t('workspace.settings.title'), icon: FolderOpened },
  { key: 'viewer', label: t('settings.viewer'), icon: View },
  { key: 'render', label: t('settings.renderQuality'), icon: Monitor },
  { key: 'surface', label: t('settings.surface'), icon: Grid },
])

onMounted(async () => {
  try {
    const limit = await api.uploadLimit()
    uploadLimitMb.value = limit.megabytes
  } catch {
    // ignore, use default
  }
  try {
    const info = await api.systemInfo()
    currentVersion.value = info.app.version
  } catch {
    // The update check reports its own current version; leave this blank.
  }
})

function open(): void {
  visible.value = true
  activeTab.value = 'general'
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

async function checkForUpdates(): Promise<void> {
  updateChecking.value = true
  try {
    const result = await api.updateCheck()
    updateResult.value = result
    if (result.current) currentVersion.value = result.current
  } catch {
    updateResult.value = {
      current: currentVersion.value,
      latest: null,
      updateAvailable: false,
      url: '',
      publishedAt: null,
      error: 'unavailable',
    }
  } finally {
    updateChecking.value = false
  }
}

function openReleasePage(): void {
  const url = updateResult.value?.url
  if (url) void openInBrowser(url)
}

const updateErrorText = computed(() => {
  const code = updateResult.value?.error
  if (!code) return ''
  const key = `settings.updateError.${code}`
  return te(key) ? t(key) : t('settings.updateError.unavailable')
})

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

const docsUrl = computed(() => `${window.location.origin}/docs`)

function openDocs(): void {
  openInBrowser(docsUrl.value)
}

async function copyDocsUrl(): Promise<void> {
  try {
    await navigator.clipboard.writeText(docsUrl.value)
    ElMessage.success(t('settings.urlCopied'))
  } catch {
    ElMessage.error(t('settings.copyFailed'))
  }
}

defineExpose({ open })
</script>

<template>
  <ElDialog
    v-model="visible"
    :title="t('settings.title')"
    width="800px"
    :close-on-click-modal="false"
  >
    <div class="settings-body">
      <!-- Left sidebar: tab navigation -->
      <nav class="settings-sidebar">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="settings-sidebar__item"
          :class="{ 'is-active': activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          <el-icon :size="14"><component :is="tab.icon" /></el-icon>
          <span>{{ tab.label }}</span>
        </button>
      </nav>

      <!-- Right content area -->
      <div class="settings-content">
        <!-- General -->
        <div v-show="activeTab === 'general'" class="settings-section">
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

          <div class="settings-item">
            <div class="settings-item__info">
              <span class="settings-item__label">{{ t('settings.version') }}</span>
              <span class="settings-item__desc">{{ t('settings.versionDesc') }}</span>
            </div>
            <div class="settings-link-group">
              <span class="settings-item__value vs-mono">{{ currentVersion ? 'v' + currentVersion : '—' }}</span>
              <ElButton size="small" :loading="updateChecking" @click="checkForUpdates">
                {{ t('settings.checkUpdates') }}
              </ElButton>
              <ElButton
                v-if="updateResult?.updateAvailable"
                size="small"
                type="primary"
                @click="openReleasePage"
              >
                {{ t('settings.openReleasePage') }}
              </ElButton>
            </div>
          </div>

          <ElAlert
            v-if="updateResult?.updateAvailable"
            :title="t('settings.updateAvailable', { version: updateResult.latest ?? '' })"
            type="success"
            :closable="false"
            show-icon
            class="settings-update-alert"
          />
          <ElAlert
            v-else-if="updateResult && !updateResult.error"
            :title="t('settings.upToDate')"
            type="info"
            :closable="false"
            show-icon
            class="settings-update-alert"
          />
          <ElAlert
            v-else-if="updateResult?.error"
            :title="updateErrorText"
            type="warning"
            :closable="false"
            show-icon
            class="settings-update-alert"
          />

          <div class="settings-item">
            <div class="settings-item__info">
              <span class="settings-item__label">{{ t('header.documentation') }}</span>
              <span class="settings-item__desc">{{ t('settings.apiDocsDesc') }}</span>
            </div>
            <div class="settings-link-group">
              <span class="settings-item__value vs-mono" style="font-size: 12px">{{ docsUrl }}</span>
              <ElButton size="small" @click="copyDocsUrl">
                {{ t('settings.copyUrl') }}
              </ElButton>
              <ElButton size="small" type="primary" @click="openDocs">
                {{ t('settings.openDocs') }}
              </ElButton>
            </div>
          </div>
        </div>

        <!-- Workspace -->
        <div v-show="activeTab === 'workspace'" class="settings-section">
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
                style="width: 240px"
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

        <!-- 3D Viewer -->
        <div v-show="activeTab === 'viewer'" class="settings-section">
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
              style="width: 200px"
            />
          </div>
        </div>

        <!-- Render Quality -->
        <div v-show="activeTab === 'render'" class="settings-section">
          <label class="settings-item">
            <div class="settings-item__info">
              <span class="settings-item__label">{{ t('settings.renderQualityLabel') }}</span>
              <span class="settings-item__desc">{{ t('settings.renderQualityDesc') }}</span>
            </div>
            <ElRadioGroup v-model="settings.viewer.renderQuality" size="small">
              <ElRadio value="low">{{ t('settings.qualityLow') }}</ElRadio>
              <ElRadio value="medium">{{ t('settings.qualityMedium') }}</ElRadio>
              <ElRadio value="high">{{ t('settings.qualityHigh') }}</ElRadio>
            </ElRadioGroup>
          </label>

          <!-- Active GL renderer: probed once a viewport exists; null before that. -->
          <div class="settings-item">
            <div class="settings-item__info">
              <span class="settings-item__label">{{ t('settings.rendererLabel') }}</span>
            </div>
            <span class="settings-item__value vs-mono" style="font-size: 12px">
              {{ rendererInfo?.renderer ?? t('common.unknown') }}
            </span>
          </div>
          <ElAlert
            v-if="rendererInfo?.software"
            type="warning"
            :closable="false"
            :title="t('settings.softwareRendererWarn')"
          />

          <!-- Optional quality trades; both default off = preset look. -->
          <label class="settings-item">
            <div class="settings-item__info">
              <span class="settings-item__label">{{ t('settings.antialiasOffLabel') }}</span>
              <span class="settings-item__desc">{{ t('settings.antialiasOffHint') }}</span>
            </div>
            <ElSwitch v-model="settings.viewer.antialiasOff" size="small" />
          </label>
          <label class="settings-item">
            <div class="settings-item__info">
              <span class="settings-item__label">{{ t('settings.adaptiveAOLabel') }}</span>
              <span class="settings-item__desc">{{ t('settings.adaptiveAOHint') }}</span>
            </div>
            <ElSwitch v-model="settings.viewer.adaptiveAO" size="small" />
          </label>
        </div>

        <!-- Surface -->
        <div v-show="activeTab === 'surface'" class="settings-section">
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
              style="width: 200px"
            />
          </div>
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
/* -- body: left sidebar + right content ------------------------------------ */

.settings-body {
  display: flex;
  gap: 0;
  min-height: 400px;
}

/* -- left sidebar ----------------------------------------------------------- */

.settings-sidebar {
  width: 160px;
  flex: none;
  border-right: 1px solid var(--vs-border);
  padding: 8px 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.settings-sidebar__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  margin: 0 6px;
  border: none;
  border-left: 2px solid transparent;
  border-radius: var(--vs-radius-sm);
  background: none;
  font: inherit;
  font-size: 13px;
  color: var(--vs-text-muted);
  cursor: pointer;
  text-align: left;
  transition: all 0.15s ease;
}

.settings-sidebar__item:hover {
  background: var(--vs-bg-sunken);
  color: var(--vs-text);
}

.settings-sidebar__item.is-active {
  color: var(--accent-primary, var(--vs-accent, #4fd1c5));
  border-left-color: var(--accent-primary, var(--vs-accent, #4fd1c5));
  background: color-mix(in srgb, var(--accent-primary, var(--vs-accent, #4fd1c5)) 6%, transparent);
  font-weight: 500;
}

/* -- right content area ----------------------------------------------------- */

.settings-content {
  flex: 1;
  min-width: 0;
  padding: 16px 24px;
  overflow-y: auto;
}

/* -- section & items (shared with original layout) -------------------------- */

.settings-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.settings-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0;
}

.settings-update-alert {
  margin-top: 4px;
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
  max-width: 360px;
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

.settings-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  font-size: 13px;
  font-family: var(--vs-font-mono);
  color: var(--accent-primary, var(--vs-accent, #4fd1c5));
  background: var(--vs-bg-sunken);
  border-radius: var(--vs-radius-sm);
  text-decoration: none;
  transition: background 0.15s ease;
}

.settings-link:hover {
  background: color-mix(in srgb, var(--accent-primary, var(--vs-accent, #4fd1c5)) 12%, transparent);
}

.settings-link-group {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
