import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Button,
  Card,
  Descriptions,
  Space,
  Spin,
  Tag,
  Typography,
  Popconfirm,
  message,
  Divider,
} from 'antd';
import {
  ArrowLeftOutlined,
  ReloadOutlined,
  DeleteOutlined,
  DownloadOutlined,
} from '@ant-design/icons';
import { useOutletContext } from 'react-router-dom';
import type { WorkbenchOutletContext } from '../../layouts/WorkbenchLayout.tsx';
import { useTheme } from '../../contexts/ThemeContext.tsx';
import Viewer3D from '../../components/Viewer3D/index.tsx';
import PrintReport from '../../components/PrintReport/index.tsx';
import api, {
  getJobDetail,
  deleteJob,
  regenerateJob,
  type JobDetail,
} from '../../services/api.ts';

const { Text, Title } = Typography;

const STATUS_TAG_MAP: Record<string, { color: string; label: string }> = {
  completed: { color: 'success', label: '已完成' },
  failed: { color: 'error', label: '失败' },
  generating: { color: 'processing', label: '生成中' },
  created: { color: 'default', label: '已创建' },
  awaiting_confirmation: { color: 'warning', label: '待确认' },
  awaiting_drawing_confirmation: { color: 'warning', label: '待图纸确认' },
  refining: { color: 'processing', label: '优化中' },
  validation_failed: { color: 'error', label: '校验失败' },
};

const DOWNLOAD_FORMATS = [
  { key: 'step', label: 'STEP', desc: '工业标准' },
  { key: 'stl', label: 'STL', desc: '3D 打印' },
  { key: '3mf', label: '3MF', desc: '新一代打印' },
  { key: 'gltf', label: 'glTF', desc: '网页预览' },
];

export default function PartDetail() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const { setPanels } = useOutletContext<WorkbenchOutletContext>();
  const { isDark } = useTheme();

  const [job, setJob] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState<string | null>(null);

  const fetchJob = useCallback(async () => {
    if (!jobId) return;
    setLoading(true);
    try {
      const data = await getJobDetail(jobId);
      setJob(data);
    } catch {
      message.error('加载零件详情失败');
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    fetchJob();
  }, [fetchJob]);

  const handleDelete = useCallback(async () => {
    if (!jobId) return;
    try {
      await deleteJob(jobId);
      message.success('已删除');
      navigate('/library');
    } catch {
      message.error('删除失败');
    }
  }, [jobId, navigate]);

  const handleRegenerate = useCallback(async () => {
    if (!jobId) return;
    try {
      const data = await regenerateJob(jobId);
      navigate(`/precision?jobId=${data.job_id}`);
    } catch {
      message.error('重新生成失败');
    }
  }, [jobId, navigate]);

  const handleDownload = useCallback(
    async (format: string) => {
      if (!jobId) return;
      setDownloading(format);
      try {
        const { data } = await api.post(
          `/v1/jobs/${jobId}/export`,
          { config: { format } },
          { responseType: 'blob' },
        );
        const ext = format === 'gltf' ? 'glb' : format;
        const url = URL.createObjectURL(data as Blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `model.${ext}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      } catch {
        message.error('下载失败');
      } finally {
        setDownloading(null);
      }
    },
    [jobId],
  );

  // Left panel: actions + downloads
  const leftPanel = useMemo(() => {
    if (loading || !job) return null;
    const statusInfo = STATUS_TAG_MAP[job.status] ?? {
      color: 'default',
      label: job.status,
    };

    return (
      <div>
        <Button
          icon={<ArrowLeftOutlined />}
          size="small"
          onClick={() => navigate('/library')}
          style={{ marginBottom: 12 }}
        >
          返回零件库
        </Button>

        <Title level={5} style={{ marginBottom: 4 }}>
          {job.input_text || '(无标题)'}
        </Title>
        <Tag color={statusInfo.color} style={{ marginBottom: 12 }}>
          {statusInfo.label}
        </Tag>

        {job.status === 'completed' && (
          <>
            <Divider style={{ margin: '12px 0' }} />
            <Text
              strong
              style={{ display: 'block', marginBottom: 8, fontSize: 12 }}
            >
              下载模型
            </Text>
            <Space direction="vertical" style={{ width: '100%' }} size={6}>
              {DOWNLOAD_FORMATS.map((fmt) => (
                <Button
                  key={fmt.key}
                  block
                  size="small"
                  icon={<DownloadOutlined />}
                  loading={downloading === fmt.key}
                  onClick={() => handleDownload(fmt.key)}
                  type={fmt.key === 'step' ? 'primary' : 'default'}
                >
                  {fmt.label}
                  <Text
                    type="secondary"
                    style={{ fontSize: 11, marginLeft: 6 }}
                  >
                    {fmt.desc}
                  </Text>
                </Button>
              ))}
            </Space>
          </>
        )}

        <Divider style={{ margin: '12px 0' }} />

        <Space direction="vertical" style={{ width: '100%' }} size={6}>
          <Button
            block
            size="small"
            icon={<ReloadOutlined />}
            onClick={handleRegenerate}
          >
            改参数重生成
          </Button>
          <Popconfirm title="确定删除此零件？" onConfirm={handleDelete}>
            <Button block size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      </div>
    );
  }, [
    loading,
    job,
    downloading,
    navigate,
    handleDownload,
    handleRegenerate,
    handleDelete,
  ]);

  // Right panel: job info + printability + params
  const rightPanel = useMemo(() => {
    if (loading || !job) return null;

    return (
      <div>
        <Card size="small" title="基本信息" style={{ marginBottom: 12 }}>
          <Descriptions column={1} size="small">
            <Descriptions.Item label="Job ID">
              <Text copyable style={{ fontSize: 11 }}>
                {job.job_id}
              </Text>
            </Descriptions.Item>
            <Descriptions.Item label="输入类型">
              {job.input_type === 'text' ? '文本生成' : '图纸生成'}
            </Descriptions.Item>
            <Descriptions.Item label="创建时间">
              {new Date(job.created_at).toLocaleString('zh-CN')}
            </Descriptions.Item>
            {job.error && (
              <Descriptions.Item label="错误">
                <Text type="danger" style={{ fontSize: 12 }}>
                  {job.error}
                </Text>
              </Descriptions.Item>
            )}
          </Descriptions>
        </Card>

        {job.printability && (
          <div style={{ marginBottom: 12 }}>
            <PrintReport results={job.printability} />
          </div>
        )}

        {job.precise_spec && (
          <Card size="small" title="参数详情">
            <pre
              style={{
                fontSize: 11,
                margin: 0,
                whiteSpace: 'pre-wrap',
                maxHeight: 200,
                overflow: 'auto',
              }}
            >
              {JSON.stringify(job.precise_spec, null, 2)}
            </pre>
          </Card>
        )}
      </div>
    );
  }, [loading, job]);

  useEffect(() => {
    setPanels({ left: leftPanel, right: rightPanel });
  }, [leftPanel, rightPanel, setPanels]);

  // Center: 3D viewer or loading
  if (loading) {
    return (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Spin size="large" />
      </div>
    );
  }

  if (!job) {
    return (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Text type="secondary">零件未找到</Text>
      </div>
    );
  }

  const modelUrl = job.result?.model_url ?? null;

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <Viewer3D modelUrl={modelUrl} darkMode={isDark} />
    </div>
  );
}
