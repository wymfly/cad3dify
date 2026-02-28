import { useState, useEffect } from 'react';
import { Steps, Typography, Space } from 'antd';
import {
  LoadingOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  EditOutlined,
  RocketOutlined,
  ToolOutlined,
  SafetyOutlined,
} from '@ant-design/icons';
import type { WorkflowPhase } from '../../types/generate.ts';

const { Text } = Typography;

interface StageInfo {
  title: string;
  icon: React.ReactNode;
}

const STAGES: StageInfo[] = [
  { title: '意图解析', icon: <ToolOutlined /> },
  { title: '参数确认', icon: <EditOutlined /> },
  { title: '模型生成', icon: <RocketOutlined /> },
  { title: '模型优化', icon: <LoadingOutlined /> },
  { title: '质量检查', icon: <SafetyOutlined /> },
  { title: '完成', icon: <CheckCircleOutlined /> },
];

const PHASE_TO_STEP: Record<WorkflowPhase, number> = {
  idle: -1,
  parsing: 0,
  confirming: 1,
  drawing_review: 1,
  generating: 2,
  refining: 3,
  completed: 5,
  failed: -1,
};

export interface PipelineProgressProps {
  phase: WorkflowPhase;
  message?: string;
  startTime?: number;
  error?: string | null;
}

export default function PipelineProgress({
  phase,
  message,
  startTime,
  error,
}: PipelineProgressProps) {
  // 记住 failed 之前的最后活跃步骤，使错误图标正确渲染
  const [lastActiveStep, setLastActiveStep] = useState(0);
  const rawStep = PHASE_TO_STEP[phase];
  const currentStep = rawStep >= 0 ? rawStep : lastActiveStep;

  useEffect(() => {
    if (rawStep >= 0 && phase !== 'failed') {
      setLastActiveStep(rawStep);
    }
  }, [rawStep, phase]);

  const [elapsed, setElapsed] = useState<string | null>(null);
  useEffect(() => {
    if (!startTime) {
      setElapsed(null);
      return;
    }
    const tick = () => {
      const seconds = Math.floor((Date.now() - startTime) / 1000);
      setElapsed(seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [startTime]);

  if (phase === 'idle') return null;

  return (
    <div>
      <Steps
        direction="vertical"
        size="small"
        current={currentStep}
        status={phase === 'failed' ? 'error' : 'process'}
        items={STAGES.map((stage, idx) => ({
          title: stage.title,
          icon:
            idx < currentStep ? (
              <CheckCircleOutlined style={{ color: '#52c41a' }} />
            ) : idx === currentStep ? (
              phase === 'failed' ? (
                <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
              ) : (
                <LoadingOutlined style={{ color: '#1677ff' }} />
              )
            ) : (
              stage.icon
            ),
          description:
            idx === currentStep ? (
              <Space direction="vertical" size={2}>
                {message && <Text type="secondary" style={{ fontSize: 12 }}>{message}</Text>}
                {elapsed && (
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    已用时 {elapsed}
                  </Text>
                )}
              </Space>
            ) : undefined,
        }))}
      />

      {phase === 'failed' && error && (
        <div
          style={{
            marginTop: 8,
            padding: '8px 12px',
            borderRadius: 6,
            background: '#fff2f0',
            border: '1px solid #ffccc7',
          }}
        >
          <Text type="danger" style={{ fontSize: 13 }}>
            {error}
          </Text>
        </div>
      )}
    </div>
  );
}
