import { Typography } from 'antd';

const { Text } = Typography;

interface HeatmapLegendProps {
  type: 'wall_thickness' | 'overhang';
  min: number | null;
  max: number | null;
  threshold: number;
  verticesAtRisk: number;
  verticesAtRiskPercent: number;
}

const TYPE_LABELS: Record<string, string> = {
  wall_thickness: '壁厚',
  overhang: '悬垂',
};

export default function HeatmapLegend({
  type,
  min,
  max,
  threshold,
  verticesAtRisk,
  verticesAtRiskPercent,
}: HeatmapLegendProps) {
  const label = TYPE_LABELS[type] ?? type;
  const fmtVal = (v: number | null) => (v != null ? v.toFixed(2) : '—');

  return (
    <div
      style={{
        position: 'absolute',
        right: 16,
        top: '50%',
        transform: 'translateY(-50%)',
        background: 'rgba(0,0,0,0.75)',
        borderRadius: 8,
        padding: '12px 14px',
        boxShadow: '0 2px 12px rgba(0,0,0,0.3)',
        zIndex: 10,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 6,
        minWidth: 72,
      }}
    >
      <Text strong style={{ color: '#fff', fontSize: 12, marginBottom: 2 }}>
        {label}分析
      </Text>

      {/* Color bar with scale labels */}
      <div style={{ display: 'flex', alignItems: 'stretch', gap: 6 }}>
        {/* Scale labels */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            height: 120,
            textAlign: 'right',
          }}
        >
          <Text style={{ color: '#22c55e', fontSize: 10, lineHeight: 1 }}>
            {fmtVal(max)}
          </Text>
          <Text style={{ color: '#eab308', fontSize: 10, lineHeight: 1 }}>
            {threshold.toFixed(2)}
          </Text>
          <Text style={{ color: '#dc2626', fontSize: 10, lineHeight: 1 }}>
            {fmtVal(min)}
          </Text>
        </div>

        {/* Gradient bar */}
        <div
          style={{
            width: 14,
            height: 120,
            borderRadius: 3,
            background: 'linear-gradient(to top, #dc2626, #eab308 50%, #22c55e)',
            border: '1px solid rgba(255,255,255,0.2)',
          }}
        />
      </div>

      {/* Risk stats */}
      <Text style={{ color: '#ffb3b3', fontSize: 11, textAlign: 'center', marginTop: 2 }}>
        {verticesAtRiskPercent.toFixed(1)}% 超限 ({verticesAtRisk})
      </Text>
    </div>
  );
}
