import { Segmented } from 'antd';
import type { PipelineConfig } from '../../types/pipeline.ts';

interface PresetSelectorProps {
  value: PipelineConfig['preset'];
  onChange: (preset: PipelineConfig['preset']) => void;
}

const presetOptions = [
  { label: '\u26A1 快速', value: 'fast' as const },
  { label: '\u2696\uFE0F 均衡', value: 'balanced' as const },
  { label: '\uD83C\uDFAF 精确', value: 'precise' as const },
  { label: '\u2699\uFE0F 自定义', value: 'custom' as const },
];

export default function PresetSelector({ value, onChange }: PresetSelectorProps) {
  return (
    <Segmented
      value={value}
      options={presetOptions}
      onChange={(val) => onChange(val as PipelineConfig['preset'])}
      block
      size="large"
    />
  );
}
