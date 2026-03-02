import type { Node, Edge } from '@xyflow/react';
import type { PipelineNodeDescriptor } from '../../types/pipeline.ts';

export interface PipelineNode {
  id: string;
  label: string;
  group: 'init' | 'analysis' | 'hitl' | 'generation' | 'postprocess' | 'final';
  strategy?: string | null;
  nonFatal?: boolean;
}

export interface PipelineTopology {
  nodes: PipelineNode[];
  edges: Array<{ source: string; target: string }>;
}

// --- Hardcoded fallback (used when API unavailable) ---

const ALL_NODES: PipelineNode[] = [
  { id: 'create_job', label: '创建任务', group: 'init' },
  { id: 'analyze_intent', label: '意图解析', group: 'analysis' },
  { id: 'analyze_vision', label: '图纸分析', group: 'analysis' },
  { id: 'analyze_organic', label: '有机分析', group: 'analysis' },
  { id: 'confirm_with_user', label: '用户确认', group: 'hitl' },
  { id: 'generate_step_text', label: '文本生成', group: 'generation' },
  { id: 'generate_step_drawing', label: '图纸生成', group: 'generation' },
  { id: 'generate_organic_mesh', label: '有机生成', group: 'generation' },
  { id: 'mesh_repair', label: '网格修复', group: 'postprocess' },
  { id: 'mesh_scale', label: '网格缩放', group: 'postprocess' },
  { id: 'boolean_cuts', label: '布尔运算', group: 'postprocess' },
  { id: 'export_formats', label: '格式导出', group: 'postprocess' },
  { id: 'convert_preview', label: 'GLB 预览', group: 'postprocess' },
  { id: 'check_printability', label: '可打印性检查', group: 'postprocess' },
  { id: 'analyze_dfam', label: 'DfAM 分析', group: 'postprocess' },
  { id: 'finalize', label: '完成', group: 'final' },
];

const ALL_EDGES = [
  { source: 'create_job', target: 'analyze_intent' },
  { source: 'create_job', target: 'analyze_vision' },
  { source: 'create_job', target: 'analyze_organic' },
  { source: 'analyze_intent', target: 'confirm_with_user' },
  { source: 'analyze_vision', target: 'confirm_with_user' },
  { source: 'analyze_organic', target: 'confirm_with_user' },
  { source: 'confirm_with_user', target: 'generate_step_text' },
  { source: 'confirm_with_user', target: 'generate_step_drawing' },
  { source: 'confirm_with_user', target: 'generate_organic_mesh' },
  { source: 'generate_step_text', target: 'convert_preview' },
  { source: 'generate_step_text', target: 'check_printability' },
  { source: 'generate_step_text', target: 'analyze_dfam' },
  { source: 'generate_step_drawing', target: 'convert_preview' },
  { source: 'generate_step_drawing', target: 'check_printability' },
  { source: 'generate_step_drawing', target: 'analyze_dfam' },
  { source: 'generate_organic_mesh', target: 'mesh_repair' },
  { source: 'mesh_repair', target: 'mesh_scale' },
  { source: 'mesh_scale', target: 'boolean_cuts' },
  { source: 'boolean_cuts', target: 'export_formats' },
  { source: 'export_formats', target: 'check_printability' },
  { source: 'export_formats', target: 'analyze_dfam' },
  { source: 'convert_preview', target: 'finalize' },
  { source: 'check_printability', target: 'finalize' },
  { source: 'analyze_dfam', target: 'finalize' },
  { source: 'export_formats', target: 'finalize' },
];

/** Path-specific node IDs */
const PATH_NODES: Record<string, string[]> = {
  text: [
    'create_job', 'analyze_intent', 'confirm_with_user',
    'generate_step_text', 'convert_preview', 'check_printability', 'analyze_dfam', 'finalize',
  ],
  drawing: [
    'create_job', 'analyze_vision', 'confirm_with_user',
    'generate_step_drawing', 'convert_preview', 'check_printability', 'analyze_dfam', 'finalize',
  ],
  organic: [
    'create_job', 'analyze_organic', 'confirm_with_user',
    'generate_organic_mesh', 'mesh_repair', 'mesh_scale', 'boolean_cuts', 'export_formats',
    'check_printability', 'analyze_dfam', 'finalize',
  ],
};

/**
 * Layout row assignments for the full (unfiltered) DAG.
 * Branching nodes at the same depth get different x positions.
 */
const FULL_LAYOUT: Record<string, { x: number; y: number }> = {
  create_job:            { x: 250, y: 0 },
  // Analysis branch: three parallel paths
  analyze_intent:        { x: 80,  y: 100 },
  analyze_vision:        { x: 250, y: 100 },
  analyze_organic:       { x: 420, y: 100 },
  confirm_with_user:     { x: 250, y: 200 },
  // Generation branch: three parallel paths
  generate_step_text:    { x: 80,  y: 300 },
  generate_step_drawing: { x: 250, y: 300 },
  generate_organic_mesh: { x: 420, y: 300 },
  // Organic postprocess chain
  mesh_repair:           { x: 420, y: 400 },
  mesh_scale:            { x: 420, y: 475 },
  boolean_cuts:          { x: 420, y: 550 },
  export_formats:        { x: 420, y: 625 },
  // Text/Drawing postprocess (fan-out from generation)
  convert_preview:       { x: 80,  y: 400 },
  check_printability:    { x: 165, y: 500 },
  analyze_dfam:          { x: 80,  y: 575 },
  finalize:              { x: 250, y: 725 },
};

