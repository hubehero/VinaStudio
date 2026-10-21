import { beforeEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

import { useSettingsStore } from './settings'

const STORAGE_KEY = 'vinastudio-settings'

function seed(payload: unknown): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
}

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
})

describe('viewer settings migration', () => {
  it('takes the antialias-off default for a v1 payload', () => {
    seed({ viewer: { antialiasOff: false, renderQuality: 'high' } })

    const settings = useSettingsStore()

    // A v1 payload stored the old false default wholesale, so it cannot prove
    // the user wanted AA on. It takes the new default exactly once.
    expect(settings.viewer.antialiasOff).toBe(true)
    expect(settings.viewer.renderQuality).toBe('high')
  })

  it('keeps an explicit v2 choice', () => {
    seed({ version: 2, viewer: { antialiasOff: false } })

    expect(useSettingsStore().viewer.antialiasOff).toBe(false)
  })

  it('keeps an absent v2 value on the current default', () => {
    seed({ version: 2, viewer: {} })

    expect(useSettingsStore().viewer.antialiasOff).toBe(true)
  })

  it('starts from the current defaults with no stored payload', () => {
    const settings = useSettingsStore()

    expect(settings.viewer.antialiasOff).toBe(true)
    expect(settings.viewer.adaptiveAO).toBe(true)
    expect(settings.viewer.renderQuality).toBe('medium')
    expect(settings.molecules.viewMode).toBe('type')
  })

  it('writes the current schema version back when a value changes', async () => {
    const settings = useSettingsStore()
    settings.viewer.antialiasOff = false
    await nextTick()

    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as {
      version?: number
      viewer?: { antialiasOff?: boolean }
    }
    expect(stored.version).toBe(2)
    expect(stored.viewer?.antialiasOff).toBe(false)
  })
})
