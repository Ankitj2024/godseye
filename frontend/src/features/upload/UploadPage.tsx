import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import FileDropzone from '../../components/FileDropzone';
import { createJob } from '../../lib/api';
import type { ReconstructionMode } from '../../types/job';
import './UploadPage.css';

function UploadPage() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<ReconstructionMode>('exact');
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState('');

  const handleFileSelect = useCallback((f: File) => {
    setFile(f);
    setError('');
  }, []);

  const handleSubmit = async () => {
    if (!file) return;

    setUploading(true);
    setUploadProgress(0);
    setError('');

    try {
      const job = await createJob(file, mode, (pct) => setUploadProgress(pct));
      navigate(`/jobs/${job.job_id}`);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Upload failed';
      setError(message);
      setUploading(false);
    }
  };

  return (
    <div className="upload-page">
      {/* Hero 7/5 Grid */}
      <section className="hero-section container">
        <div className="hero-grid">
          {/* Left Column: Headline & Upload Form */}
          <div className="hero-left">
            <div className="hero-badge-wrap">
              <span className="badge-yellow">SPATIAL AI PIPELINE</span>
              <span className="badge-pill font-mono">LOCAL-FIRST</span>
            </div>

            <h1 className="hero-heading display-xl">
              Turn drone video into 3D world models.
            </h1>

            <p className="hero-subhead body-md">
              Ingest a single aerial video stream. Generate dense photogrammetric geometry, 
              learned depth maps, and 3D semantic bounding objects in an automated asynchronous pipeline.
            </p>

            {/* Mode Selector */}
            <div className="mode-selection-group">
              <span className="section-label caption-uppercase">RECONSTRUCTION MODE</span>
              <div className="mode-cards-grid">
                <button
                  type="button"
                  className={`mode-card ${mode === 'exact' ? 'mode-card-active' : ''}`}
                  onClick={() => !uploading && setMode('exact')}
                  disabled={uploading}
                >
                  <div className="mode-card-header">
                    <span className="mode-title title-sm">Exact Reconstruction</span>
                    {mode === 'exact' && <span className="mode-check-pill">SELECTED</span>}
                  </div>
                  <p className="mode-description body-sm">
                    Deterministic SfM + dense meshing. Preserves strict observational gaps where coverage is sparse.
                  </p>
                </button>

                <button
                  type="button"
                  className={`mode-card ${mode === 'generative' ? 'mode-card-active' : ''}`}
                  onClick={() => !uploading && setMode('generative')}
                  disabled={uploading}
                >
                  <div className="mode-card-header">
                    <span className="mode-title title-sm">Generative Augmentation</span>
                    {mode === 'generative' && <span className="mode-check-pill">SELECTED</span>}
                  </div>
                  <p className="mode-description body-sm">
                    AI-assisted scene completion. Inferred 3D geometric proxies populate ambiguous or occluded regions.
                  </p>
                </button>
              </div>
            </div>

            {/* Dropzone */}
            <div className="upload-box-wrap">
              <FileDropzone onFileSelect={handleFileSelect} disabled={uploading} />
            </div>

            {/* Upload Progress */}
            {uploading && (
              <div className="upload-progress-card surface-card">
                <div className="upload-progress-row">
                  <span className="font-mono body-sm">STREAMING_INPUT_PAYLOAD</span>
                  <span className="font-mono stat-pct">{uploadProgress}%</span>
                </div>
                <div className="progress-bar">
                  <div className="progress-bar-fill" style={{ width: `${uploadProgress}%` }} />
                </div>
              </div>
            )}

            {/* Error Message */}
            {error && (
              <div className="upload-error-box font-mono">
                <span>✕ ERROR:</span> {error}
              </div>
            )}

            {/* Primary Action Button */}
            <div className="upload-cta-row">
              <button
                type="button"
                className="button-primary submit-cta"
                onClick={handleSubmit}
                disabled={!file || uploading}
              >
                {uploading ? (
                  <>
                    <span className="animate-spin">◈</span>
                    INITIALIZING PIPELINE...
                  </>
                ) : (
                  <>
                    START RECONSTRUCTION JOB
                    <span>→</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Right Column: Code Window Card & Live Stat Callouts */}
          <div className="hero-right">
            {/* Terminal / Code Window Mockup */}
            <div className="code-window-card">
              <div className="code-window-header">
                <div className="window-dots">
                  <span className="dot" />
                  <span className="dot" />
                  <span className="dot" />
                </div>
                <span className="window-title">godseye-pipeline.sh</span>
                <span className="badge-emerald font-mono">ENGINE ACTIVE</span>
              </div>
              <pre className="code-content">
                <code>
                  <span className="code-comment"># Stage 1: Fast keyframe selection</span>{'\n'}
                  <span className="code-keyword">godseye</span> extract --input video.mp4 --heuristic laplacian_variance{'\n'}
                  <span className="code-output">✓ Filtered 14,200 frames → 180 optimal keyframes</span>{'\n\n'}
                  <span className="code-comment"># Stage 2: Classical SfM pose solving</span>{'\n'}
                  <span className="code-keyword">colmap</span> feature_extractor --database_path sfm.db{'\n'}
                  <span className="code-keyword">colmap</span> exhaustive_matcher --database_path sfm.db{'\n'}
                  <span className="code-output">✓ Estimated 180 camera extrinsics | 99.4% inliers</span>{'\n\n'}
                  <span className="code-comment"># Stage 3: Monocular depth & 3D Bounding</span>{'\n'}
                  <span className="code-keyword">depth_anything_v2</span> --fuse_sparse sparse.ply{'\n'}
                  <span className="code-keyword">yolo_world_3d</span> --taxonomy [building, vehicle, road]{'\n'}
                  <span className="code-output">✓ 34 cuboid nodes registered to scene_graph.json</span>{'\n\n'}
                  <span className="code-comment"># Stage 4: Package exportable world model</span>{'\n'}
                  <span className="code-keyword">godseye</span> package --format glb --out scene.glb{'\n'}
                  <span className="code-highlight">→ Ready for interactive inspection</span>
                </code>
              </pre>
            </div>

            {/* Stat Callout Strip */}
            <div className="hero-stats-grid">
              <div className="stat-unit">
                <span className="stat-display">180</span>
                <span className="stat-label caption-uppercase">MAX KEYFRAMES</span>
                <p className="stat-desc body-sm">Optimal frame coverage filtered automatically from 10-minute video</p>
              </div>

              <div className="stat-unit">
                <span className="stat-display">8+</span>
                <span className="stat-label caption-uppercase">3D SEMANTIC CLASSES</span>
                <p className="stat-desc body-sm">Oriented bounding cuboids tagged directly in scene graph</p>
              </div>

              <div className="stat-unit">
                <span className="stat-display">&lt;15m</span>
                <span className="stat-label caption-uppercase">AVERAGE RUNTIME</span>
                <p className="stat-desc body-sm">Asynchronous end-to-end processing with persistent artifact caching</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Feature Section: 3-Up Cards */}
      <section className="features-band container">
        <div className="section-head">
          <span className="caption-uppercase">CORE CAPABILITIES</span>
          <h2 className="display-md">Built for mission-critical aerial intelligence.</h2>
        </div>

        <div className="feature-cards-grid">
          <div className="surface-card feature-item">
            <span className="feature-index font-mono">01 / DENSE RECONSTRUCTION</span>
            <h3 className="title-lg">Deterministic Structure-from-Motion</h3>
            <p className="body-md">
              Extract accurate sparse point clouds and multi-view dense geometry using industry-standard COLMAP solvers and Open3D surface generation.
            </p>
          </div>

          <div className="surface-card feature-item">
            <span className="feature-index font-mono">02 / SPATIAL UNDERSTANDING</span>
            <h3 className="title-lg">Object-Level 3D Semantics</h3>
            <p className="body-md">
              Detect buildings, vehicles, trees, and infrastructure with orientation and metric volume extents, organized in a queryable scene graph.
            </p>
          </div>

          <div className="surface-card feature-item">
            <span className="feature-index font-mono">03 / HONEST CONFIDENCE</span>
            <h3 className="title-lg">Layered Generative Completion</h3>
            <p className="body-md">
              Clearly separate measured physical geometry from AI-inferred proxies. Inspect uncertainty with confidence maps before exporting.
            </p>
          </div>
        </div>
      </section>

      {/* Yellow CTA Band */}
      <section className="cta-band-section container">
        <div className="feature-card-yellow cta-band-content">
          <div className="cta-band-text">
            <span className="caption-uppercase" style={{ color: '#0a0a0a' }}>AIR-GAPPED & ENTERPRISE READY</span>
            <h2 className="display-md" style={{ color: '#0a0a0a' }}>
              Full sovereignty on your own infrastructure.
            </h2>
            <p className="body-md" style={{ color: '#2a2a2a' }}>
              Designed to transition seamlessly from remote GPU acceleration to on-premise dedicated clusters.
            </p>
          </div>
          <button
            type="button"
            className="button-secondary"
            style={{ backgroundColor: '#0a0a0a', color: '#ffffff', borderColor: '#0a0a0a' }}
            onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          >
            LAUNCH DEMO
          </button>
        </div>
      </section>
    </div>
  );
}

export default UploadPage;
