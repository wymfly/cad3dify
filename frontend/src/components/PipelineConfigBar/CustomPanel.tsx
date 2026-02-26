import { Checkbox, Tooltip, InputNumber, Space, Row, Col } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import type { PipelineConfig, TooltipSpec } from '../../types/pipeline.ts';

interface CustomPanelProps {
  config: PipelineConfig;
  tooltips: Record<string, TooltipSpec>;
  onChange: (patch: Partial<PipelineConfig>) => void;
}

interface ToggleFieldDef {
  key: keyof PipelineConfig;
  label: string;
}

interface NumberFieldDef {
  key: keyof PipelineConfig;
  label: string;
  min: number;
  max: number;
}

const toggleFields: ToggleFieldDef[] = [
  { key: 'rag_enabled', label: 'RAG 增强' },
  { key: 'ocr_assist', label: 'OCR 辅助' },
  { key: 'two_pass_analysis', label: '两阶段分析' },
  { key: 'multi_model_voting', label: '多模型投票' },
  { key: 'api_whitelist', label: 'API 白名单' },
  { key: 'ast_pre_check', label: 'AST 预检查' },
  { key: 'volume_check', label: '体积验证' },
  { key: 'topology_check', label: '拓扑验证' },
  { key: 'cross_section_check', label: '截面分析' },
  { key: 'multi_view_render', label: '多视角渲染' },
  { key: 'structured_feedback', label: '结构化反馈' },
  { key: 'rollback_on_degrade', label: '退化回滚' },
  { key: 'contour_overlay', label: '轮廓叠加' },
  { key: 'printability_check', label: '可打印性检查' },
];

const numberFields: NumberFieldDef[] = [
  { key: 'best_of_n', label: '多路生成 (N)', min: 1, max: 10 },
  { key: 'self_consistency_runs', label: 'Self-Consistency 次数', min: 1, max: 5 },
  { key: 'max_refinements', label: '最大修复轮数', min: 0, max: 10 },
];

function renderTooltip(tooltips: Record<string, TooltipSpec>, key: string) {
  const tip = tooltips[key];
  if (!tip) return null;

  const content = (
    <div style={{ maxWidth: 280 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{tip.title}</div>
      <div>{tip.description}</div>
      {tip.when_to_use && (
        <div style={{ marginTop: 4, color: '#91caff' }}>
          适用场景: {tip.when_to_use}
        </div>
      )}
      {tip.cost && (
        <div style={{ marginTop: 2, color: '#ffccc7' }}>
          开销: {tip.cost}
        </div>
      )}
      {tip.default && (
        <div style={{ marginTop: 2, color: '#d9f7be' }}>
          默认: {tip.default}
        </div>
      )}
    </div>
  );

  return (
    <Tooltip title={content} placement="top">
      <QuestionCircleOutlined
        style={{ color: '#999', marginLeft: 4, cursor: 'help' }}
      />
    </Tooltip>
  );
}

export default function CustomPanel({ config, tooltips, onChange }: CustomPanelProps) {
  return (
    <div style={{ padding: '12px 0' }}>
      <Row gutter={[16, 8]}>
        {toggleFields.map((field) => (
          <Col key={field.key} xs={24} sm={12} md={8}>
            <Space size={4}>
              <Checkbox
                checked={config[field.key] as boolean}
                onChange={(e) => onChange({ [field.key]: e.target.checked })}
              >
                {field.label}
              </Checkbox>
              {renderTooltip(tooltips, field.key)}
            </Space>
          </Col>
        ))}
      </Row>
      <Row gutter={[16, 8]} style={{ marginTop: 12 }}>
        {numberFields.map((field) => (
          <Col key={field.key} xs={24} sm={12} md={8}>
            <Space size={4}>
              <span>{field.label}:</span>
              <InputNumber
                size="small"
                min={field.min}
                max={field.max}
                value={config[field.key] as number}
                onChange={(val) => {
                  if (val !== null) onChange({ [field.key]: val });
                }}
                style={{ width: 64 }}
              />
              {renderTooltip(tooltips, field.key)}
            </Space>
          </Col>
        ))}
      </Row>
    </div>
  );
}