// --- Dynamic topology from API ---

/** Infer group from node descriptor properties */
function inferGroup(desc: PipelineNodeDescriptor): PipelineNode['group'] {
  if (desc.is_entry) return 'init';
  if (desc.is_terminal) return 'final';
  if (desc.supports_hitl) return 'hitl';
  if (desc.name.startsWith('analyze_')) return 'analysis';
  if (desc.name.startsWith('generate_')) return 'generation';
  return 'postprocess';
}

/** Build topology from API node descriptors */
export function buildTopologyFromDescriptors(
  descriptors: PipelineNodeDescriptor[],
): { nodes: PipelineNode[]; edges: Array<{ source: string; target: string }> } {
  const nodes: PipelineNode[] = descriptors.map((d) => ({
    id: d.name,
    label: d.display_name,
    group: inferGroup(d),
    strategy: d.default_strategy,
    nonFatal: d.non_fatal,
  }));

  // Build produces → producer mapping
  const producerMap = new Map<string, string>();
  for (const d of descriptors) {
    for (const asset of d.produces) {
      producerMap.set(asset, d.name);
    }
  }

  // Derive edges from requires/produces
  const edges: Array<{ source: string; target: string }> = [];
  const edgeSet = new Set<string>();

  for (const d of descriptors) {
    for (const req of d.requires) {
      // OR dependency: [["a", "b"]] → need ANY of a or b
      const assets = Array.isArray(req) ? req : [req];
      for (const asset of assets) {
        const producer = producerMap.get(asset);
        if (producer && producer !== d.name) {
          const key = `${producer}->${d.name}`;
          if (!edgeSet.has(key)) {
            edgeSet.add(key);
            edges.push({ source: producer, target: d.name });
          }
        }
      }
    }
  }

  // Terminal nodes: connect all leaf nodes (no outgoing edges) to terminal
  const terminal = descriptors.find((d) => d.is_terminal);
  if (terminal) {
    const hasOutgoing = new Set(edges.map((e) => e.source));
    for (const d of descriptors) {
      if (!d.is_terminal && !hasOutgoing.has(d.name)) {
        const key = `${d.name}->${terminal.name}`;
        if (!edgeSet.has(key)) {
          edgeSet.add(key);
          edges.push({ source: d.name, target: terminal.name });
        }
      }
    }
  }

  return { nodes, edges };
}

/** Build path-specific node IDs from descriptors */
function buildPathNodes(
  descriptors: PipelineNodeDescriptor[],
): Record<string, string[]> {
  const paths: Record<string, string[]> = {};
  const allTypes = new Set<string>();
  for (const d of descriptors) {
    for (const t of d.input_types) allTypes.add(t);
  }

  for (const inputType of allTypes) {
    paths[inputType] = descriptors
      .filter((d) =>
        d.input_types.length === 0 || d.input_types.includes(inputType),
      )
      .map((d) => d.name);
  }
  return paths;
}

/** Filter topology by input_type, return ReactFlow-compatible nodes and edges. */
export function getFilteredTopology(
  inputType: string | null,
  descriptors?: PipelineNodeDescriptor[],
): { nodes: Node[]; edges: Edge[] } {
  let allNodes: PipelineNode[];
  let allEdges: Array<{ source: string; target: string }>;
  let pathNodes: Record<string, string[]>;

  if (descriptors && descriptors.length > 0) {
    const topo = buildTopologyFromDescriptors(descriptors);
    allNodes = topo.nodes;
    allEdges = topo.edges;
    pathNodes = buildPathNodes(descriptors);
  } else {
    allNodes = ALL_NODES;
    allEdges = ALL_EDGES;
    pathNodes = PATH_NODES;
  }

  const visibleIds = new Set(
    inputType && pathNodes[inputType]
      ? pathNodes[inputType]
      : allNodes.map((n) => n.id),
  );

  const filteredNodes = allNodes.filter((n) => visibleIds.has(n.id));
  const filteredEdges = allEdges.filter(
    (e) => visibleIds.has(e.source) && visibleIds.has(e.target),
  );

  // For single-path (filtered), use simple vertical layout centered at x=200
  // For full DAG (unfiltered), use branch-aware positions
  const isSinglePath = inputType != null && pathNodes[inputType] != null;

  const nodes: Node[] = filteredNodes.map((n, i) => ({
    id: n.id,
    type: 'pipelineNode',
    position: isSinglePath
      ? { x: 200, y: i * 100 }
      : FULL_LAYOUT[n.id] ?? { x: 200, y: i * 100 },
    data: {
      label: n.label,
      group: n.group,
      strategy: n.strategy,
      nonFatal: n.nonFatal,
    },
  }));

  const edges: Edge[] = filteredEdges.map((e) => ({
    id: `${e.source}-${e.target}`,
    source: e.source,
    target: e.target,
    type: 'animatedEdge',
    animated: false,
  }));

  return { nodes, edges };
}
