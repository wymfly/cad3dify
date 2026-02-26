export type FailureCategory =
  | 'TYPE_RECOGNITION'
  | 'ANNOTATION_MISS'
  | 'CODE_EXECUTION'
  | 'STRUCTURAL_ERROR'
  | 'DIMENSION_DEVIATION';

export interface BenchmarkMetrics {
  compile_rate: number;
  type_accuracy: number;
  param_accuracy_p50: number;
  bbox_match_rate: number;
  avg_duration_s: number;
  avg_tokens: number;
}

export interface CaseResult {
  case_id: string;
  compiled: boolean;
  type_correct: boolean;
  param_accuracy: number;
  bbox_match: boolean;
  duration_s: number;
  tokens_used: number;
  failure_category?: FailureCategory;
  error_detail?: string;
}

export interface BenchmarkReport {
  run_id: string;
  dataset: string;
  timestamp: string;
  metrics: BenchmarkMetrics;
  failure_counts: Record<FailureCategory, number>;
  results: CaseResult[];
}

export interface BenchmarkSummary {
  run_id: string;
  dataset: string;
  timestamp: string;
  metrics: BenchmarkMetrics;
}

export interface BenchmarkProgressEvent {
  current: number;
  total: number;
  case_id: string;
  stage: string;
}
