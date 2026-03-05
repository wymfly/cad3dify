import { test, expect } from '@playwright/test';
import { mockCommonApis, mockJobList } from './fixtures/base';
import { MOCK_JOB_LIST_EMPTY } from './fixtures/mock-data';

test.describe('创意雕塑工作台', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommonApis(page);
    await mockJobList(page, MOCK_JOB_LIST_EMPTY);
    // 拦截 organic generate API
    await page.route('**/api/v1/organic', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          job_id: 'organic-001',
          status: 'completed',
          model_url: '/outputs/organic-001/model.glb',
          stl_url: '/outputs/organic-001/model.stl',
          threemf_url: '/outputs/organic-001/model.3mf',
          mesh_stats: { vertices: 1200, faces: 2400, volume_mm3: 5000, is_watertight: true },
          printability: {
            printable: true,
            score: 0.88,
            issues: [],
            material_estimate: { filament_weight_g: 30, filament_length_m: 10, cost_estimate_cny: 8 },
            time_estimate: { total_minutes: 90, layer_count: 300 },
          },
        }),
      });
    });
  });

  test('4.1 Idle 左面板 - 输入和设置区可见', async ({ page }) => {
    await page.goto('/organic');

    // 文本描述输入
    await expect(page.getByText('文本描述', { exact: true })).toBeVisible();
    await expect(page.getByPlaceholder(/描述你想要的 3D 模型/)).toBeVisible();

    // 参考图片上传
    await expect(page.getByText('参考图片', { exact: false }).first()).toBeVisible();

    // 工程约束
    await expect(page.getByText('工程约束', { exact: true })).toBeVisible();
    await expect(page.getByText('包围盒尺寸', { exact: false }).first()).toBeVisible();

    // 生成设置
    await expect(page.getByText('生成设置')).toBeVisible();

    // 生成按钮
    await expect(page.getByRole('button', { name: '生成' })).toBeVisible();
  });

  test('4.2 生成按钮无输入时禁用', async ({ page }) => {
    await page.goto('/organic');

    const genBtn = page.getByRole('button', { name: '生成' });
    await expect(genBtn).toBeDisabled();
  });

  test('4.3 输入文字后生成按钮启用', async ({ page }) => {
    await page.goto('/organic');

    await page.getByPlaceholder(/描述你想要的 3D 模型/).fill('流线型花瓶');

    const genBtn = page.getByRole('button', { name: '生成' });
    await expect(genBtn).toBeEnabled();
  });

  test('4.4 Idle 右面板 - 创意雕塑指南', async ({ page }) => {
    await page.goto('/organic');

    await expect(page.getByRole('heading', { name: '创意雕塑' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '示例' })).toBeVisible();
    await expect(page.getByText(/流线型花瓶，底部宽顶部窄/)).toBeVisible();
  });

  test('4.5 约束表单 - 添加工程切割', async ({ page }) => {
    await page.goto('/organic');

    // 点击添加切割按钮
    await page.getByRole('button', { name: '添加' }).click();

    // 切割类型选择器出现
    await expect(page.getByText('平底切割')).toBeVisible();
    // 偏移输入出现
    await expect(page.getByText('偏移')).toBeVisible();
  });

  test('4.6 清空输入后生成按钮再次禁用', async ({ page }) => {
    await page.goto('/organic');

    const textarea = page.getByPlaceholder(/描述你想要的 3D 模型/);
    const genBtn = page.getByRole('button', { name: '生成' });

    // 输入 → 启用
    await textarea.fill('花瓶');
    await expect(genBtn).toBeEnabled();

    // 清空 → 禁用
    await textarea.fill('');
    await expect(genBtn).toBeDisabled();
  });
});
