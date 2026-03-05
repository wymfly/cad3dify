import { useEffect, useRef, useState } from 'react';
import { Typography, Spin } from 'antd';
import { CheckCircleFilled, CloseCircleFilled, LoadingOutlined } from '@ant-design/icons';
import { validatePipelineConfig } from '../../services/api.ts';
import type { NodeLevelConfig, PipelineValidateResponse } from '../../types/pipeline.ts';

const { Text } = Typography;

interface ValidationBannerProps {
  config: Record<string, NodeLevelConfig>;
  inputType?: string | null;
}

export default function ValidationBanner({ config, inputType }: ValidationBannerProps) {
  const [result, setResult] = useState<PipelineValidateResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);

    timerRef.current = setTimeout(() => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setLoading(true);
      validatePipelineConfig(inputType ?? null, config, controller.signal)
        .then((data) => {
          if (!controller.signal.aborted) {
            setResult(data);
          }
        })
        .catch((err) => {
          if (!controller.signal.aborted && err?.name !== 'AbortError') {
            setResult({ valid: false, error: '验证请求失败' });
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 300);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      abortRef.current?.abort();
    };
  }, [config, inputType]);

  if (!result && !loading) return null;

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      padding: '4px 0',
      fontSize: 12,
    }}>
      {loading ? (
        <>
          <Spin indicator={<LoadingOutlined style={{ fontSize: 12 }} />} size="small" />
          <Text type="secondary" style={{ fontSize: 12 }}>验证中…</Text>
        </>
      ) : result?.valid ? (
        <>
          <CheckCircleFilled style={{ color: '#52c41a', fontSize: 12 }} />
          <Text type="secondary" style={{ fontSize: 12 }}>
            {result.node_count} 节点
          </Text>
        </>
      ) : (
        <>
          <CloseCircleFilled style={{ color: '#ff4d4f', fontSize: 12 }} />
          <Text type="danger" style={{ fontSize: 12 }}>
            {result?.error ?? '无效配置'}
          </Text>
        </>
      )}
    </div>
  );
}
