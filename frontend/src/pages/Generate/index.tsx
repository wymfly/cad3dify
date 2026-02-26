import { useState, useCallback } from 'react';
import { Typography, Row, Col, Button, Space } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import PipelineConfigBar from '../../components/PipelineConfigBar/index.tsx';
import Viewer3D from '../../components/Viewer3D/index.tsx';
import ParamForm from '../../components/ParamForm/index.tsx';
import ChatInput from './ChatInput.tsx';
import GenerateWorkflow, { useGenerateWorkflow } from './GenerateWorkflow.tsx';
import type { ParamDefinition } from '../../types/template.ts';

const { Title, Paragraph } = Typography;

/** Placeholder params for the confirmation step (will be populated by IntentParser). */
const PLACEHOLDER_PARAMS: ParamDefinition[] = [
  {
    name: 'outer_diameter',
    display_name: '外径',
    unit: 'mm',
    param_type: 'float',
    range_min: 10,
    range_max: 500,
    default: 100,
  },
  {
    name: 'thickness',
    display_name: '厚度',
    unit: 'mm',
    param_type: 'float',
    range_min: 1,
    range_max: 200,
    default: 20,
  },
];

export default function Generate() {
  const {
    state: workflow,
    startTextGenerate,
    startDrawingGenerate,
    confirmParams,
    reset,
  } = useGenerateWorkflow();

  const [paramValues, setParamValues] = useState<
    Record<string, number | string | boolean>
  >({
    outer_diameter: 100,
    thickness: 20,
  });

  const handleParamChange = useCallback(
    (name: string, value: number | string | boolean) => {
      setParamValues((prev) => ({ ...prev, [name]: value }));
    },
    [],
  );

  const handleConfirm = useCallback(() => {
    const numericParams: Record<string, number> = {};
    for (const [k, v] of Object.entries(paramValues)) {
      if (typeof v === 'number') {
        numericParams[k] = v;
      }
    }
    confirmParams(numericParams);
  }, [paramValues, confirmParams]);

  const isInputDisabled =
    workflow.phase !== 'idle' && workflow.phase !== 'completed' && workflow.phase !== 'failed';

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
        }}
      >
        <div>
          <Title level={3} style={{ margin: 0 }}>
            生成 3D 模型
          </Title>
          <Paragraph type="secondary" style={{ margin: 0 }}>
            描述零件或上传工程图纸，AI 自动生成 3D CAD 模型
          </Paragraph>
        </div>
        {workflow.phase !== 'idle' && (
          <Button icon={<ReloadOutlined />} onClick={reset}>
            重新开始
          </Button>
        )}
      </div>

      <Row gutter={24}>
        {/* Left panel: input + params */}
        <Col xs={24} lg={10}>
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            {/* Chat input */}
            <ChatInput
              onSendText={startTextGenerate}
              onSendImage={startDrawingGenerate}
              disabled={isInputDisabled}
              loading={workflow.phase === 'parsing'}
            />

            {/* Workflow progress */}
            <GenerateWorkflow
              state={workflow}
              onPhaseChange={() => {}}
            />

            {/* Parameter confirmation form (shown during confirming phase) */}
            {workflow.phase === 'confirming' && (
              <ParamForm
                params={PLACEHOLDER_PARAMS}
                values={paramValues}
                onChange={handleParamChange}
                onConfirm={handleConfirm}
                onReset={() =>
                  setParamValues({ outer_diameter: 100, thickness: 20 })
                }
                title="参数确认"
              />
            )}

            {/* Pipeline config (collapsed) */}
            <PipelineConfigBar />
          </Space>
        </Col>

        {/* Right panel: 3D preview */}
        <Col xs={24} lg={14}>
          <div style={{ height: 600 }}>
            <Viewer3D modelUrl={workflow.modelUrl} />
          </div>
        </Col>
      </Row>
    </div>
  );
}
