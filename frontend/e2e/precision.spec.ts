import { test, expect } from '@playwright/test';
import {
  mockCommonApis,
  mockJobCreateSSE,
  mockJobConfirmSSE,
  mockJobList,
  mockJobEventsEmpty,
} from './fixtures/base';
import {
  SSE_TEXT_FLOW_EVENTS,
  SSE_COMPLETED_EVENTS,
  SSE_FAILED_EVENTS,
  MOCK_JOB_LIST_EMPTY,
} from './fixtures/mock-data';

test.describe('精密建模工作台', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommonApis(page);
    await mockJobList(page, MOCK_JOB_LIST_EMPTY);
    await mockJobEventsEmpty(page);
  });

  test('3.1 Idle 左面板 - InputPanel 可见', async ({ page }) => {
    await page.goto('/precision');

    // 输入方式选择器（Segmented）
    await expect(page.getByText('输入方式', { exact: true })).toBeVisible();
    await expect(page.getByText('文本描述', { exact: true })).toBeVisible();
    await expect(page.getByText('工程图纸', { exact: true })).toBeVisible();

    // 文本输入区
    await expect(page.getByPlaceholder(/描述你想要的零件/)).toBeVisible();

    // 生成按钮
    await expect(page.getByRole('button', { name: '生成模型' })).toBeVisible();
  });

  test('3.2 Idle 右面板 - 快速入门可见', async ({ page }) => {
    await page.goto('/precision');

    await expect(page.getByText('快速入门')).toBeVisible();
    await expect(page.getByText('示例')).toBeVisible();
    await expect(page.getByText(/做一个外径100mm的法兰盘/)).toBeVisible();
  });

  test('3.3 Idle 中央区 - Viewer3D 存在', async ({ page }) => {
    await page.goto('/precision');

    // Three.js 渲染到 canvas
    const canvas = page.locator('canvas');
    await expect(canvas).toBeVisible();
  });

  test('3.4 文本输入触发生成 - API 被调用', async ({ page }) => {
    // 拦截 POST /api/v1/jobs 并记录调用
    let apiCalled = false;
    await page.route('**/api/v1/jobs', async (route) => {
      if (route.request().method() === 'POST') {
        apiCalled = true;
        const body = route.request().postDataJSON();
        expect(body.input_type).toBe('text');
        expect(body.text).toContain('法兰盘');
        // 返回 SSE 流
        const sseBody = SSE_TEXT_FLOW_EVENTS
          .map((evt) => `data: ${JSON.stringify(evt)}\n\n`)
          .join('');
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: sseBody,
        });
      } else {
        await route.fallback();
      }
    });

    await page.goto('/precision');
    await page.getByPlaceholder(/描述你想要的零件/).fill('法兰盘，外径100mm');
    await page.getByRole('button', { name: '生成模型' }).click();

    // 等待 API 被调用
    await expect.poll(() => apiCalled).toBe(true);
  });

  test('3.5 意图解析完成 → 进入参数确认阶段', async ({ page }) => {
    await mockJobCreateSSE(page, SSE_TEXT_FLOW_EVENTS);

    await page.goto('/precision');
    await page.getByPlaceholder(/描述你想要的零件/).fill('法兰盘');
    await page.getByRole('button', { name: '生成模型' }).click();

    // SSE 返回 intent_parsed → 左面板应显示参数确认表单
    await expect(page.getByText('参数确认')).toBeVisible({ timeout: 5000 });
    // 应显示 "确认参数" 按钮和参数标签（3 个参数）
    await expect(page.getByRole('button', { name: '确认参数' })).toBeVisible();
    await expect(page.getByText('3 个参数')).toBeVisible();
  });

  test('3.6 生成完成 → DownloadPanel 可见', async ({ page }) => {
    // 先进入参数确认阶段
    await mockJobCreateSSE(page, SSE_TEXT_FLOW_EVENTS);

    await page.goto('/precision');
    await page.getByPlaceholder(/描述你想要的零件/).fill('法兰盘');
    await page.getByRole('button', { name: '生成模型' }).click();

    // 等待参数确认阶段
    await expect(page.getByText('参数确认')).toBeVisible({ timeout: 5000 });

    // 设置 confirm 的 mock
    await mockJobConfirmSSE(page, SSE_COMPLETED_EVENTS);

    // 点击确认参数
    await page.getByRole('button', { name: '确认参数' }).click();

    // 等待完成 → DownloadPanel 出现
    await expect(page.getByText(/下载/)).toBeVisible({ timeout: 5000 });
  });

  test('3.7 生成完成 → 右面板显示 DfAM 报告', async ({ page }) => {
    await mockJobCreateSSE(page, SSE_TEXT_FLOW_EVENTS);

    await page.goto('/precision');
    await page.getByPlaceholder(/描述你想要的零件/).fill('法兰盘');
    await page.getByRole('button', { name: '生成模型' }).click();

    await expect(page.getByText('参数确认')).toBeVisible({ timeout: 5000 });

    await mockJobConfirmSSE(page, SSE_COMPLETED_EVENTS);
    await page.getByRole('button', { name: '确认参数' }).click();

    // 右面板显示可打印性报告（PrintReport 组件）
    await expect(page.getByText(/可打印性/i).or(page.getByText('生成完成'))).toBeVisible({ timeout: 5000 });
  });

  test('3.8 生成失败 → 重新开始按钮', async ({ page }) => {
    await mockJobCreateSSE(page, SSE_FAILED_EVENTS);

    await page.goto('/precision');
    await page.getByPlaceholder(/描述你想要的零件/).fill('错误的零件');
    await page.getByRole('button', { name: '生成模型' }).click();

    // 失败后显示错误信息和重新开始按钮
    await expect(page.getByText('重新开始')).toBeVisible({ timeout: 5000 });

    // 点击重新开始 → 回到 idle
    await page.getByRole('button', { name: '重新开始' }).click();
    await expect(page.getByText('输入方式')).toBeVisible();
  });

  test('3.9 切换到图纸模式 → 上传区域可见', async ({ page }) => {
    await page.goto('/precision');

    // 点击"工程图纸"模式（Segmented 选项）
    await page.getByText('工程图纸', { exact: true }).click();

    // 上传区域出现
    await expect(page.getByText(/点击或拖拽上传工程图纸/)).toBeVisible();

    // 按钮文案变为"分析图纸"
    await expect(page.getByRole('button', { name: '分析图纸' })).toBeVisible();
  });
});
