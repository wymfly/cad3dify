import { test, expect } from '@playwright/test';
import { mockCommonApis, mockJobList } from './fixtures/base';
import { MOCK_JOB_LIST_EMPTY } from './fixtures/mock-data';

test.describe('旧路由重定向', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommonApis(page);
    await mockJobList(page, MOCK_JOB_LIST_EMPTY);
  });

  test('6.1 /generate → /precision', async ({ page }) => {
    await page.goto('/generate');
    await expect(page).toHaveURL(/\/precision/);
  });

  test('6.2 /generate/organic → /organic', async ({ page }) => {
    await page.goto('/generate/organic');
    await expect(page).toHaveURL(/\/organic/);
  });

  test('6.3 /history → /library', async ({ page }) => {
    await page.goto('/history');
    await expect(page).toHaveURL(/\/library/);
  });
});
