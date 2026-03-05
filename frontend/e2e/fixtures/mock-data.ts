/**
 * 预设的 API mock 响应数据，供 E2E 测试使用。
 */

/** SSE 事件：文本生成完整流程 */
export const SSE_TEXT_FLOW_EVENTS = [
  { job_id: 'job-001', status: 'created', message: 'Job 已创建' },
  {
    job_id: 'job-001',
    status: 'intent_parsed',
    message: '意图解析完成',
    template_name: 'flange',
    params: [
      { name: 'outer_diameter', display_name: '外径', param_type: 'float', default: 100, unit: 'mm' },
      { name: 'inner_diameter', display_name: '内径', param_type: 'float', default: 50, unit: 'mm' },
      { name: 'thickness', display_name: '厚度', param_type: 'float', default: 15, unit: 'mm' },
    ],
  },
];

/** SSE 事件：生成完成 */
export const SSE_COMPLETED_EVENTS = [
  { job_id: 'job-001', status: 'generating', message: '正在生成 3D 模型…' },
  { job_id: 'job-001', status: 'refining', message: '正在优化模型…' },
  {
    job_id: 'job-001',
    status: 'completed',
    message: '生成完成',
    model_url: '/outputs/job-001/model.glb',
    step_path: 'outputs/job-001/model.step',
    printability: {
      printable: true,
      score: 0.92,
      issues: [],
      material_estimate: { filament_weight_g: 45.2, filament_length_m: 15.1, cost_estimate_cny: 12.5 },
      time_estimate: { total_minutes: 120, layer_count: 450 },
    },
  },
];

/** SSE 事件：生成失败 */
export const SSE_FAILED_EVENTS = [
  { job_id: 'job-err', status: 'created', message: 'Job 已创建' },
  { job_id: 'job-err', status: 'failed', message: 'CadQuery 代码执行失败：语法错误' },
];

/** 零件库列表：混合状态 */
export const MOCK_JOB_LIST = {
  items: [
    {
      job_id: 'job-a1',
      status: 'completed',
      input_type: 'text' as const,
      input_text: '法兰盘，外径100mm',
      created_at: '2026-02-28T10:00:00Z',
      result: { model_url: '/outputs/job-a1/model.glb' },
    },
    {
      job_id: 'job-a2',
      status: 'completed',
      input_type: 'drawing' as const,
      input_text: '阶梯轴图纸',
      created_at: '2026-02-28T09:30:00Z',
      result: { model_url: '/outputs/job-a2/model.glb' },
    },
    {
      job_id: 'job-a3',
      status: 'failed',
      input_type: 'text' as const,
      input_text: '齿轮模数2',
      created_at: '2026-02-28T09:00:00Z',
      result: null,
    },
    {
      job_id: 'job-a4',
      status: 'completed',
      input_type: 'text' as const,
      input_text: '轴承座',
      created_at: '2026-02-27T15:00:00Z',
      result: { model_url: '/outputs/job-a4/model.glb' },
    },
  ],
  total: 4,
  page: 1,
  page_size: 20,
};

/** 零件库列表：空 */
export const MOCK_JOB_LIST_EMPTY = {
  items: [],
  total: 0,
  page: 1,
  page_size: 20,
};

/** 零件详情 */
export const MOCK_JOB_DETAIL = {
  job_id: 'job-a1',
  status: 'completed',
  input_type: 'text' as const,
  input_text: '法兰盘，外径100mm',
  intent: { part_category: '法兰盘', part_type: 'rotational' },
  precise_spec: null,
  drawing_spec: null,
  result: { model_url: '/outputs/job-a1/model.glb', step_path: 'outputs/job-a1/model.step' },
  printability: {
    printable: true,
    score: 0.92,
    issues: [],
    material_estimate: { filament_weight_g: 45.2, filament_length_m: 15.1, cost_estimate_cny: 12.5 },
    time_estimate: { total_minutes: 120, layer_count: 450 },
  },
  error: null,
  created_at: '2026-02-28T10:00:00Z',
};
