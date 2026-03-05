import { Select, Typography } from 'antd';
import type { NodeLevelPreset } from '../../types/pipeline.ts';

const { Text } = Typography;

interface PresetSelectorProps {
  presets: NodeLevelPreset[];
  value: string;
  onChange: (presetName: string) => void;
}

export default function PresetSelector({ presets, value, onChange }: PresetSelectorProps) {
  const options = [
    ...presets.map((p) => ({
      label: (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>{p.display_name}</span>
          <Text type="secondary" style={{ fontSize: 11 }}>{p.description}</Text>
        </div>
      ),
      value: p.name,
    })),
    { label: '自定义', value: 'custom' },
  ];

  return (
    <Select
      value={value}
      options={options}
      onChange={onChange}
      size="small"
      style={{ width: '100%' }}
      optionLabelProp="label"
    />
  );
}
