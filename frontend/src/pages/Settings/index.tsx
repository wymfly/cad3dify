import { Typography, Empty } from 'antd';

const { Title } = Typography;

export default function Settings() {
  return (
    <div>
      <Title level={3}>设置</Title>
      <Empty description="设置页面即将上线" style={{ marginTop: 48 }} />
    </div>
  );
}
