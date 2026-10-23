<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { useUiStore } from '@/stores/ui'
import { useUndoStore } from '@/stores/undo'

const emit = defineEmits<{ settings: []; shortcuts: [] }>()

const { t } = useI18n()
const router = useRouter()
const ui = useUiStore()
const undo = useUndoStore()

interface PaletteCommand {
  id: string
  label: string
  group: 'navigation' | 'actions' | 'preferences'
  keywords: string
  disabled?: boolean
  run: () => void | Promise<void>
}

const visible = ref(false)
const query = ref('')
const selectedIndex = ref(0)
const inputRef = ref<{ focus: () => void } | null>(null)

const navigation = [
  ['workbench', '/workbench'],
  ['molecules', '/molecules'],
  ['box', '/box'],
  ['docking', '/docking'],
  ['report', '/report'],
  ['batch', '/batch'],
  ['screening', '/screening'],
  ['results', '/results'],
  ['environment', '/environment'],
  ['help', '/help'],
  ['about', '/about'],
] as const

const commands = ref<PaletteCommand[]>([])

function buildCommands(): void {
  commands.value = [
    ...navigation.map(([key, path]) => ({
      id: `nav-${key}`,
      label: t(`nav.${key}`),
      group: 'navigation' as const,
      keywords: `${path} ${key}`,
      run: () => { void router.push(path) },
    })),
    {
      id: 'undo',
      label: t('commandPalette.undo'),
      group: 'actions',
      keywords: 'undo ctrl z',
      disabled: !undo.canUndo,
      run: () => { void undo.undoLast() },
    },
    {
      id: 'settings',
      label: t('commandPalette.settings'),
      group: 'actions',
      keywords: 'settings preferences',
      run: () => emit('settings'),
    },
    {
      id: 'shortcuts',
      label: t('commandPalette.shortcuts'),
      group: 'actions',
      keywords: 'keyboard shortcuts help',
      run: () => emit('shortcuts'),
    },
    {
      id: 'theme-dark',
      label: t('commandPalette.themeDark'),
      group: 'preferences',
      keywords: 'theme dark',
      run: () => ui.setTheme('dark'),
    },
    {
      id: 'theme-light',
      label: t('commandPalette.themeLight'),
      group: 'preferences',
      keywords: 'theme light',
      run: () => ui.setTheme('light'),
    },
    {
      id: 'theme-system',
      label: t('commandPalette.themeSystem'),
      group: 'preferences',
      keywords: 'theme system',
      run: () => ui.setTheme('system'),
    },
    {
      id: 'language-zh',
      label: t('commandPalette.languageZh'),
      group: 'preferences',
      keywords: 'language chinese zh',
      run: () => ui.setLocalePreference('zh-CN'),
    },
    {
      id: 'language-en',
      label: t('commandPalette.languageEn'),
      group: 'preferences',
      keywords: 'language english en',
      run: () => ui.setLocalePreference('en-US'),
    },
  ]
}

watch(
  () => [ui.locale, ui.theme, undo.canUndo, undo.lastLabel],
  buildCommands,
  { immediate: true },
)

const filtered = ref<PaletteCommand[]>([])

watch(
  () => [query.value, commands.value] as const,
  () => {
    const needle = query.value.trim().toLowerCase()
    filtered.value = needle
      ? commands.value.filter((command) =>
          `${command.label} ${command.keywords}`.toLowerCase().includes(needle),
        )
      : commands.value
    selectedIndex.value = 0
  },
  { immediate: true },
)

watch(selectedIndex, async () => {
  await nextTick()
  document.getElementById(`command-${filtered.value[selectedIndex.value]?.id}`)?.scrollIntoView({
    block: 'nearest',
  })
})

function open(): void {
  query.value = ''
  selectedIndex.value = 0
  visible.value = true
  void nextTick(() => inputRef.value?.focus())
}

function focusInput(): void {
  inputRef.value?.focus()
}

function runCommand(command: PaletteCommand | undefined): void {
  if (!command || command.disabled) return
  visible.value = false
  void command.run()
}

function move(delta: number): void {
  if (filtered.value.length === 0) return
  selectedIndex.value =
    (selectedIndex.value + delta + filtered.value.length) % filtered.value.length
}

function onInputKeydown(event: KeyboardEvent): void {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    move(1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    move(-1)
  } else if (event.key === 'Enter') {
    event.preventDefault()
    runCommand(filtered.value[selectedIndex.value])
  }
}

function onGlobalKeydown(event: KeyboardEvent): void {
  if (event.defaultPrevented) return
  const target = event.target as HTMLElement | null
  const editable = target?.matches('input, textarea, select, [contenteditable="true"]') ?? false
  const modifier = event.metaKey || event.ctrlKey

  if (modifier && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    if (visible.value) visible.value = false
    else open()
    return
  }
  if (editable) return
  if (document.querySelector('.el-overlay')) return
  if (modifier && event.key.toLowerCase() === 'z') {
    event.preventDefault()
    void undo.undoLast()
  } else if (event.key === '?') {
    event.preventDefault()
    emit('shortcuts')
  }
}

onMounted(() => window.addEventListener('keydown', onGlobalKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onGlobalKeydown))

defineExpose({ open })
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="t('commandPalette.title')"
    width="600px"
    append-to-body
    class="command-palette"
    @opened="focusInput"
  >
    <el-input
      ref="inputRef"
      v-model="query"
      :placeholder="t('commandPalette.placeholder')"
      :aria-label="t('commandPalette.placeholder')"
      role="combobox"
      aria-controls="command-palette-list"
      :aria-expanded="true"
      @keydown="onInputKeydown"
    />
    <div
      id="command-palette-list"
      class="command-palette__list"
      role="listbox"
      :aria-label="t('commandPalette.title')"
    >
      <button
        v-for="(command, index) in filtered"
        :id="`command-${command.id}`"
        :key="command.id"
        type="button"
        role="option"
        class="command-palette__item"
        :class="{ 'is-active': index === selectedIndex, 'is-disabled': command.disabled }"
        :aria-selected="index === selectedIndex"
        :disabled="command.disabled"
        @mousemove="selectedIndex = index"
        @click="runCommand(command)"
      >
        <span>{{ command.label }}</span>
        <span class="command-palette__group">{{ t(`commandPalette.group.${command.group}`) }}</span>
      </button>
      <p v-if="filtered.length === 0" class="command-palette__empty">
        {{ t('commandPalette.empty') }}
      </p>
    </div>
    <p class="command-palette__hint">↑ ↓ · Enter · Esc</p>
  </el-dialog>
</template>

<style scoped>
.command-palette__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 360px;
  margin-top: 10px;
  overflow: auto;
}

.command-palette__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 8px 10px;
  border: 0;
  border-radius: var(--vs-radius-sm);
  background: transparent;
  color: var(--vs-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.command-palette__item:hover,
.command-palette__item.is-active {
  background: var(--vs-accent-soft);
}

.command-palette__item.is-disabled {
  color: var(--vs-text-faint);
  cursor: default;
}

.command-palette__group {
  font-size: 11px;
  color: var(--vs-text-faint);
}

.command-palette__empty {
  padding: 12px 10px;
  font-size: 13px;
  color: var(--vs-text-faint);
}

.command-palette__hint {
  margin: 10px 2px 0;
  font-size: 11px;
  color: var(--vs-text-faint);
  text-align: right;
}
</style>
