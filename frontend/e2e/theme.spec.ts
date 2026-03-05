import { test, expect } from '@playwright/test';
import { mockCommonApis, mockJobList } from './fixtures/base';
import { MOCK_JOB_LIST_EMPTY } from './fixtures/mock-data';

test.describe('亮暗主题切换', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommonApis(page);
    await mockJobList(page, MOCK_JOB_LIST_EMPTY);
    // 清除主题偏好，确保从默认亮色开始
    await page.addInitScript(() => localStorage.removeItem('cadpilot-theme'));
  });

  test('2.1 默认亮色主题', async ({ page }) => {
    await page.goto('/precision');

    const header = page.locator('header');
    const bg = await header.evaluate((el) => getComputedStyle(el).backgroundColor);
    // 亮色模式 header 背景应为白色系 (rgb(255, 255, 255))
    expect(bg).toMatch(/rgb\(255,\s*255,\s*255\)/);
  });

  test('2.2 切换到暗色主题', async ({ page }) => {
    await page.goto('/precision');

    // 点击主题切换按钮（MoonOutlined 图标按钮）
    const themeBtn = page.locator('header button').filter({ has: page.locator('[aria-label="moon"]') });
    await themeBtn.click();

    // header 背景变为深色
    const header = page.locator('header');
    const bg = await header.evaluate((el) => getComputedStyle(el).backgroundColor);
    // 暗色模式：#1f1f1f = rgb(31, 31, 31)
    expect(bg).toMatch(/rgb\(31,\s*31,\s*31\)/);
  });

  test('2.3 再次切换回亮色', async ({ page }) => {
    await page.goto('/precision');

    const themeBtn = page.locator('header button').last();
    // 切到暗色
    await themeBtn.click();
    // 切回亮色（暗色时图标变为 SunOutlined）
    await themeBtn.click();

    const header = page.locator('header');
    const bg = await header.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(bg).toMatch(/rgb\(255,\s*255,\s*255\)/);
  });

  test('2.4 暗色主题刷新后持久化', async ({ browser }) => {
    // 用新 context 避免 beforeEach 的 addInitScript 清除 localStorage
    const context = await browser.newContext();
    const page = await context.newPage();
    await mockCommonApis(page);
    await mockJobList(page, MOCK_JOB_LIST_EMPTY);

    await page.goto('/precision');

    // 切到暗色
    const themeBtn = page.locator('header button').filter({ has: page.locator('[aria-label="moon"]') });
    await themeBtn.click();

    // 刷新（不会执行 addInitScript 因为是独立 context）
    await page.reload();

    // 仍为暗色
    const header = page.locator('header');
    const bg = await header.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(bg).toMatch(/rgb\(31,\s*31,\s*31\)/);

    await context.close();
  });

  test('2.5 暗色主题 localStorage 正确', async ({ page }) => {
    await page.goto('/precision');

    // 默认 light
    let theme = await page.evaluate(() => localStorage.getItem('cadpilot-theme'));
    expect(theme).toBeNull(); // 默认不写入

    // 切到暗色
    const themeBtn = page.locator('header button').filter({ has: page.locator('[aria-label="moon"]') });
    await themeBtn.click();

    theme = await page.evaluate(() => localStorage.getItem('cadpilot-theme'));
    expect(theme).toBe('dark');
  });
});
