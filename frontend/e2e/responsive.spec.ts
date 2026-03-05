import { test, expect } from '@playwright/test';
import { mockCommonApis, mockJobList } from './fixtures/base';
import { MOCK_JOB_LIST_EMPTY } from './fixtures/mock-data';

test.describe('响应式布局', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommonApis(page);
    await mockJobList(page, MOCK_JOB_LIST_EMPTY);
  });

  test('7.1 移动端无侧面板', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/precision');

    // 移动端下左面板内容 "输入方式" 不直接可见（在 Drawer 中）
    await expect(page.getByText('输入方式')).not.toBeVisible();
  });

  test('7.2 移动端浮动按钮出现', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/precision');

    // 应出现浮动按钮（fixed 定位的 button）
    const floatingButtons = page.locator('button[style*="fixed"]');
    await expect(floatingButtons.first()).toBeVisible();
  });

  test('7.3 移动端左侧 Drawer 弹出', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/precision');

    // 点击左浮动按钮（带 RightOutlined 图标）
    const leftBtn = page.locator('button[style*="fixed"][style*="left"]');
    await leftBtn.click();

    // Drawer 弹出，标题为"操作面板"
    await expect(page.getByText('操作面板')).toBeVisible();
  });

  test('7.4 移动端右侧 Drawer 弹出', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/precision');

    // 点击右浮动按钮
    const rightBtn = page.locator('button[style*="fixed"][style*="right"]');
    await rightBtn.click();

    // Drawer 弹出，标题为"详情"
    await expect(page.getByText('详情')).toBeVisible();
  });

  test('7.5 桌面端三栏布局正常', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto('/precision');

    // 桌面端左面板内容直接可见
    await expect(page.getByText('输入方式')).toBeVisible();
    // 右面板内容直接可见
    await expect(page.getByText('快速入门')).toBeVisible();
    // 中央 canvas 可见
    await expect(page.locator('canvas')).toBeVisible();
  });
});
