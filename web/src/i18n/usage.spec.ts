// @vitest-environment node

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import enUS from './locales/en-US'
import zhCN from './locales/zh-CN'

function flatten(value: unknown, prefix = ''): string[] {
  if (value === null || typeof value !== 'object') return [prefix]
  return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
    flatten(child, prefix ? `${prefix}.${key}` : key),
  )
}

function sources(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    if (statSync(path).isDirectory()) return sources(path)
    if (!/\.(ts|vue)$/.test(path) || path.endsWith('.spec.ts')) return []
    return [path]
  })
}

function usedKeys(source: string): string[] {
  return [...source.matchAll(/\bt\(\s*['"]([^'"]+)['"]/g)].map(
    (match) => match[1] ?? '',
  )
}

describe('locale key usage', () => {
  it('every literal t() key exists in both locales', () => {
    const en = new Set(flatten(enUS))
    const zh = new Set(flatten(zhCN))
    const root = fileURLToPath(new URL('..', import.meta.url))
    const missing = sources(root).flatMap((path) => {
      const keys = usedKeys(readFileSync(path, 'utf8'))
      return keys
        .filter((key) => !en.has(key) || !zh.has(key))
        .map((key) => `${path.replace(root, '')}: ${key}`)
    })
    expect(missing).toEqual([])
  })
})
