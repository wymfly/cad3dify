import { useState, useEffect, useCallback, useMemo } from 'react';
import { Button, Typography, Empty } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useOutletContext } from 'react-router-dom';
import type { WorkbenchOutletContext } from '../../layouts/WorkbenchLayout.tsx';
import { useGenerateWorkflowContext } from '../../contexts/GenerateWorkflowContext.tsx';
import { useTheme } from '../../contexts/ThemeContext.tsx';
import { useParametricPreview } from '../../hooks/useParametricPreview.ts';
import InputPanel from '../../components/InputPanel/index.tsx';
import DrawingSpecForm from '../../components/DrawingSpecForm/index.tsx';
import ParamForm from '../../components/ParamForm/index.tsx';
import PipelineProgress from '../../components/PipelineProgress/index.tsx';
import PipelineLog from '../../components/PipelineLog/index.tsx';
import DownloadPanel from '../../components/DownloadPanel/index.tsx';
import PrintReport from '../../components/PrintReport/index.tsx';
import Viewer3D from '../../components/Viewer3D/index.tsx';
import type { JobEvent } from '../../hooks/useJobEvents.ts';

const { Text, Title } = Typography;

export default function PrecisionWorkbench() {
  const { setPanels } = useOutletContext<WorkbenchOutletContext>();
  const { isDark } = useTheme();
  const {
    workflow,
    startTextGenerate,
    startDrawingGenerate,
    confirmParams,
    confirmDrawingSpec,
    reset,
    pipelineConfig,
  } = useGenerateWorkflowContext();

  const [paramValues, setParamValues] = useState<
    Record<string, number | string | boolean>
  >({});
  const [sseEvents] = useState<JobEvent[]>([]);
  const [startTime] = useState<number | null>(null);

  // Initialize param values from parsed params
  useEffect(() => {
    if (workflow.parsedParams) {
      const defaults: Record<string, number | string | boolean> = {};
      for (const p of workflow.parsedParams) {
        if (p.default != null) defaults[p.name] = p.default;
      }
      setParamValues(defaults);
    }
  }, [workflow.parsedParams]);

  const handleParamChange = useCallback(
    (name: string, value: number | string | boolean) => {
      setParamValues((prev) => ({ ...prev, [name]: value }));
    },
    [],
  );

  const handleConfirm = useCallback(() => {
    const numericParams: Record<string, number> = {};
    for (const [k, v] of Object.entries(paramValues)) {
      if (typeof v === 'number') numericParams[k] = v;
    }
    confirmParams(numericParams);
  }, [paramValues, confirmParams]);

  // Numeric params for preview
  const numericParams = useMemo(() => {
    const result: Record<string, number> = {};
    for (const [k, v] of Object.entries(paramValues)) {
      if (typeof v === 'number') result[k] = v;
    }
    return result;
  }, [paramValues]);

  // Parametric preview during confirming
  const { previewUrl } = useParametricPreview({
    templateName: workflow.templateName,
    params: numericParams,
    enabled: workflow.phase === 'confirming' && !!workflow.templateName,
    debounceMs: 500,
  });

  const viewerModelUrl = previewUrl ?? workflow.modelUrl;

  // === 左面板内容（按管道阶段自动切换）===
  const leftPanel = useMemo(() => {
    switch (workflow.phase) {
      case 'idle':
        return (
          <InputPanel
            onSendText={(text) => startTextGenerate(text, pipelineConfig)}
            onSendImage={(file) => startDrawingGenerate(file, pipelineConfig)}
          />
        );

      case 'parsing':
        return (
          <PipelineProgress
            phase={workflow.phase}
            message={workflow.message}
            startTime={startTime ?? undefined}
          />
        );

      case 'drawing_review':
        return workflow.drawingSpec ? (
          <DrawingSpecForm
            drawingSpec={workflow.drawingSpec}
            onConfirm={confirmDrawingSpec}
            onCancel={reset}
          />
        ) : null;

      case 'confirming':
        return workflow.parsedParams && workflow.parsedParams.length > 0 ? (
          <ParamForm
            params={workflow.parsedParams}
            values={paramValues}
            onChange={handleParamChange}
            onConfirm={handleConfirm}
            onReset={() => {
              if (workflow.parsedParams) {
                const defaults: Record<string, number | string | boolean> = {};
                for (const p of workflow.parsedParams) {
                  if (p.default != null) defaults[p.name] = p.default;
                }
                setParamValues(defaults);
              }
            }}
            title="参数确认"
          />
        ) : null;

      case 'generating':
      case 'refining':
        return (
          <PipelineProgress
            phase={workflow.phase}
            message={workflow.message}
            startTime={startTime ?? undefined}
          />
        );

      case 'completed':
        return workflow.jobId ? (
          <DownloadPanel
            jobId={workflow.jobId}
            onRegenerate={reset}
          />
        ) : null;

      case 'failed':
        return (
          <div>
            <PipelineProgress
              phase={workflow.phase}
              message={workflow.message}
              error={workflow.error}
            />
            <Button
              type="primary"
              icon={<ReloadOutlined />}
              onClick={reset}
              style={{ marginTop: 16, width: '100%' }}
            >
              重新开始
            </Button>
          </div>
        );

      default:
        return null;
    }
  }, [
    workflow.phase,
    workflow.message,
    workflow.drawingSpec,
    workflow.parsedParams,
    workflow.jobId,
    workflow.error,
    paramValues,
    startTime,
    pipelineConfig,
    startTextGenerate,
    startDrawingGenerate,
    confirmDrawingSpec,
    confirmParams,
    handleParamChange,
    handleConfirm,
    reset,
  ]);

  // === 右面板内容（按管道阶段自动切换）===
  const rightPanel = useMemo(() => {
    switch (workflow.phase) {
      case 'idle':
        return (
          <div>
            <Title level={5}>快速入门</Title>
            <Text type="secondary" style={{ fontSize: 13 }}>
              在左侧面板输入零件描述或上传工程图纸，AI 将自动分析并生成 3D CAD 模型。
            </Text>
            <div style={{ marginTop: 16 }}>
              <Title level={5}>示例</Title>
              <ul style={{ paddingLeft: 16, color: '#666', fontSize: 13 }}>
                <li>做一个外径100mm的法兰盘</li>
                <li>创建直径50mm高80mm的阶梯轴</li>
                <li>上传工程图纸自动识别</li>
              </ul>
            </div>
          </div>
        );

      case 'drawing_review':
        return (
          <div>
            <Title level={5}>原始图纸</Title>
            <Text type="secondary" style={{ fontSize: 13 }}>
              请对照原始图纸核对左侧 AI 识别结果
            </Text>
          </div>
        );

      case 'parsing':
      case 'generating':
      case 'refining':
        return (
          <div>
            <Title level={5}>管道日志</Title>
            <PipelineLog events={sseEvents} />
          </div>
        );

      case 'confirming':
        return (
          <div>
            <Title level={5}>参数说明</Title>
            <Text type="secondary" style={{ fontSize: 13 }}>
              调整左侧参数后，3D 预览将在 500ms 后自动更新。
              确认参数无误后点击"确认参数"开始生成。
            </Text>
          </div>
        );

      case 'completed':
        return workflow.printability ? (
          <PrintReport results={workflow.printability} />
        ) : (
          <div>
            <Title level={5}>生成完成</Title>
            <Text type="secondary">
              模型已生成，可在左侧面板下载多种格式。
            </Text>
          </div>
        );

      case 'failed':
        return (
          <Empty
            description="生成失败，请检查输入后重试"
            style={{ marginTop: 40 }}
          />
        );

      default:
        return null;
    }
  }, [workflow.phase, workflow.printability, sseEvents]);

  // 注入面板内容到 WorkbenchLayout
  useEffect(() => {
    setPanels({ left: leftPanel, right: rightPanel });
  }, [leftPanel, rightPanel, setPanels]);

  // 中央区域始终显示 3D 预览
  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <Viewer3D modelUrl={viewerModelUrl} darkMode={isDark} />
    </div>
  );
}
