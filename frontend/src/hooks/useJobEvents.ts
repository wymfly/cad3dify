import { useEffect, useRef, useCallback, useState } from 'react';
import type { JobStatus } from '../types/generate.ts';

/** SSE 事件载荷 */
export interface JobEvent {
  job_id: string;
  status: JobStatus;
  stage?: string;
  message: string;
  progress?: number;
  [key: string]: unknown;
}

interface UseJobEventsOptions {
  jobId: string | null;
  onEvent?: (event: JobEvent) => void;
  onComplete?: (event: JobEvent) => void;
  onError?: (event: JobEvent) => void;
}

interface UseJobEventsResult {
  events: JobEvent[];
  connected: boolean;
  disconnect: () => void;
}

const TERMINAL_STATUSES: ReadonlySet<string> = new Set(['completed', 'failed']);

/**
 * 订阅 Job SSE 事件流。
 * 连接 `GET /api/v1/jobs/{id}/events`，返回实时事件列表。
 * 当 Job 到达终态时自动断开。
 */
export function useJobEvents({
  jobId,
  onEvent,
  onComplete,
  onError,
}: UseJobEventsOptions): UseJobEventsResult {
  // 使用 jobId 作为 key 来重置事件列表
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  // 用 ref 保持回调最新引用（在 effect 中更新，避免 render 期间写 ref）
  const onEventRef = useRef(onEvent);
  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);
  useEffect(() => {
    onEventRef.current = onEvent;
    onCompleteRef.current = onComplete;
    onErrorRef.current = onError;
  });

  const closeSource = useCallback(() => {
    if (sourceRef.current) {
      sourceRef.current.close();
      sourceRef.current = null;
    }
  }, []);

  const disconnect = useCallback(() => {
    closeSource();
    setConnected(false);
  }, [closeSource]);

  useEffect(() => {
    // jobId 变化时重置状态
    setEvents([]);
    setConnected(false);

    if (!jobId) return;

    const url = `/api/v1/jobs/${jobId}/events`;
    const source = new EventSource(url);
    sourceRef.current = source;

    const safeParse = (raw: string): JobEvent | null => {
      try {
        return JSON.parse(raw) as JobEvent;
      } catch {
        return null;
      }
    };

    const handleEvent = (event: JobEvent) => {
      setEvents((prev) => [...prev, event]);
      onEventRef.current?.(event);

      if (event.status === 'completed') {
        onCompleteRef.current?.(event);
        source.close();
        sourceRef.current = null;
        setConnected(false);
      } else if (event.status === 'failed') {
        onErrorRef.current?.(event);
        source.close();
        sourceRef.current = null;
        setConnected(false);
      }
    };

    // 监听命名事件
    source.addEventListener('progress', (e: MessageEvent) => {
      const data = safeParse(e.data);
      if (data) handleEvent(data);
    });

    source.addEventListener('completed', (e: MessageEvent) => {
      const data = safeParse(e.data);
      if (data) handleEvent({ ...data, status: 'completed' });
    });

    source.addEventListener('failed', (e: MessageEvent) => {
      const data = safeParse(e.data);
      if (data) handleEvent({ ...data, status: 'failed' });
    });

    // 回退：处理无 event 字段的通用消息
    source.onmessage = (e: MessageEvent) => {
      const data = safeParse(e.data);
      if (!data) return;
      handleEvent(data);
    };

    source.onopen = () => {
      setConnected(true);
    };

    source.onerror = () => {
      // EventSource 会自动重连；如果已到终态则断开
      setEvents((prev) => {
        const last = prev[prev.length - 1];
        if (last && TERMINAL_STATUSES.has(last.status)) {
          source.close();
          sourceRef.current = null;
          setConnected(false);
        }
        return prev;
      });
    };

    return () => {
      source.close();
      sourceRef.current = null;
    };
  }, [jobId]);

  return { events, connected, disconnect };
}
