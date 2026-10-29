import { describe, expect, it } from 'vitest'

import enUS from './locales/en-US'
import zhCN from './locales/zh-CN'

function flatten(value: unknown, prefix = ''): string[] {
  if (value === null || typeof value !== 'object') return [prefix]
  return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
    flatten(child, prefix ? `${prefix}.${key}` : key),
  )
}

function missing(source: unknown, target: unknown): string[] {
  const keys = new Set(flatten(target))
  return flatten(source).filter((key) => !keys.has(key))
}

describe('locale key parity', () => {
  it('zh-CN and en-US expose the same message keys', () => {
    expect(missing(zhCN, enUS)).toEqual([])
    expect(missing(enUS, zhCN)).toEqual([])
  })
})
