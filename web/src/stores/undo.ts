import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

/** A reversible user action; the callback must restore the earlier state. */
export interface UndoEntry {
  id: number
  label: string
  run: () => void | Promise<void>
}

export const UNDO_LIMIT = 20

export const useUndoStore = defineStore('undo', () => {
  const stack = ref<UndoEntry[]>([])
  let nextId = 1

  const canUndo = computed(() => stack.value.length > 0)
  const lastLabel = computed(() => stack.value.at(-1)?.label ?? '')

  function push(label: string, run: () => void | Promise<void>): void {
    stack.value.push({ id: nextId++, label, run })
    if (stack.value.length > UNDO_LIMIT) stack.value.shift()
  }

  async function undoLast(): Promise<boolean> {
    const entry = stack.value.pop()
    if (!entry) return false
    try {
      await entry.run()
      return true
    } catch {
      return false
    }
  }

  function clear(): void {
    stack.value = []
  }

  return { stack, canUndo, lastLabel, push, undoLast, clear }
})
