import { useState } from 'react';
import { Switch, Select, Tag, Tooltip, Typography } from 'antd';
import { DownOutlined, RightOutlined } from '@ant-design/icons';
import SchemaForm from '../SchemaForm/index.tsx';
import { useDesignTokens } from '../../theme/useDesignTokens.ts';
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

interface PhaseGroup {
  key: string;
  label: string;
  color: string;
  nodes: PipelineNodeDescriptor[];
}

function classifyPhase(desc: PipelineNodeDescriptor): string {
  if (desc.is_entry || desc.is_terminal || desc.supports_hitl) return 'system';
  if (desc.name.startsWith('analyze_') || desc.name.startsWith('parse_')) return 'analysis';
  if (desc.name.startsWith('generate_')) return 'generation';
  return 'postprocess';
}

function groupByPhase(descriptors: PipelineNodeDescriptor[]): PhaseGroup[] {
  const phases: Record<string, PipelineNodeDescriptor[]> = {
    analysis: [],
    generation: [],
    postprocess: [],
  };

  for (const desc of descriptors) {
    const phase = classifyPhase(desc);
    if (phase === 'system') continue;
    phases[phase]?.push(desc);
  }

  const groups: PhaseGroup[] = [];
  if (phases.analysis.length > 0) {
    groups.push({ key: 'analysis', label: '分析 & 预处理', color: '#1677ff', nodes: phases.analysis });
  }
  if (phases.generation.length > 0) {
    groups.push({ key: 'generation', label: '核心生成', color: '#722ed1', nodes: phases.generation });
  }
  if (phases.postprocess.length > 0) {
    groups.push({ key: 'postprocess', label: '后处理 & 优化', color: '#13c2c2', nodes: phases.postprocess });
  }
  return groups;
}

export default function CustomPanel({
  descriptors,
  config,
  onChange,
  strategyAvailability,
}: CustomPanelProps) {
  const dt = useDesignTokens();
  const [expandedNode, setExpandedNode] = useState<string | null>(null);

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

  const phases = groupByPhase(descriptors);

  return (
    <div style={{ padding: '4px 0' }}>
      {phases.map((phase, phaseIdx) => (
        <div key={phase.key} style={{ marginBottom: phaseIdx < phases.length - 1 ? 12 : 0 }}>
          {/* Phase header */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            marginBottom: 6,
          }}>
            <div style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              backgroundColor: phase.color,
              flexShrink: 0,
            }} />
            <Text strong style={{ fontSize: 11, color: phase.color, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              {phase.label}
            </Text>
          </div>

          {/* Nodes in this phase */}
          <div style={{ marginLeft: 3, borderLeft: `2px solid ${phase.color}30`, paddingLeft: 14 }}>
            {phase.nodes.map((desc) => {
              const nodeConf = config[desc.name] ?? {};
              const enabled = nodeConf.enabled !== false;
              const canToggle = !NON_TOGGLEABLE.has(desc.name);
              const availability = strategyAvailability?.[desc.name] ?? {};
              const isExpanded = expandedNode === desc.name;
              const hasDetail = desc.config_schema || (desc.fallback_chain && desc.fallback_chain.length > 0);

              return (
                <div key={desc.name} style={{ marginBottom: 4 }}>
                  {/* Node row */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '3px 6px',
                      borderRadius: 4,
                      cursor: hasDetail && enabled ? 'pointer' : 'default',
                      backgroundColor: isExpanded ? dt.color.surface3 : 'transparent',
                      transition: 'background-color 0.15s',
                    }}
                    onClick={() => {
                      if (hasDetail && enabled) {
                        setExpandedNode(isExpanded ? null : desc.name);
                      }
                    }}
                  >
                    {/* Expand indicator */}
                    {hasDetail && enabled ? (
                      isExpanded
                        ? <DownOutlined style={{ fontSize: 9, color: dt.color.textTertiary, flexShrink: 0 }} />
                        : <RightOutlined style={{ fontSize: 9, color: dt.color.textTertiary, flexShrink: 0 }} />
                    ) : (
                      <span style={{ width: 9, flexShrink: 0 }} />
                    )}

                    {/* Toggle switch */}
                    {canToggle && (
                      <Switch
                        size="small"
                        checked={enabled}
                        onChange={(val) => handleToggle(desc.name, val)}
                        onClick={(_, e) => e.stopPropagation()}
                      />
                    )}

                    {/* Node name */}
                    <Text style={{
                      fontSize: 12,
                      opacity: enabled ? 1 : 0.45,
                      flexShrink: 0,
                    }}>
                      {desc.display_name}
                    </Text>

                    {/* Spacer */}
                    <span style={{ flex: 1 }} />

                    {/* Strategy selector */}
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
                        style={{ maxWidth: 120 }}
                        variant="borderless"
                      />
                    )}

                    {/* Non-fatal tag */}
                    {desc.non_fatal && (
                      <Tag
                        color="default"
                        style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}
                      >
                        可选
                      </Tag>
                    )}
                  </div>

                  {/* Expanded detail inspector */}
                  {isExpanded && enabled && (
                    <div style={{
                      marginLeft: 24,
                      marginTop: 2,
                      marginBottom: 6,
                      padding: '6px 10px',
                      borderRadius: 4,
                      backgroundColor: dt.color.surface3,
                    }}>
                      {desc.description && (
                        <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 6 }}>
                          {desc.description}
                        </Text>
                      )}

                      {desc.fallback_chain && desc.fallback_chain.length > 0 && (
                        <div style={{ marginBottom: 6 }}>
                          <Text type="secondary" style={{ fontSize: 11 }}>回退链: </Text>
                          {desc.fallback_chain.map((s, i) => (
                            <span key={s}>
                              <Tag color="blue" style={{ fontSize: 10, padding: '0 3px', margin: 0 }}>{s}</Tag>
                              {i < desc.fallback_chain!.length - 1 && (
                                <Text type="secondary" style={{ fontSize: 10 }}> → </Text>
                              )}
                            </span>
                          ))}
                        </div>
                      )}

                      {desc.config_schema && (
                        <SchemaForm
                          schema={desc.config_schema as Record<string, unknown> & { properties?: Record<string, unknown> }}
                          value={nodeConf}
                          onChange={(params) => handleParams(desc.name, params)}
                          scope="engineering"
                        />
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
