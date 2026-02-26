import { Typography } from 'antd';
import PrintConfigPanel from './PrintConfigPanel.tsx';

const { Title } = Typography;

export default function Settings() {
  return (
    <div>
      <Title level={3}>设置</Title>
      <PrintConfigPanel />
    </div>
  );
}
