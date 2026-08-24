import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getJob, getJobProgress } from '../../lib/api';
import type { JobDetail } from '../../types/job';
import StageProgress from '../../components/StageProgress';
import './Jobs.css';

function JobDetailPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Initial load
  useEffect(() => {
    if (!jobId) return;

    async function loadJob() {
      try {
        const data = await getJob(jobId!);
        setJob(data);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to load job';
        setError(message);
      } finally {
        setLoading(false);
      }
    }

    loadJob();
  }, [jobId]);

  // Polling for progress
  useEffect(() => {
    if (!jobId || !job || job.status === 'completed' || job.status === 'failed') return;

    const interval = setInterval(async () => {
      try {
        const progress = await getJobProgress(jobId);
        setJob(prev => prev ? {
          ...prev,
          status: progress.status,
          progress_pct: progress.progress_pct,
          current_stage: progress.current_stage,
          stages: progress.stages
        } : null);
      } catch (err) {
        console.error('Failed to poll progress', err);
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [jobId, job?.status]);

  if (loading) {
    return (
      <div className="job-detail-page container">
        <div className="skeleton-line w-40" style={{ height: '32px', marginBottom: '24px' }} />
        <div className="job-detail-grid">
          <div className="surface-card" style={{ height: '400px' }} />
          <div className="surface-card" style={{ height: '400px' }} />
        </div>
      </div>
    );
  }

  if (error || !job) {
    return (
      <div className="job-detail-page container">
        <div className="jobs-error-banner font-mono">
          <span>✕ ERROR:</span> {error || 'Job not found'}
        </div>
        <Link to="/jobs" className="button-secondary">
          ← Back to Jobs
        </Link>
      </div>
    );
  }

  const isCompleted = job.status === 'completed';
  const isFailed = job.status === 'failed';
  const isRunning = !isCompleted && !isFailed && job.status !== 'created';

  return (
    <div className="job-detail-page container">
      {/* Top Breadcrumb & Actions */}
      <div className="detail-top-nav">
        <Link to="/jobs" className="back-link caption-uppercase font-mono">
          ← BACK TO JOBS
        </Link>
        <div className="detail-tags-row">
          <span className="badge-pill font-mono">{job.mode.toUpperCase()} MODE</span>
          <span className={`status-badge ${
            isCompleted ? 'badge-emerald' :
            isRunning ? 'badge-yellow' :
            isFailed ? 'badge-rose' :
            'badge-pill'
          }`}>
            {job.status.replace('_', ' ')}
          </span>
        </div>
      </div>

      {/* Main Header */}
      <div className="detail-header-card surface-card">
        <div className="detail-title-group">
          <span className="caption-uppercase">ACTIVE PIPELINE MANIFEST</span>
          <h1 className="job-title display-sm font-mono">JOB_{job.job_id}</h1>
        </div>

        <div className="detail-stat-callout">
          <span className="stat-display">{job.progress_pct}%</span>
          <span className="stat-sublabel caption-uppercase">AGGREGATE COMPLETION</span>
        </div>
      </div>

      {/* 2-Column Grid */}
      <div className="job-detail-grid">
        {/* Left Column: Stage Timeline */}
        <div className="detail-left-col">
          <div className="surface-card detail-pipeline-card">
            <div className="card-header-row">
              <h2 className="title-md">Execution Stages</h2>
              <span className="badge-pill font-mono">{job.stages.length} STAGES</span>
            </div>

            <div className="pipeline-wrap">
              <StageProgress stages={job.stages} />
            </div>

            {isCompleted && (
              <div className="job-complete-box">
                <span className="caption-uppercase" style={{ color: '#22c55e' }}>ARTIFACT GENERATION COMPLETE</span>
                <p className="body-sm" style={{ margin: '8px 0 16px' }}>
                  All 3D dense geometry, camera trajectories, and semantic bounding objects are packaged and ready.
                </p>
                <div className="action-buttons-row">
                  <button type="button" className="button-primary" disabled>
                    Open 3D Viewer (Phase 5)
                  </button>
                  <button type="button" className="button-secondary" disabled>
                    Download .GLB Bundle (Phase 11)
                  </button>
                </div>
              </div>
            )}

            {isFailed && (
              <div className="job-fail-box font-mono">
                <span className="error-title">EXECUTION FAILED</span>
                <p className="error-text">{job.error || 'A worker process encountered an unrecoverable exception.'}</p>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Technical Metadata */}
        <div className="detail-right-col">
          <div className="surface-card">
            <div className="card-header-row">
              <h2 className="title-md">Payload Telemetry</h2>
            </div>

            <div className="telemetry-list font-mono">
              <div className="telemetry-item">
                <span className="tel-label">SOURCE_FILE</span>
                <span className="tel-value truncate">{job.video?.filename || 'video.mp4'}</span>
              </div>

              <div className="telemetry-item">
                <span className="tel-label">PAYLOAD_SIZE</span>
                <span className="tel-value">
                  {job.video?.size_bytes ? `${(job.video.size_bytes / (1024 * 1024)).toFixed(2)} MB` : 'N/A'}
                </span>
              </div>

              <div className="telemetry-item">
                <span className="tel-label">CREATED_AT</span>
                <span className="tel-value">{new Date(job.created_at).toLocaleString()}</span>
              </div>

              <div className="telemetry-item">
                <span className="tel-label">LAST_UPDATE</span>
                <span className="tel-value">{new Date(job.updated_at).toLocaleString()}</span>
              </div>

              <div className="telemetry-item">
                <span className="tel-label">TARGET_SCHEMA</span>
                <span className="tel-value">GodsEye-v1.0-GLTF</span>
              </div>

              <div className="telemetry-item">
                <span className="tel-label">COMPUTE_ENGINE</span>
                <span className="tel-value">Localhost (Orchestrator)</span>
              </div>
            </div>
          </div>

          <div className="surface-card" style={{ marginTop: 'var(--spacing-lg)' }}>
            <div className="card-header-row">
              <h2 className="title-md">Confidence & Traceability</h2>
            </div>
            <p className="body-sm" style={{ marginBottom: '16px' }}>
              Every geometric node maintains provenance. Inferred proxy structures are isolated from measured photogrammetric points.
            </p>
            <div className="confidence-pill-row">
              <span className="badge-pill font-mono">100% TRACEABLE</span>
              <span className="badge-pill font-mono">AIR-GAPPED COMPLIANT</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default JobDetailPage;
