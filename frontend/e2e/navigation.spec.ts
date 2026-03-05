import { test, expect } from '@playwright/test';
import { mockCommonApis, mockJobList } from './fixtures/base';
import { MOCK_JOB_LIST_EMPTY } from './fixtures/mock-data';

test.describe('导航与三栏布局', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommonApis(page);
    await mockJobList(page, MOCK_JOB_LIST_EMPTY);
  });

  test('1.1 默认路由重定向到 /precision', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/precision/);
  });

  test('1.2 Tab 导航 - 精密建模', async ({ page }) => {
    await page.goto('/organic');
    await page.getByRole('button', { name: '精密建模' }).click();
    await expect(page).toHaveURL(/\/precision/);
  });

  test('1.3 Tab 导航 - 创意雕塑', async ({ page }) => {
    await page.goto('/precision');
    await page.getByRole('button', { name: '创意雕塑' }).click();
    await expect(page).toHaveURL(/\/organic/);
  });

  test('1.4 Tab 导航 - 零件库', async ({ page }) => {
    await page.goto('/precision');
    await page.getByRole('button', { name: '零件库' }).click();
    await expect(page).toHaveURL(/\/library/);
  });

  test('1.5 Logo 点击导航到 /precision', async ({ page }) => {
    await page.goto('/library');
    await page.getByText('CAD3Dify').click();
    await expect(page).toHaveURL(/\/precision/);
  });

  test('1.6 三栏布局可见', async ({ page }) => {
    await page.goto('/precision');

    // TopNav 存在
    const header = page.locator('header');
    await expect(header).toBeVisible();

    // 文本 "CAD3Dify" 在 header 中
    await expect(header.getByText('CAD3Dify')).toBeVisible();

    // 三个 Tab 按钮
    await expect(page.getByRole('button', { name: '精密建模' })).toBeVisible();
    await expect(page.getByRole('button', { name: '创意雕塑' })).toBeVisible();
    await expect(page.getByRole('button', { name: '零件库' })).toBeVisible();
  });

  test('1.7 左面板折叠', async ({ page }) => {
    await page.goto('/precision');

    // 左面板内容可见（"输入方式" 文字来自 InputPanel）
    await expect(page.getByText('输入方式')).toBeVisible();

    // 点击左面板折叠按钮（第一个带有 LeftOutlined 图标的按钮）
    const leftCollapseBtn = page.locator('button').filter({ has: page.locator('[aria-label="left"]') }).first();
    await leftCollapseBtn.click();

    // 左面板内容隐藏
    await expect(page.getByText('输入方式')).not.toBeVisible();
  });

  test('1.8 右面板折叠', async ({ page }) => {
    await page.goto('/precision');

    // 右面板内容可见
    await expect(page.getByText('快速入门')).toBeVisible();

    // 点击右面板折叠按钮
    const rightCollapseBtn = page.locator('button').filter({ has: page.locator('[aria-label="right"]') }).first();
    await rightCollapseBtn.click();

    // 右面板内容隐藏
    await expect(page.getByText('快速入门')).not.toBeVisible();
  });

  test('1.9 折叠状态刷新后持久化', async ({ page }) => {
    await page.goto('/precision');

    // 折叠左面板
    const leftCollapseBtn = page.locator('button').filter({ has: page.locator('[aria-label="left"]') }).first();
    await leftCollapseBtn.click();
    await expect(page.getByText('输入方式')).not.toBeVisible();

    // 刷新页面
    await page.reload();

    // 左面板仍然折叠
    await expect(page.getByText('输入方式')).not.toBeVisible();
  });
});
