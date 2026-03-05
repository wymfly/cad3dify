/** mock-data 共享类型（避免循环依赖） */

export interface JobSummary {
  job_id: string;
  status: string;
  input_type: 'text' | 'drawing';
  input_text: string;
  created_at: string;
  result?: Record<string, unknown> | null;
}

export interface PaginatedJobsResponse {
  items: JobSummary[];
  total: number;
  page: number;
  page_size: number;
}
