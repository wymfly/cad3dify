import { useState, useEffect, useCallback } from 'react';
import { Card, Collapse } from 'antd';
import PresetSelector from './PresetSelector.tsx';
import CustomPanel from './CustomPanel.tsx';
import ValidationBanner from './ValidationBanner.tsx';
import { getNodePresets, getPipelineNodes, getStrategyAvailability } from '../../services/api.ts';
import type { PipelineNodeDescriptor, NodeLevelConfig, NodeLevelPreset, StrategyAvailabilityMap } from '../../types/pipeline.ts';

/** Default presets used when API is unavailable */
const FALLBACK_PRESETS: NodeLevelPreset[] = [
  {
    name: 'fast',
    display_name: '快速模式',
    description: '跳过非必要步骤，最快出结果',
    config: {
      check_printability: { enabled: false },
      analyze_dfam: { enabled: false },
    },
  },
  {
    name: 'balanced',
    display_name: '均衡模式',
    description: '默认配置，兼顾速度和质量',
    config: {
      check_printability: { enabled: true },
      analyze_dfam: { enabled: false },
    },
  },
  {
    name: 'full_print',
    display_name: '打印就绪',
    description: '完整分析，确保3D打印质量',
    config: {
      check_printability: { enabled: true },
      analyze_dfam: { enabled: true },
    },
  },
];

export interface NodeLevelPipelineConfig {
  preset: string;
  nodeConfig: Record<string, NodeLevelConfig>;
}

const DEFAULT_CONFIG: NodeLevelPipelineConfig = {
  preset: 'balanced',
  nodeConfig: {
    check_printability: { enabled: true },
    analyze_dfam: { enabled: false },
  },
};

export interface PipelineConfigBarProps {
  value?: NodeLevelPipelineConfig;
  onChange?: (config: NodeLevelPipelineConfig) => void;
}

export { DEFAULT_CONFIG };

export default function PipelineConfigBar({ value, onChange: onExternalChange }: PipelineConfigBarProps) {
  const [internalConfig, setInternalConfig] = useState<NodeLevelPipelineConfig>(DEFAULT_CONFIG);
  const config = value ?? internalConfig;
  const [presets, setPresets] = useState<NodeLevelPreset[]>(FALLBACK_PRESETS);
  const [descriptors, setDescriptors] = useState<PipelineNodeDescriptor[]>([]);
  const [customExpanded, setCustomExpanded] = useState(false);
  const [strategyAvailability, setStrategyAvailability] = useState<StrategyAvailabilityMap>({});

  useEffect(() => {
    getNodePresets()
      .then(setPresets)
      .catch(() => { /* Use fallback presets */ });
    getPipelineNodes()
      .then(setDescriptors)
      .catch(() => { /* No descriptors — custom panel stays empty */ });
    getStrategyAvailability()
      .then(setStrategyAvailability)
      .catch(() => { /* Strategy availability unavailable — degrade gracefully */ });
  }, []);

  const updateConfig = useCallback((newConfig: NodeLevelPipelineConfig) => {
    setInternalConfig(newConfig);
    onExternalChange?.(newConfig);
  }, [onExternalChange]);

  const handlePresetChange = useCallback((presetName: string) => {
    if (presetName === 'custom') {
      updateConfig({ ...config, preset: 'custom' });
      setCustomExpanded(true);
    } else {
      const preset = presets.find((p) => p.name === presetName);
      if (preset) {
        updateConfig({ preset: presetName, nodeConfig: { ...preset.config } });
      }
      setCustomExpanded(false);
    }
  }, [config, presets, updateConfig]);

  const handleCustomChange = useCallback((nodeConfig: Record<string, NodeLevelConfig>) => {
    updateConfig({ preset: 'custom', nodeConfig });
  }, [updateConfig]);

  return (
    <Card size="small" title="管道配置" style={{ marginBottom: 16 }}>
      <PresetSelector
        presets={presets}
        value={config.preset}
        onChange={handlePresetChange}
      />
      <ValidationBanner config={config.nodeConfig} />
      {descriptors.length > 0 && (
        <Collapse
          activeKey={customExpanded ? ['custom'] : []}
          onChange={(keys) => setCustomExpanded(keys.includes('custom'))}
          ghost
          style={{ marginTop: 12 }}
          items={[
            {
              key: 'custom',
              label: '节点级配置',
              children: (
                <CustomPanel
                  descriptors={descriptors}
                  config={config.nodeConfig}
                  onChange={handleCustomChange}
                  strategyAvailability={strategyAvailability}
                />
              ),
            },
          ]}
        />
      )}
    </Card>
  );
}
