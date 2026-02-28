import { Button, Space, Tooltip } from 'antd';
import {
  BorderOutlined,
  GatewayOutlined,
} from '@ant-design/icons';

export interface CameraPreset {
  label: string;
  position: [number, number, number];
}

const VIEW_PRESETS: CameraPreset[] = [
  { label: '正视', position: [0, 0, 5] },
  { label: '俯视', position: [0, 5, 0] },
  { label: '侧视', position: [5, 0, 0] },
  { label: '等轴', position: [3, 3, 3] },
];

interface ViewControlsProps {
  wireframe: boolean;
  darkMode?: boolean;
  onWireframeToggle: () => void;
  onViewChange: (position: [number, number, number]) => void;
}

export default function ViewControls({
  wireframe,
  darkMode = false,
  onWireframeToggle,
  onViewChange,
}: ViewControlsProps) {
  return (
    <Space
      size={4}
      style={{
        position: 'absolute',
        bottom: 12,
        left: '50%',
        transform: 'translateX(-50%)',
        background: darkMode ? 'rgba(31,31,31,0.9)' : 'rgba(255,255,255,0.9)',
        borderRadius: 6,
        padding: '4px 8px',
        boxShadow: darkMode ? '0 2px 8px rgba(0,0,0,0.4)' : '0 2px 8px rgba(0,0,0,0.12)',
        zIndex: 10,
      }}
    >
      {VIEW_PRESETS.map((preset) => (
        <Tooltip key={preset.label} title={preset.label}>
          <Button
            size="small"
            onClick={() => onViewChange(preset.position)}
          >
            {preset.label}
          </Button>
        </Tooltip>
      ))}
      <Tooltip title={wireframe ? '切换实体' : '切换线框'}>
        <Button
          size="small"
          type={wireframe ? 'primary' : 'default'}
          icon={wireframe ? <GatewayOutlined /> : <BorderOutlined />}
          onClick={onWireframeToggle}
        />
      </Tooltip>
    </Space>
  );
}
