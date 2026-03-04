import { Switch, Select, Collapse, Tag, Tooltip, Space, Typography } from 'antd';
import SchemaForm from '../SchemaForm/index.tsx';
import type { PipelineNodeDescriptor, NodeLevelConfig, StrategyAvailabilityMap } from '../../types/pipeline.ts';

const { Text } = Typography;

interface CustomPanelProps {
  descriptors: PipelineNodeDescriptor[];
  config: Record<string, NodeLevelConfig>;
  onChange: (nodeConfig: Record<string, NodeLevelConfig>) => void;
  strategyAvailability?: StrategyAvailabilityMap;
}

/** Nodes that are always enabled and cannot be toggled */
const NON_TOGGLEABLE = new Set(['create_job', 'confirm_with_user', 'finalize']);

function inferGroup(desc: PipelineNodeDescriptor): string {
  if (desc.is_entry || desc.is_terminal || desc.supports_hitl) return 'system';
  if (desc.name.startsWith('analyze_')) return 'analysis';
  if (desc.name.startsWith('generate_')) return 'generation';
  return 'postprocess';
}

export default function CustomPanel({
  descriptors,
  config,
  onChange,
  strategyAvailability,
}: CustomPanelProps) {
  const handleToggle = (nodeName: string, enabled: boolean) => {
    const updated = { ...config };
    updated[nodeName] = { ...updated[nodeName], enabled };
    onChange(updated);
  };

  const handleStrategy = (nodeName: string, strategy: string) => {
    const updated = { ...config };
    updated[nodeName] = { ...updated[nodeName], strategy };
    onChange(updated);
  };

  const handleParams = (nodeName: string, params: Record<string, unknown>) => {
    const updated = { ...config };
    updated[nodeName] = { ...updated[nodeName], ...params };
    onChange(updated);
  };

  // Filter out system nodes
  const configurable = descriptors.filter((d) => inferGroup(d) !== 'system');

  const items = configurable.map((desc) => {
    const nodeConf = config[desc.name] ?? {};
    const enabled = nodeConf.enabled !== false;
    const canToggle = !NON_TOGGLEABLE.has(desc.name);
    const availability = strategyAvailability?.[desc.name] ?? {};

    return {
      key: desc.name,
      label: (
        <Space size={8}>
          {canToggle && (
            <Switch
              size="small"
              checked={enabled}
              onChange={(val) => { handleToggle(desc.name, val); }}
              onClick={(_, e) => e.stopPropagation()}
            />
          )}
          <Text style={{ opacity: enabled ? 1 : 0.5 }}>
            {desc.display_name}
          </Text>
          {desc.strategies.length > 1 && enabled && (
            <Select
              size="small"
              value={nodeConf.strategy ?? desc.default_strategy ?? desc.strategies[0]}
              onChange={(val) => handleStrategy(desc.name, val)}
              onClick={(e) => e.stopPropagation()}
              options={desc.strategies.map((s) => {
                const avail = availability[s];
                const isAvailable = avail?.available !== false;
                return {
                  label: isAvailable ? s : (
                    <Tooltip title={avail?.reason ?? '不可用'}>
                      <span style={{ opacity: 0.5 }}>{s}</span>
                    </Tooltip>
                  ),
                  value: s,
                  disabled: !isAvailable,
                };
              })}
              style={{ minWidth: 120 }}
            />
          )}
          {desc.non_fatal && (
            <Tag color="default" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>
              可选
            </Tag>
          )}
        </Space>
      ),
      children: enabled ? (
        <div>
          {desc.fallback_chain && desc.fallback_chain.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <Text type="secondary" style={{ fontSize: 11 }}>Fallback: </Text>
              {desc.fallback_chain.map((s, i) => (
                <span key={s}>
                  <Tag color="blue" style={{ fontSize: 11 }}>{s}</Tag>
                  {i < desc.fallback_chain!.length - 1 && <Text type="secondary">→ </Text>}
                </span>
              ))}
            </div>
          )}
          {desc.config_schema && (
            <SchemaForm
              schema={desc.config_schema as Record<string, unknown> & { properties?: Record<string, unknown> }}
              value={nodeConf}
              onChange={(params) => handleParams(desc.name, params)}
            />
          )}
        </div>
      ) : null,
      collapsible: enabled ? undefined : ('disabled' as const),
    };
  });

  return (
    <Collapse
      size="small"
      items={items}
      ghost
    />
  );
}
