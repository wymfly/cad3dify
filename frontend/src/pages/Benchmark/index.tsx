import { useState, useEffect } from 'react';
import { Typography, Table, Button, Space, Tag, message } from 'antd';
import { PlayCircleOutlined, EyeOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import type { ColumnsType } from 'antd/es/table';
import { getBenchmarkHistory } from '../../services/api.ts';
import type { BenchmarkSummary } from '../../types/benchmark.ts';

const { Title } = Typography;

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function rateTag(value: number) {
  const percent = value * 100;
  let color = 'red';
  if (percent >= 80) color = 'green';
  else if (percent >= 60) color = 'orange';
  return <Tag color={color}>{formatPercent(value)}</Tag>;
}

const columns: ColumnsType<BenchmarkSummary> = [
  {
    title: '日期',
    dataIndex: 'timestamp',
    key: 'timestamp',
    width: 180,
    render: (val: string) => new Date(val).toLocaleString('zh-CN'),
    sorter: (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
    defaultSortOrder: 'descend',
  },
  {
    title: '数据集',
    dataIndex: 'dataset',
    key: 'dataset',
    width: 120,
  },
  {
    title: '编译率',
    dataIndex: ['metrics', 'compile_rate'],
    key: 'compile_rate',
    width: 100,
    render: (val: number) => rateTag(val),
  },
  {
    title: '类型准确率',
    dataIndex: ['metrics', 'type_accuracy'],
    key: 'type_accuracy',
    width: 110,
    render: (val: number) => rateTag(val),
  },
  {
    title: '参数准确率',
    dataIndex: ['metrics', 'param_accuracy_p50'],
    key: 'param_accuracy_p50',
    width: 110,
    render: (val: number) => rateTag(val),
  },
  {
    title: '几何匹配率',
    dataIndex: ['metrics', 'bbox_match_rate'],
    key: 'bbox_match_rate',
    width: 110,
    render: (val: number) => rateTag(val),
  },
  {
    title: '平均耗时',
    dataIndex: ['metrics', 'avg_duration_s'],
    key: 'avg_duration_s',
    width: 100,
    render: (val: number) => `${val.toFixed(1)}s`,
  },
  {
    title: '操作',
    key: 'actions',
    width: 80,
    render: (_, record) => (
      <Button
        type="link"
        size="small"
        icon={<EyeOutlined />}
        data-run-id={record.run_id}
      >
        详情
      </Button>
    ),
  },
];

export default function Benchmark() {
  const navigate = useNavigate();
  const [history, setHistory] = useState<BenchmarkSummary[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    getBenchmarkHistory()
      .then(setHistory)
      .catch(() => {
        message.info('评测 API 尚未就绪，显示空数据');
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>评测基准</Title>
        <Button
          type="primary"
          icon={<PlayCircleOutlined />}
          onClick={() => navigate('/benchmark/run')}
        >
          运行评测
        </Button>
      </Space>
      <Table<BenchmarkSummary>
        columns={columns}
        dataSource={history}
        rowKey="run_id"
        loading={loading}
        pagination={{ pageSize: 10 }}
        onRow={(record) => ({
          onClick: () => navigate(`/benchmark/${record.run_id}`),
          style: { cursor: 'pointer' },
        })}
        locale={{ emptyText: '暂无评测记录' }}
      />
    </div>
  );
}
