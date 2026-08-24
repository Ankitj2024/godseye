import type { StageInfo } from '../types/job';
import './StageProgress.css';

interface StageProgressProps {
  stages: StageInfo[];
  compact?: boolean;
}

function StageProgress({ stages, compact = false }: StageProgressProps) {
  return (
    <div className={`stage-timeline ${compact ? 'stage-timeline-compact' : ''}`}>
      {stages.map((stage, index) => {
        const isCompleted = stage.status === 'completed';
        const isRunning = stage.status === 'running';
        const isFailed = stage.status === 'failed';
        const isSkipped = stage.status === 'skipped';
        const isPending = stage.status === 'pending';

        return (
          <div key={stage.name} className={`stage-step stage-step-${stage.status}`}>
            <div className="stage-marker-col">
              <div className={`stage-marker marker-${stage.status}`}>
                {isRunning && <span className="marker-pulse" />}
                {isCompleted && <span className="marker-check">✓</span>}
                {isFailed && <span className="marker-x">✕</span>}
                {(isPending || isSkipped) && <span className="marker-dot">·</span>}
              </div>
              {index < stages.length - 1 && (
                <div className={`stage-line line-${stage.status}`} />
              )}
            </div>

            <div className="stage-body">
              <div className="stage-headline">
                <span className="stage-title font-mono">{stage.display_name}</span>
                <span className={`stage-status-tag ${
                  isCompleted ? 'badge-emerald' :
                  isRunning ? 'badge-yellow' :
                  isFailed ? 'badge-rose' :
                  'badge-pill'
                }`}>
                  {stage.status}
                </span>
              </div>

              {!compact && stage.message && (
                <p className="stage-desc">{stage.message}</p>
              )}

              {isRunning && stage.progress_pct > 0 && (
                <div className="stage-progress-bar-wrap">
                  <div className="progress-bar">
                    <div
                      className="progress-bar-fill"
                      style={{ width: `${stage.progress_pct}%` }}
                    />
                  </div>
                  <span className="stage-pct-label font-mono">{stage.progress_pct}%</span>
                </div>
              )}

              {isFailed && stage.error && (
                <div className="stage-error-block font-mono">
                  <span>ERR:</span> {stage.error}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default StageProgress;
