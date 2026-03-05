import { test, expect } from '@playwright/test';
import { mockCommonApis, mockJobList, mockJobDetail } from './fixtures/base';
import { MOCK_JOB_LIST, MOCK_JOB_LIST_EMPTY, MOCK_JOB_DETAIL } from './fixtures/mock-data';

test.describe('零件库', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommonApis(page);
  });

  test('5.1 空状态提示', async ({ page }) => {
    await mockJobList(page, MOCK_JOB_LIST_EMPTY);
    await page.goto('/library');

    await expect(page.getByText('暂无生成记录')).toBeVisible();
  });

  test('5.2 左面板筛选器可见', async ({ page }) => {
    await mockJobList(page, MOCK_JOB_LIST);
    await page.goto('/library');

    // 搜索输入框
    await expect(page.getByPlaceholder('搜索零件名称...')).toBeVisible();
    // 状态下拉
    await expect(page.getByText('全部状态')).toBeVisible();
    // 类型下拉
    await expect(page.getByText('全部类型')).toBeVisible();
    // 记录数
    await expect(page.getByText('共 4 条记录')).toBeVisible();
  });

  test('5.3 右面板帮助文本', async ({ page }) => {
    await mockJobList(page, MOCK_JOB_LIST);
    await page.goto('/library');

    await expect(page.getByText('零件库').first()).toBeVisible();
    await expect(page.getByText(/浏览历史生成的 3D 模型/)).toBeVisible();
    await expect(page.getByText(/使用左侧筛选器缩小范围/)).toBeVisible();
  });

  test('5.4 卡片网格展示', async ({ page }) => {
    await mockJobList(page, MOCK_JOB_LIST);
    await page.goto('/library');

    // 应显示 4 张卡片（根据 mock 数据）
    const cards = page.locator('.ant-card');
    await expect(cards).toHaveCount(4);
  });

  test('5.5 状态筛选发送正确请求', async ({ page }) => {
    let lastRequestUrl = '';
    await page.route('**/api/v1/jobs**', async (route) => {
      if (route.request().method() === 'GET') {
        lastRequestUrl = route.request().url();
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_JOB_LIST),
        });
      } else {
        await route.fallback();
      }
    });

    await page.goto('/library');
    await page.waitForTimeout(500);

    // 点击状态选择器并选择"已完成"
    await page.getByText('全部状态').click();
    await page.getByTitle('已完成').click();

    // 验证请求包含 status 参数
    await expect.poll(() => lastRequestUrl).toContain('status=completed');
  });

  test('5.6 类型筛选发送正确请求', async ({ page }) => {
    let lastRequestUrl = '';
    await page.route('**/api/v1/jobs**', async (route) => {
      if (route.request().method() === 'GET') {
        lastRequestUrl = route.request().url();
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_JOB_LIST),
        });
      } else {
        await route.fallback();
      }
    });

    await page.goto('/library');
    await page.waitForTimeout(500);

    // 点击类型选择器并选择"文本生成"
    await page.getByText('全部类型').click();
    await page.getByTitle('文本生成').click();

    await expect.poll(() => lastRequestUrl).toContain('input_type=text');
  });

  test('5.7 关键词搜索客户端过滤', async ({ page }) => {
    await mockJobList(page, MOCK_JOB_LIST);
    await page.goto('/library');

    // 等待卡片加载
    await expect(page.locator('.ant-card')).toHaveCount(4);

    // 搜索 "法兰盘"
    await page.getByPlaceholder('搜索零件名称...').fill('法兰盘');

    // 应只显示 1 张匹配的卡片
    await expect(page.locator('.ant-card')).toHaveCount(1);
  });

  test('5.8 点击卡片导航到详情页', async ({ page }) => {
    await mockJobList(page, MOCK_JOB_LIST);
    await mockJobDetail(page, 'job-a1', MOCK_JOB_DETAIL);

    await page.goto('/library');

    // 点击第一张卡片
    await page.locator('.ant-card').first().click();

    // 导航到详情页
    await expect(page).toHaveURL(/\/library\/job-a1/);
  });
});
