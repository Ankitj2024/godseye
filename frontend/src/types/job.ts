/**
 * TypeScript types for God's Eye jobs, matching the backend Pydantic models.
 */

export type ReconstructionMode = 'exact' | 'generative';

export type StageStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

export type JobStatus =
  | 'created'
  | 'ingesting'
  | 'selecting_frames'
  | 'reconstructing'
  | 'enhancing_depth'
  | 'detecting_semantics'
  | 'building_scene_graph'
  | 'completing_scene'
  | 'packaging'
  | 'completed'
  | 'failed'
  | 'partial_success';

export interface StageInfo {
  name: string;
  display_name: string;
  status: StageStatus;
  message: string;
  progress_pct: number;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  artifact_paths: string[];
}

export interface VideoMetadata {
  filename: string;
  size_bytes: number;
  content_type: string;
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  codec: string | null;
}

export interface JobSummary {
  job_id: string;
  mode: ReconstructionMode;
  status: JobStatus;
  created_at: string;
  progress_pct: number;
  current_stage: string | null;
  video_filename: string | null;
}

export interface JobDetail {
  job_id: string;
  mode: ReconstructionMode;
  status: JobStatus;
  created_at: string;
  updated_at: string;
  video: VideoMetadata | null;
  stages: StageInfo[];
  progress_pct: number;
  current_stage: string | null;
  error: string | null;
  result_summary: string | null;
}

export interface JobProgress {
  job_id: string;
  status: JobStatus;
  progress_pct: number;
  current_stage: string | null;
  stages: StageInfo[];
}
