/**
 * API client for communicating with the God's Eye backend.
 */

import type { JobDetail, JobSummary, JobProgress, ReconstructionMode } from '../types/job';

const API_BASE = 'http://localhost:8000/api';

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const response = await fetch(url, options);

  if (!response.ok) {
    const body = await response.text();
    let message: string;
    try {
      const parsed = JSON.parse(body);
      message = parsed.detail || body;
    } catch {
      message = body;
    }
    throw new ApiError(response.status, message);
  }

  return response.json();
}

/** Check backend health. */
export async function checkHealth(): Promise<{ status: string; service: string }> {
  return request('/health');
}

/** Create a new job by uploading a video file. */
export async function createJob(
  file: File,
  mode: ReconstructionMode,
  onProgress?: (pct: number) => void,
): Promise<JobDetail> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('mode', mode);

  // Use XMLHttpRequest for upload progress tracking
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE}/jobs`);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };

    xhr.onload = () => {
      if (xhr.status === 201) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new ApiError(xhr.status, err.detail || 'Upload failed'));
        } catch {
          reject(new ApiError(xhr.status, 'Upload failed'));
        }
      }
    };

    xhr.onerror = () => reject(new Error('Network error during upload'));
    xhr.send(formData);
  });
}

/** List all jobs. */
export async function listJobs(): Promise<JobSummary[]> {
  return request('/jobs');
}

/** Get full job detail. */
export async function getJob(jobId: string): Promise<JobDetail> {
  return request(`/jobs/${jobId}`);
}

/** Get job pipeline progress. */
export async function getJobProgress(jobId: string): Promise<JobProgress> {
  return request(`/jobs/${jobId}/progress`);
}

export { ApiError };
