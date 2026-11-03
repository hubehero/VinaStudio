import { expect, test } from '@playwright/test'

/**
 * Browser smoke against the production SPA, not the Vite dev server.
 *
 * It uses a fresh temporary workspace initialised through the API so the test
 * never reads or mutates a real user workspace.  It deliberately stops before
 * a real docking run: the full 1IEP scientific chain remains a pytest concern.
 */
test.beforeEach(async ({ request, page }) => {
  // The browser locale is English in CI; pin the product's default locale so
  // the smoke's user-visible landmarks are deterministic.
  await page.addInitScript(() => {
    localStorage.setItem('vinastudio.locale', 'zh-CN')
  })
  const workspace = `/tmp/vinastudio-e2e-${Date.now()}-${Math.random().toString(36).slice(2)}`
  const response = await request.post('/api/workspace/init', {
    data: { path: workspace, name: 'E2E workspace' },
  })
  expect(response.ok()).toBeTruthy()
})

test('primary routes render on the production bundle', async ({ page }) => {
  const landmarks: Array<[string, string]> = [
    ['workbench', '对接流程'],
    ['molecules', '分子目录'],
    ['box', '结合位点盒子'],
    ['docking', '参数'],
    ['report', '结果汇报'],
    ['batch', '批量筛选'],
    ['screening', '虚拟筛选工作台'],
    ['results', '历史检索'],
    ['environment', '环境自检'],
    ['help', '使用帮助'],
    ['about', '关于'],
  ]

  for (const [route, landmark] of landmarks) {
    await page.goto(`/#/${route}`)
    await expect(page.getByText(landmark, { exact: false }).first()).toBeVisible()
    await expect(page.locator('body')).not.toContainText('Internal Server Error')
  }
})

test('environment diagnostics runs in the production bundle', async ({ page }) => {
  await page.goto('/#/environment')
  const button = page.getByRole('button', { name: '诊断并修复' })
  await expect(button).toBeEnabled()
  await button.click()
  await expect(page.getByText(/项检查/)).toBeVisible({ timeout: 20_000 })
})
