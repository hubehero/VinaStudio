<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWorkspaceStore } from '@/stores/workspace'
import { pickDirectory } from '@/api/bridge'

const { t } = useI18n()
const workspaceStore = useWorkspaceStore()

const emit = defineEmits<{
  (e: 'complete'): void
}>()

const step = ref<'welcome' | 'choose' | 'creating' | 'done'>('welcome')
const workspaceName = ref('VinaStudio Workspace')
const customPath = ref('')
const isCreating = ref(false)
const errorMessage = ref('')

const suggestedPath = computed(() => {
  const home = '~'
  return `${home}/VinaStudioWorkspace`
})

async function browseDirectory() {
  try {
    const dir = await pickDirectory(t('workspace.choose.browseTitle'))
    if (dir) {
      customPath.value = dir
    }
  } catch {
    // User cancelled or bridge not available
  }
}

async function createWorkspace() {
  const path = customPath.value.trim()
  if (!path) {
    errorMessage.value = t('workspace.error.pathRequired')
    return
  }

  isCreating.value = true
  errorMessage.value = ''
  step.value = 'creating'

  try {
    await workspaceStore.initWorkspace(path, workspaceName.value || 'VinaStudio Workspace')
    step.value = 'done'
    // Emit complete after brief success display — no page reload needed
    setTimeout(() => emit('complete'), 1200)
  } catch (e: unknown) {
    errorMessage.value = e instanceof Error ? e.message : String(e)
    step.value = 'choose'
  } finally {
    isCreating.value = false
  }
}

function useDefaultPath() {
  customPath.value = suggestedPath.value
}
</script>

<template>
  <div class="workspace-wizard">
    <!-- Step: Welcome -->
    <div v-if="step === 'welcome'" class="wizard-step">
      <div class="welcome-icon">📁</div>
      <h1>{{ t('workspace.welcome.title') }}</h1>
      <p class="welcome-text">{{ t('workspace.welcome.description') }}</p>
      <button class="btn-primary" @click="step = 'choose'">
        {{ t('workspace.welcome.getStarted') }}
      </button>
    </div>

    <!-- Step: Choose Directory -->
    <div v-if="step === 'choose'" class="wizard-step">
      <h2>{{ t('workspace.choose.title') }}</h2>
      <p class="step-description">{{ t('workspace.choose.description') }}</p>

      <div class="form-group">
        <label>{{ t('workspace.choose.nameLabel') }}</label>
        <input
          v-model="workspaceName"
          type="text"
          :placeholder="t('workspace.choose.namePlaceholder')"
          class="form-input"
        />
      </div>

      <div class="form-group">
        <label>{{ t('workspace.choose.pathLabel') }}</label>
        <div class="path-input-group">
          <input
            v-model="customPath"
            type="text"
            :placeholder="t('workspace.choose.pathPlaceholder')"
            class="form-input"
          />
          <button class="btn-secondary" @click="browseDirectory">
            {{ t('workspace.choose.browse') }}
          </button>
        </div>
        <button class="btn-link" @click="useDefaultPath">
          {{ t('workspace.choose.useDefault', { path: suggestedPath }) }}
        </button>
      </div>

      <div v-if="errorMessage" class="error-message">
        {{ errorMessage }}
      </div>

      <div class="step-actions">
        <button class="btn-secondary" @click="step = 'welcome'">
          {{ t('workspace.choose.back') }}
        </button>
        <button
          class="btn-primary"
          :disabled="!customPath.trim() || isCreating"
          @click="createWorkspace"
        >
          {{ isCreating ? t('workspace.choose.creating') : t('workspace.choose.create') }}
        </button>
      </div>
    </div>

    <!-- Step: Creating -->
    <div v-if="step === 'creating'" class="wizard-step">
      <div class="spinner"></div>
      <h2>{{ t('workspace.creating.title') }}</h2>
      <p>{{ t('workspace.creating.description') }}</p>
    </div>

    <!-- Step: Done -->
    <div v-if="step === 'done'" class="wizard-step">
      <div class="done-icon">✓</div>
      <h2>{{ t('workspace.done.title') }}</h2>
      <p>{{ t('workspace.done.description', { path: workspaceStore.workspacePath }) }}</p>
    </div>
  </div>
</template>

<style scoped>
.workspace-wizard {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--vs-bg-app, #0d1526);
  z-index: 9999;
}

.wizard-step {
  max-width: 480px;
  width: 100%;
  padding: 48px;
  text-align: center;
}

.welcome-icon {
  font-size: 64px;
  margin-bottom: 24px;
}

h1 {
  font-size: 28px;
  font-weight: 600;
  color: var(--vs-text, #e6edf7);
  margin: 0 0 16px;
}

h2 {
  font-size: 22px;
  font-weight: 600;
  color: var(--vs-text, #e6edf7);
  margin: 0 0 12px;
}

.welcome-text {
  color: var(--vs-text-faint, #8b949e);
  line-height: 1.6;
  margin-bottom: 32px;
}

.step-description {
  color: var(--vs-text-faint, #8b949e);
  margin-bottom: 24px;
}

.form-group {
  margin-bottom: 20px;
  text-align: left;
}

label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: var(--vs-text, #e6edf7);
  margin-bottom: 8px;
}

.form-input {
  width: 100%;
  padding: 10px 14px;
  font-size: 14px;
  background: var(--vs-bg-sunken, #161b22);
  border: 1px solid var(--vs-border, #30363d);
  border-radius: 6px;
  color: var(--vs-text, #e6edf7);
  outline: none;
  transition: border-color 0.2s;
}

.form-input:focus {
  border-color: var(--accent-primary, #4fd1c5);
}

.form-input::placeholder {
  color: var(--vs-text-faint, #484f58);
}

.path-input-group {
  display: flex;
  gap: 8px;
}

.path-input-group .form-input {
  flex: 1;
}

.btn-primary {
  padding: 12px 32px;
  font-size: 15px;
  font-weight: 500;
  background: var(--accent-primary, #4fd1c5);
  color: var(--vs-bg-app, #0d1526);
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: opacity 0.2s;
}

.btn-primary:hover {
  opacity: 0.9;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 10px 20px;
  font-size: 14px;
  background: var(--vs-bg-sunken, #161b22);
  color: var(--vs-text, #e6edf7);
  border: 1px solid var(--vs-border, #30363d);
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-secondary:hover {
  background: var(--vs-bg-surface, #21262d);
}

.btn-link {
  background: none;
  border: none;
  color: var(--accent-primary, #4fd1c5);
  font-size: 13px;
  cursor: pointer;
  padding: 4px 0;
  margin-top: 8px;
}

.btn-link:hover {
  text-decoration: underline;
}

.step-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-top: 32px;
}

.error-message {
  padding: 12px;
  background: rgba(248, 81, 73, 0.1);
  border: 1px solid rgba(248, 81, 73, 0.4);
  border-radius: 6px;
  color: #f85149;
  font-size: 14px;
  margin-top: 16px;
}

.spinner {
  width: 48px;
  height: 48px;
  border: 3px solid var(--vs-border, #30363d);
  border-top-color: var(--accent-primary, #4fd1c5);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 24px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.done-icon {
  width: 64px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(63, 185, 80, 0.15);
  color: #3fb950;
  font-size: 32px;
  border-radius: 50%;
  margin: 0 auto 24px;
}
</style>
