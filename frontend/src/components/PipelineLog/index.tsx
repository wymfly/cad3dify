import { useEffect, useRef } from 'react';
import { Typography, Tag } from 'antd';
import type { JobEvent } from '../../hooks/useJobEvents.ts';

const { Text } = Typography;

const STATUS_COLORS: Record<string, string> = {
  created: 'default',
  analyzing: 'processing',
  intent_parsed: 'blue',
  awaiting_confirmation: 'warning',
  awaiting_drawing_confirmation: 'warning',
  generating: 'processing',
  refining: 'processing',
  completed: 'success',
  failed: 'error',
};

export interface PipelineLogProps {
  events: JobEvent[];
  maxHeight?: number;
}

export default function PipelineLog({
  events,
  maxHeight = 400,
}: PipelineLogProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events.length]);

  if (events.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 24, color: '#999' }}>
        <Text type="secondary">等待管道事件...</Text>
      </div>
    );
  }

  return (
    <div
      style={{
        maxHeight,
        overflow: 'auto',
        fontFamily: 'monospace',
        fontSize: 12,
        lineHeight: 1.8,
      }}
    >
      {events.map((event, idx) => {
        const color = STATUS_COLORS[event.status] ?? 'default';
        const time = new Date().toLocaleTimeString('zh-CN', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        });
        return (
          <div
            key={idx}
            style={{
              padding: '2px 0',
              borderBottom: '1px solid rgba(0,0,0,0.04)',
            }}
          >
            <Text type="secondary" style={{ fontSize: 11, marginRight: 6 }}>
              {time}
            </Text>
            <Tag
              color={color}
              style={{ fontSize: 11, lineHeight: '16px', marginRight: 6 }}
            >
              {event.stage ?? event.status}
            </Tag>
            <Text style={{ fontSize: 12 }}>{event.message}</Text>
            {event.progress != null && (
              <Text type="secondary" style={{ fontSize: 11, marginLeft: 4 }}>
                ({Math.round(event.progress * 100)}%)
              </Text>
            )}
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
