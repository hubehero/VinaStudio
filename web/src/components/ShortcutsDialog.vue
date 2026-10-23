<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const { t } = useI18n()

const shortcuts = [
  { keys: 'Ctrl/Cmd + K', label: 'shortcuts.commandPalette' },
  { keys: '↑ / ↓', label: 'shortcuts.navigate' },
  { keys: 'Enter', label: 'shortcuts.run' },
  { keys: 'Ctrl/Cmd + Z', label: 'shortcuts.undo' },
  { keys: '?', label: 'shortcuts.help' },
  { keys: 'Esc', label: 'shortcuts.escape' },
] as const
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="t('shortcuts.title')"
    width="480px"
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
  >
    <dl class="shortcuts-list">
      <div v-for="shortcut in shortcuts" :key="shortcut.keys" class="shortcuts-list__row">
        <dt><kbd>{{ shortcut.keys }}</kbd></dt>
        <dd>{{ t(shortcut.label) }}</dd>
      </div>
    </dl>
    <p class="shortcuts-note">{{ t('shortcuts.note') }}</p>
  </el-dialog>
</template>

<style scoped>
.shortcuts-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
}

.shortcuts-list__row {
  display: flex;
  align-items: baseline;
  gap: 14px;
}

.shortcuts-list__row dt {
  flex: 0 0 150px;
}

.shortcuts-list__row dd {
  margin: 0;
  font-size: 13px;
  color: var(--vs-text-muted);
}

kbd {
  display: inline-block;
  padding: 1px 6px;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius-sm);
  background: var(--vs-bg-sunken);
  font-family: var(--vs-font-mono);
  font-size: 11px;
}

.shortcuts-note {
  margin: 16px 0 0;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--vs-text-faint);
}
</style>
