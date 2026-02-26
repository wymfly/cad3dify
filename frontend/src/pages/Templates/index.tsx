import { Typography, Empty } from 'antd';

const { Title } = Typography;

export default function Templates() {
  return (
    <div>
      <Title level={3}>参数化模板</Title>
      <Empty description="模板库即将上线" style={{ marginTop: 48 }} />
    </div>
  );
}
