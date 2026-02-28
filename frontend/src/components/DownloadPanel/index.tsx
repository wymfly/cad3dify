import { useState } from 'react';
import { Button, Space, Typography, message, Divider } from 'antd';
import {
  DownloadOutlined,
  SaveOutlined,
  ReloadOutlined,
} from '@ant-design/icons';

const { Text, Title } = Typography;

interface DownloadFormat {
  key: string;
  label: string;
  description: string;
}

const FORMATS: DownloadFormat[] = [
  { key: 'step', label: 'STEP', description: '工业标准 B-Rep 格式' },
  { key: 'stl', label: 'STL', description: '3D 打印通用格式' },
  { key: '3mf', label: '3MF', description: '新一代 3D 打印格式' },
  { key: 'gltf', label: 'glTF', description: '网页 3D 预览格式' },
];

export interface DownloadPanelProps {
  jobId: string;
  onRegenerate?: () => void;
  onSaveToLibrary?: () => void;
}

export default function DownloadPanel({
  jobId,
  onRegenerate,
  onSaveToLibrary,
}: DownloadPanelProps) {
  const [downloading, setDownloading] = useState<string | null>(null);

  const handleDownload = async (format: string) => {
    setDownloading(format);
    try {
      const resp = await fetch('/api/v1/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: jobId, config: { format } }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: '下载失败' }));
        message.error((err as Record<string, string>).detail ?? '下载失败');
        return;
      }
      const blob = await resp.blob();
      const ext = format === 'gltf' ? 'glb' : format;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `model.${ext}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      message.error('下载请求失败');
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div>
      <Title level={5} style={{ marginBottom: 12 }}>
        下载模型
      </Title>

      <Space direction="vertical" style={{ width: '100%' }} size={8}>
        {FORMATS.map((fmt) => (
          <Button
            key={fmt.key}
            block
            icon={<DownloadOutlined />}
            loading={downloading === fmt.key}
            onClick={() => handleDownload(fmt.key)}
            type={fmt.key === 'step' ? 'primary' : 'default'}
          >
            <span style={{ flex: 1, textAlign: 'left' }}>
              {fmt.label}
              <Text
                type="secondary"
                style={{ fontSize: 11, marginLeft: 8 }}
              >
                {fmt.description}
              </Text>
            </span>
          </Button>
        ))}
      </Space>

      <Divider style={{ margin: '16px 0' }} />

      <Space direction="vertical" style={{ width: '100%' }} size={8}>
        {onSaveToLibrary && (
          <Button
            block
            icon={<SaveOutlined />}
            onClick={onSaveToLibrary}
          >
            保存到零件库
          </Button>
        )}
        {onRegenerate && (
          <Button
            block
            icon={<ReloadOutlined />}
            onClick={onRegenerate}
          >
            重新生成
          </Button>
        )}
      </Space>
    </div>
  );
}
