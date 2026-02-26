export interface PipelineConfig {
  preset: 'fast' | 'balanced' | 'precise' | 'custom';

  // Stage 1: Drawing analysis enhancements
  ocr_assist: boolean;
  two_pass_analysis: boolean;
  multi_model_voting: boolean;
  self_consistency_runs: number;

  // Stage 2: Code generation
  best_of_n: number;
  rag_enabled: boolean;
  api_whitelist: boolean;
  ast_pre_check: boolean;

  // Stage 3: Validation
  volume_check: boolean;
  topology_check: boolean;
  cross_section_check: boolean;

  // Stage 4: Refinement loop
  max_refinements: number;
  multi_view_render: boolean;
  structured_feedback: boolean;
  rollback_on_degrade: boolean;
  contour_overlay: boolean;

  // Stage 5: Output
  printability_check: boolean;
  output_formats: string[];
}

export interface TooltipSpec {
  title: string;
  description: string;
  when_to_use: string;
  cost: string;
  default: string;
}

export interface PresetInfo {
  name: string;
  config: PipelineConfig;
}
