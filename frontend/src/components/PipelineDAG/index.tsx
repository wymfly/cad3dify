import { useState, useCallback, useEffect, useMemo } from 'react';
import { ReactFlow, Background, Controls } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import NodeCard from './NodeCard.tsx';
import AnimatedEdge from './AnimatedEdge.tsx';
import NodeInspector from './NodeInspector.tsx';
import type { NodeInspectorData } from './NodeInspector.tsx';
import type { NodeStatus } from './NodeCard.tsx';
import { getFilteredTopology } from './topology.ts';
import type { JobEvent } from '../../hooks/useJobEvents.ts';

export interface NodeState {
  status: NodeStatus;
  elapsedMs?: number;
  reasoning?: Record<string, string> | null;
  outputsSummary?: Record<string, unknown> | null;
  error?: string;
}

const nodeTypes = { pipelineNode: NodeCard };
const edgeTypes = { animatedEdge: AnimatedEdge };

interface PipelineDAGProps {
  inputType: string | null;
  events: JobEvent[];
}

export default function PipelineDAG({ inputType, events }: PipelineDAGProps) {
  const [nodeStates, setNodeStates] = useState<Map<string, NodeState>>(new Map());
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [inspectorData, setInspectorData] = useState<NodeInspectorData | null>(null);

  // Process events into node states
  useEffect(() => {
    const states = new Map<string, NodeState>();

    for (const evt of events) {
      const node = (evt as Record<string, unknown>).node as string | undefined;
      if (!node) continue;

      const status = evt.status as string;

      if (status === 'node.started' || (evt as Record<string, unknown>).timestamp) {
        // node.started event — check if this looks like a started event
        if (!states.has(node) || states.get(node)!.status === 'pending') {
          states.set(node, { status: 'running' });
        }
      }
    }

    // Second pass: overwrite with completed/failed
    for (const evt of events) {
      const evtAny = evt as Record<string, unknown>;
      const node = evtAny.node as string | undefined;
      if (!node) continue;

      if (evtAny.elapsed_ms != null && evtAny.error == null && evtAny.outputs_summary != null) {
        // node.completed
        states.set(node, {
          status: 'completed',
          elapsedMs: evtAny.elapsed_ms as number,
          reasoning: evtAny.reasoning as Record<string, string> | null,
          outputsSummary: evtAny.outputs_summary as Record<string, unknown>,
        });
      } else if (evtAny.elapsed_ms != null && evtAny.error != null) {
        // node.failed
        states.set(node, {
          status: 'failed',
          elapsedMs: evtAny.elapsed_ms as number,
          error: evtAny.error as string,
        });
      }
    }

    setNodeStates(states);
  }, [events]);

  const { nodes: baseNodes, edges: baseEdges } = useMemo(
    () => getFilteredTopology(inputType),
    [inputType],
  );

  // Enrich nodes with status data
  const nodes = useMemo(
    () =>
      baseNodes.map((n) => {
        const state = nodeStates.get(n.id);
        return {
          ...n,
          data: {
            ...n.data,
            status: state?.status || 'pending',
            elapsedMs: state?.elapsedMs,
          },
        };
      }),
    [baseNodes, nodeStates],
  );

  // Animate edges whose source is completed
  const edges = useMemo(
    () =>
      baseEdges.map((e) => {
        const sourceState = nodeStates.get(e.source);
        return {
          ...e,
          animated: sourceState?.status === 'completed',
        };
      }),
    [baseEdges, nodeStates],
  );

  const handleNodeClick = useCallback(
    (_: unknown, node: { id: string; data: Record<string, unknown> }) => {
      const state = nodeStates.get(node.id);
      if (!state || state.status === 'pending') return;

      setInspectorData({
        nodeId: node.id,
        label: (node.data.label as string) ?? node.id,
        status: state.status,
        elapsedMs: state.elapsedMs,
        reasoning: state.reasoning,
        outputsSummary: state.outputsSummary,
        error: state.error,
      });
      setInspectorOpen(true);
    },
    [nodeStates],
  );

  return (
    <div style={{ height: 500, border: '1px solid #f0f0f0', borderRadius: 8 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodeClick={handleNodeClick}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls />
      </ReactFlow>

      <NodeInspector
        open={inspectorOpen}
        data={inspectorData}
        onClose={() => setInspectorOpen(false)}
      />
    </div>
  );
}
