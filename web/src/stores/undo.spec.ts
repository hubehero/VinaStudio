import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { UNDO_LIMIT, useUndoStore } from './undo'

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('undo stack', () => {
  it('undoes the latest action first and reports success', async () => {
    const values: string[] = []
    const undo = useUndoStore()
    undo.push('first', () => { values.push('first') })
    undo.push('second', () => { values.push('second') })

    expect(undo.lastLabel).toBe('second')
    expect(await undo.undoLast()).toBe(true)
    expect(values).toEqual(['second'])
    expect(await undo.undoLast()).toBe(true)
    expect(values).toEqual(['second', 'first'])
    expect(await undo.undoLast()).toBe(false)
  })

  it('keeps the stack bounded', () => {
    const undo = useUndoStore()
    for (let i = 0; i < UNDO_LIMIT + 5; i += 1) undo.push(`entry ${i}`, () => {})
    expect(undo.stack).toHaveLength(UNDO_LIMIT)
    expect(undo.stack[0]?.label).toBe('entry 5')
  })

  it('drops an entry when its restore callback fails', async () => {
    const undo = useUndoStore()
    undo.push('broken', () => {
      throw new Error('restore failed')
    })
    expect(await undo.undoLast()).toBe(false)
    expect(undo.canUndo).toBe(false)
  })
})
