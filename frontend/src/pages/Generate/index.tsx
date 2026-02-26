import { Typography, Row, Col } from 'antd';
import PipelineConfigBar from '../../components/PipelineConfigBar/index.tsx';
import Viewer3D from '../../components/Viewer3D/index.tsx';

const { Title, Paragraph } = Typography;

export default function Generate() {
  return (
    <div>
      <Title level={3}>生成 3D 模型</Title>
      <Paragraph type="secondary">
        上传 2D 工程图纸，配置管道参数，AI 自动生成 3D CAD 模型
      </Paragraph>
      <Row gutter={24}>
        <Col xs={24} lg={10}>
          <PipelineConfigBar />
          <div
            style={{
              marginTop: 16,
              padding: 48,
              textAlign: 'center',
              background: '#fafafa',
              borderRadius: 8,
              border: '2px dashed #d9d9d9',
            }}
          >
            <Paragraph type="secondary">
              拖拽或点击上传工程图纸（PNG / JPG）
            </Paragraph>
          </div>
        </Col>
        <Col xs={24} lg={14}>
          <div style={{ height: 500 }}>
            <Viewer3D modelUrl={null} />
          </div>
        </Col>
      </Row>
    </div>
  );
}
