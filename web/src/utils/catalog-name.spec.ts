import { describe, expect, it } from 'vitest'

import { chineseAlias } from './catalog-name'

describe('chineseAlias', () => {
  it('returns the first CJK alias', () => {
    expect(chineseAlias(['raloxifene', '雷洛昔芬', 'Evista'])).toBe('雷洛昔芬')
  })

  it('returns null when no alias is Chinese', () => {
    expect(chineseAlias(['raloxifene', 'Evista'])).toBeNull()
    expect(chineseAlias([])).toBeNull()
    expect(chineseAlias(null)).toBeNull()
  })
})
