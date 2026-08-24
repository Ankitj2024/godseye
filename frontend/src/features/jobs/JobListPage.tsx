import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { listJobs } from '../../lib/api';
import type { JobSummary } from '../../types/job';
import './Jobs.css';

function JobListPage() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    async function loadJobs() {
      try {
        const data = await listJobs();
        setJobs(data);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to load jobs';
        setError(message);
      } finally {
        setLoading(false);
      }
    }

    loadJobs();
    
    // Poll every 5 seconds for updates
    const interval = setInterval(loadJobs, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="jobs-page container">
      {/* Page Header */}
      <div className="jobs-header-row">
        <div className="jobs-header-left">
          <span className="caption-uppercase">ORCHESTRATION</span>
          <h1 className="display-md">Reconstruction Jobs</h1>
        </div>
        <Link to="/" className="button-primary">
          + New Ingest Job
        </Link>
      </div>

      {error && (
        <div className="jobs-error-banner font-mono">
          <span>✕ ERROR:</span> {error}
        </div>
      )}

      {loading && jobs.length === 0 ? (
        <div className="jobs-grid">
          {[1, 2, 3].map((i) => (
            <div key={i} className="surface-card job-skeleton-card">
              <div className="skeleton-line w-40" />
              <div className="skeleton-line w-80" />
              <div className="skeleton-line w-60" />
            </div>
          ))}
        </div>
      ) : jobs.length === 0 ? (
        <div className="surface-card empty-state-box">
          <div className="empty-symbol-box">
            <span className="empty-symbol font-mono">∅</span>
          </div>
          <h2 className="title-md">No jobs registered in local store</h2>
          <p className="body-sm">
            Upload an aerial drone video stream to initialize an asynchronous reconstruction pipeline.
          </p>
          <Link to="/" className="button-primary" style={{ marginTop: 'var(--spacing-md)' }}>
            Upload First Video
          </Link>
        </div>
      ) : (
        <div className="jobs-grid">
          {jobs.map((job) => {
            const isCompleted = job.status === 'completed';
            const isFailed = job.status === 'failed';
            const isRunning = !isCompleted && !isFailed && job.status !== 'created';

            return (
              <Link to={`/jobs/${job.job_id}`} key={job.job_id} className="surface-card job-card-link">
                <div className="job-card-top">
                  <div className="job-id-wrap">
                    <span className="job-id-label caption-uppercase">JOB ID</span>
                    <span className="job-id font-mono">{job.job_id}</span>
                  </div>
                  <span className={`status-badge ${
                    isCompleted ? 'badge-emerald' :
                    isRunning ? 'badge-yellow' :
                    isFailed ? 'badge-rose' :
                    'badge-pill'
                  }`}>
                    {job.status.replace('_', ' ')}
                  </span>
                </div>

                <div className="job-card-meta-list">
                  <div className="meta-row">
                    <span className="meta-label">Mode</span>
                    <span className="meta-value font-mono capitalize">{job.mode}</span>
                  </div>
                  <div className="meta-row">
                    <span className="meta-label">Source File</span>
                    <span className="meta-value font-mono truncate" title={job.video_filename || ''}>
                      {job.video_filename || 'video.mp4'}
                    </span>
                  </div>
                  <div className="meta-row">
                    <span className="meta-label">Registered</span>
                    <span className="meta-value font-mono">
                      {new Date(job.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </span>
                  </div>
                </div>

                <div className="job-card-bottom">
                  <div className="job-progress-header">
                    <span className="job-stage-label font-mono">
                      {job.current_stage ? job.current_stage.replace('_', ' ') : 'Queued'}
                    </span>
                    <span className="job-pct font-mono">{job.progress_pct}%</span>
                  </div>
                  <div className="progress-bar">
                    <div
                      className="progress-bar-fill"
                      style={{ width: `${job.progress_pct}%` }}
                    />
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default JobListPage;
