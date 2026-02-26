import { Typography, Card, Row, Col } from 'antd';
import {
  ExperimentOutlined,
  AppstoreOutlined,
  BarChartOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

const { Title, Paragraph } = Typography;

export default function Home() {
  const navigate = useNavigate();

  const cards = [
    {
      title: '生成 3D 模型',
      description: '上传 2D 工程图纸，AI 自动生成 3D CAD 模型',
      icon: <ExperimentOutlined style={{ fontSize: 32 }} />,
      path: '/generate',
    },
    {
      title: '参数化模板',
      description: '浏览和使用预定义的参数化零件模板',
      icon: <AppstoreOutlined style={{ fontSize: 32 }} />,
      path: '/templates',
    },
    {
      title: '评测基准',
      description: '运行评测基准，查看生成质量指标',
      icon: <BarChartOutlined style={{ fontSize: 32 }} />,
      path: '/benchmark',
    },
  ];

  return (
    <div>
      <Title level={2}>CAD3Dify</Title>
      <Paragraph type="secondary">
        AI 驱动的 2D 工程图纸 → 3D CAD 模型生成工具
      </Paragraph>
      <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
        {cards.map((card) => (
          <Col key={card.path} xs={24} sm={12} lg={8}>
            <Card
              hoverable
              onClick={() => navigate(card.path)}
              style={{ textAlign: 'center', height: '100%' }}
            >
              <div style={{ marginBottom: 16, color: '#1677ff' }}>
                {card.icon}
              </div>
              <Title level={4}>{card.title}</Title>
              <Paragraph type="secondary">{card.description}</Paragraph>
            </Card>
          </Col>
        ))}
      </Row>
    </div>
  );
}
