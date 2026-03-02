import { Segmented } from 'antd';
import type { NodeLevelPreset } from '../../types/pipeline.ts';

interface PresetSelectorProps {
  presets: NodeLevelPreset[];
  value: string;
  onChange: (presetName: string) => void;
}

export default function PresetSelector({ presets, value, onChange }: PresetSelectorProps) {
  const options = [
    ...presets.map((p) => ({
      label: p.display_name,
      value: p.name,
    })),
    { label: '自定义', value: 'custom' },
  ];

  return (
    <Segmented
      value={value}
      options={options}
      onChange={(val) => onChange(val as string)}
      block
      size="large"
    />
  );
}
