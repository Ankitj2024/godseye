# God's Eye: System Scope, Architecture & Context

> **Document Status**: Comprehensive Context & Architectural Reference  
> **Last Updated**: September 2026  
> **Repository**: `Godseye` (Backend-first Drone-to-3D Spatial AI Pipeline)

---

## 1. Executive Summary & Vision

**God's Eye** is a backend-first spatial AI and 3D scene reconstruction pipeline. It transforms raw drone aerial video (typically ~10-minute 4K sweeps) into structured, queryable 3D world models and exportable scene assets (`GLB`, `PLY`, `OBJ`, plus semantic/scene graph metadata).

### The Core Promise
> *"Give God's Eye one drone video path. Get back a usable 3D world model."*

### The Backend-Only Pivot
The project intentionally eschews frontend/web dashboard complexity (no React UI, no upload web portal, no live streaming frontend). All computational and engineering effort is concentrated directly into the reconstruction fidelity, spatial intelligence, and pipeline robustness. The system operates via a single local CLI entrypoint (`run_pipeline.py`) that drives local control-plane orchestration while delegating compute-heavy operations to cloud workers on **Modal**.

---

## 2. System Architecture: Control Plane vs. Compute Plane

God's Eye employs a strict bifurcation between local management and cloud compute:

```
                      +------------------------------------------+
                      |               LOCAL MACHINE              |
                      |              (Control Plane)             |
                      |                                          |
                      |  - CLI & Config (Typer, Rich, Pydantic)  |
                      |  - Video Probing & Staging (OpenCV)      |
                      |  - Frame Extraction & Keyframe Selection |
                      |  - Manifest Store (Atomic JSON state)    |
                      |  - Pipeline Runner & Stage Transitions   |
                      |  - Final Output Packaging                |
                      +--------------------+---------------------+
                                           |
                                  Modal Volume Sync
                             (godseye-jobs /jobs prefix)
                                           |
                      +--------------------+---------------------+
                      |               MODAL CLOUD                |
                      |             (Compute Plane)              |
                      |                                          |
                      |  Worker: Diagnostics (ping / debian)     |
                      |  Worker: COLMAP Exact Reconstruction     |
                      |          (CUDA / SIFT / Dense Stereo)    |
                      |  Worker: Geometry Postprocess            |
                      |          (Open3D / Poisson Mesh / GLB)   |
                      |  Worker: (Planned) Depth Enhancement     |
                      |  Worker: (Planned) Semantic Detection    |
                      |  Worker: (Planned) Generative Completion |
                      +------------------------------------------+
```

### Architectural Principles
1. **Local Control Plane**: The local machine owns the filesystem, job ID generation, input video validation, candidate frame decoding, intelligent keyframe curation, manifest persistence, error tracking, and deliverable packaging.
2. **Compute Plane on Modal**: GPU-heavy and environment-sensitive tasks (COLMAP with CUDA, Open3D mesh generation on Python 3.11) run containerized in Modal.
3. **Volume as Shared State**: Intermediate data between cloud stages (e.g., COLMAP point clouds fed into Open3D) remain on the Modal Volume (`godseye-jobs`), avoiding costly round-trips back to the local host.
4. **Single Source of Truth**: There is no SQL/NoSQL database. Each job's complete lifecycle is atomically recorded in `work/<job_id>/manifest.json`.

---

## 3. Repository Directory Structure

```text
Godseye/
├── run_pipeline.py               # Root executable entrypoint (passes through to godseye CLI)
├── pyproject.toml                # Project metadata, dependencies, ruff & pytest config
├── requirements.txt              # Pinned requirements for the LOCAL orchestrator
├── prd.md                        # Product Requirements Document
├── architecture.md               # Backend-only system architecture specification
├── development_plan.md           # Step-wise 12-phase development roadmap
├── context.md                    # System context & reference guide (this document)
├── sample.mp4                    # Sample drone video for testing and local runs
│
├── modal_app/                    # Modal Compute Plane Application
│   ├── app.py                    # Deployment entrypoint (`modal deploy modal_app/app.py`)
│   ├── diagnostics.py            # Diagnostic ping worker for `godseye doctor`
│   ├── common/                   # Shared Modal utilities
│   │   ├── app.py                # `modal.App("godseye")` declaration
│   │   ├── config.py             # Compute configurations (CPUs, GPUs, memory, timeouts)
│   │   ├── results.py            # Uniform RemoteStageResult envelopes (success/failure)
│   │   ├── shell.py              # Subprocess execution with live logging
│   │   └── volumes.py            # `modal.Volume.from_name("godseye-jobs")` helpers
│   ├── reconstruction/           # COLMAP SfM & Dense Stereo Worker
│   │   ├── colmap.py             # Subprocess driver for feature extractor, matcher, mapper
│   │   ├── image.py              # Modal CUDA container definition with COLMAP
│   │   └── worker.py             # `reconstruct_exact` remote function
│   └── geometry/                 # Open3D Geometry Postprocessing Worker
│       ├── image.py              # Modal container definition (Python 3.11, Open3D, trimesh)
│       └── worker.py             # `postprocess_geometry` function (cleaning, Poisson mesh, GLB)
│
├── src/godseye/                  # God's Eye Core Python Package
│   ├── config.py                 # Pydantic Settings (env overrides with GODSEYE_ prefix)
│   ├── errors.py                 # Custom exception hierarchy with failure origin tracking
│   ├── artifacts/                # Output document builders and deliverable packaging
│   │   ├── documents.py          # scene.json, objects.json, confidence.json, run_summary.json
│   │   └── packaging.py          # Deliverable collector, log copier, hash verify
│   ├── cli/                      # Typer CLI implementation
│   │   └── app.py                # Commands: run, resume, stages, inspect, doctor
│   ├── orchestrator/             # Job lifecycle and execution engine
│   │   ├── bootstrap.py          # Job initialization, video probe, hardlink/copy staging
│   │   ├── job.py                # JobPaths resolver and timestamped job ID generator
│   │   ├── manifest_store.py     # Thread-safe atomic manifest.json reader/writer
│   │   └── runner.py             # PipelineRunner stage execution loop, resume & skip logic
│   ├── pipeline/                 # Stage contracts and pipeline composition
│   │   ├── context.py            # StageContext (manifest, paths, config, remote transport)
│   │   ├── registry.py           # Pipeline definitions for EXACT and GENERATIVE modes
│   │   └── stage.py              # Stage base class, StageOutcome, NotImplementedStage
│   ├── remote/                   # Modal execution transport layer
│   │   └── transport.py          # ModalTransport (Volume upload/download, function spawn/poll)
│   ├── schemas/                  # Data contracts and serialization models
│   │   ├── enums.py              # PipelineMode, StageName, StageStatus, Provenance, etc.
│   │   ├── manifest.py           # JobManifest, StageRecord, ArtifactRecord, VideoMetadata
│   │   ├── remote.py             # ReconstructionRequest, GeometryRequest, RemoteStageResult
│   │   └── scene.py              # SceneDocument, SceneObject, SceneGraph, Confidence models
│   ├── stages/                   # Pipeline stage implementations
│   │   ├── frame_extraction.py   # Local candidate frame extraction via OpenCV
│   │   ├── keyframe_selection.py # Local blur, novelty, and spacing scoring
│   │   ├── reconstruction_exact.py # Modal COLMAP SfM stage
│   │   ├── geometry_postprocess.py # Modal Open3D mesh & GLB export stage
│   │   ├── output_packaging.py   # Local final deliverable packaging to outputs/<job_id>
│   │   └── remote_stage.py       # Base class for Modal-dispatched stages
│   └── utils/                    # Utility helpers
│       ├── fs.py                 # File manipulation, atomic writes, size formatters
│       ├── hashing.py            # SHA-256 calculation
│       ├── logging.py            # Rich logging & stage-specific log routing
│       └── video.py              # OpenCV video probing and metadata extraction
│
├── tests/                        # Pytest Test Suite
│   ├── conftest.py               # Shared fixtures, temporary workspaces, synthetic data
│   ├── test_colmap_parsers.py    # COLMAP text model & PLY parser tests
│   ├── test_documents_and_contracts.py # JSON output document schema validation
│   ├── test_keyframes.py         # Sharpness, novelty, and uniform subsampling tests
│   ├── test_manifest.py          # ManifestStore atomic write, update, and resume tests
│   ├── test_pipeline_runner.py   # PipelineRunner execution, skip, and error handling
│   └── test_reconstruction_gate.py # Reconstruction registration threshold gate tests
│
├── assets/                       # Local 3D proxy asset library for generative completion
├── work/                         # Local per-job working directories (intermediate artifacts)
└── outputs/                      # Local per-job final deliverables
```

---

## 4. Pipeline Stages & Execution Flow

The full pipeline spans 10 logical stages executed in strict order.

| # | Stage Name | Target | Status | Description |
|---|------------|--------|--------|-------------|
| 0 | `job_setup` | Local | **Implemented** | Validates video, extracts metadata (probe), hard-links video to `work/<job_id>/input/`, initializes `manifest.json`. |
| 1 | `frame_extraction` | Local | **Implemented** | Decodes video at planned stride (e.g. 2 fps), resizes to max width (1080p/1920px), writes candidates and `candidates.json`. |
| 2 | `keyframe_selection` | Local | **Implemented** | Scores candidate frames on sharpness (Laplacian variance), novelty (signature delta), and spacing. Subsamples to `target_count` (e.g. 200). |
| 3 | `reconstruction_exact` | Modal (GPU) | **Implemented** | Uploads keyframes to Modal Volume; runs COLMAP feature extraction, matching (exhaustive/sequential), and SfM mapping; verifies registration gate. |
| 4 | `geometry_postprocess` | Modal (CPU) | **Implemented** | Reads COLMAP output directly from Volume; applies Open3D voxel downsampling, statistical outlier removal, kNN normals, Poisson meshing, and exports `exact_scene.glb`. |
| 5 | `depth_enhancement` | Modal (GPU) | *Phase 9 (Scaffolded)* | Monocular depth estimation to densify and strengthen weak geometry regions. |
| 6 | `semantic_detection` | Modal (GPU) | *Phase 7 (Scaffolded)* | 3D oriented bounding box / cuboid detection for spatial objects. |
| 7 | `scene_graph` | Local | *Phase 8 (Scaffolded)* | Generates nodes, spatial relationships, and hierarchy between detected objects. |
| 8 | `generative_completion` | Modal (GPU) | *Phase 10 (Scaffolded)* | Inserts proxy 3D assets from `assets/` to complete occluded/ambiguous regions (Generative mode only). |
| 9 | `output_packaging` | Local | **Implemented** | Collects deliverables into `outputs/<job_id>/`, writes `scene.json`, `objects.json`, `scene_graph.json`, `confidence.json`, `run_summary.json`. |

### Unimplemented Stage Handling: "Absence Stated, Never Implied"
Stages 5, 6, 7, and 8 are registered in `godseye.pipeline.registry` as `NotImplementedStage`. When the pipeline runs:
- The runner marks them as `SKIPPED` with an explicit reason citing the roadmap phase.
- `output_packaging` emits schema-valid JSON documents (`objects.json`, `scene_graph.json`) with `generated: false` and explicit diagnostic reasons. Consumers are never left guessing whether data failed or was simply not produced.

---

## 5. Exact vs. Generative Reconstruction Modes

God's Eye defines two operational modes via `--mode`:

### 1. Exact Mode (`--mode exact`)
- **Philosophy**: Pure empirical fidelity. Geometry reflects only what was triangulated from camera observations.
- **Behavior**: Sparse or unobserved regions remain empty. No synthetic fill or proxy assets are hallucinated.
- **Output Deliverable**: `exact_scene.glb`, `pointcloud.ply`, `mesh.obj`, `mesh.ply`.

### 2. Generative Mode (`--mode generative`)
- **Philosophy**: Usability in downstream simulation/rendering where holes and missing objects are unacceptable.
- **Behavior**: Starts strictly from the `exact` baseline. Identifies weak or missing objects, matches them to semantic classes, and retrieves proxy meshes from `assets/`.
- **Output Separation**: Exact and generative outputs are kept strictly distinct (`exact_scene.glb` vs. `generative_scene.glb`). Provenance tags (`observed` vs. `inferred`) guarantee full traceability.

---

## 6. Data Contracts & On-Disk Storage Model

### Working Directory Layout: `work/<job_id>/`
Every job receives an isolated workspace keyed by `YYYYmmdd-HHMMSS-xxxxxx`:
```text
work/<job_id>/
├── input/
│   └── video.mp4                 # Hard-linked (or copied) source video
├── frames/
│   ├── candidates/               # All extracted frames (cand_000000.jpg, ...)
│   ├── candidates.json           # Candidate frame index & metadata
│   ├── selected/                 # Curated keyframes (frame_00001.jpg, ...)
│   └── selection.json            # Selection scores & threshold metrics
├── reconstruction/               # Downloaded COLMAP outputs
│   ├── sparse_points.ply
│   ├── dense_points.ply
│   ├── model/ (cameras.txt, images.txt, points3D.txt)
│   └── logs/
├── geometry/                     # Downloaded Open3D outputs
│   ├── exact_scene.glb
│   ├── pointcloud_clean.ply
│   ├── mesh.ply / mesh.obj
│   └── logs/
├── logs/                         # Detailed logs per stage
│   ├── pipeline.log
│   ├── frame_extraction.log
│   ├── keyframe_selection.log
│   ├── reconstruction_exact.log
│   └── geometry_postprocess.log
└── manifest.json                 # Authoritative state machine
```

### Output Directory Layout: `outputs/<job_id>/`
The final deliverable package copied at the end of the run:
```text
outputs/<job_id>/
├── exact_scene.glb               # Primary 3D scene (mesh or point cloud GLB)
├── pointcloud.ply                # Cleaned dense point cloud
├── mesh.obj / mesh.ply           # Poisson reconstructed mesh
├── cameras/                      # Camera poses from SfM
├── scene.json                    # Top-level scene description & bounds
├── objects.json                  # Semantic 3D object list (generated: false currently)
├── scene_graph.json              # Scene hierarchy & relations (generated: false currently)
├── confidence.json               # Spatial confidence & observed point counts
├── run_summary.json              # High-level execution summary, timing, warnings
├── manifest.json                 # Snapshot of the complete job manifest
└── logs/                         # Preserved execution logs for auditing
```

---

## 7. Remote Worker Architecture & Infrastructure (Modal)

The compute plane is deployed with `modal deploy modal_app/app.py` under the app name `godseye`.

### Containers & Worker Definitions
1. **Diagnostics (`ping`)**:
   - Image: `debian_slim` with Python 3.11.
   - Purpose: Verifies API token, Volume mount accessibility, and write permissions in seconds.
2. **Reconstruction (`reconstruct_exact`)**:
   - Image: `colmap/colmap:latest` official CUDA image with SIFT and patch-match stereo support.
   - Resources: GPU assigned (`COLMAP_GPU = "T4"` or configured), 8 CPU cores, 32GB RAM, 6-hour timeout.
   - Storage Strategy: Intermediate dense stereo depth maps (which can number tens of thousands) are processed on container-local `/tmp/godseye/workspace` to prevent Volume IOPS throttling. Only final models and PLYs are committed to the Volume.
   - Registration Quality Gate: Enforces `min_registered_images` (default 5) and `min_registration_ratio` (default 50%). If a flight path lacks parallax and COLMAP only registers a tiny fraction of frames, it fails early with actionable user advice rather than producing a deceptive, broken point cloud.
3. **Geometry Postprocessing (`postprocess_geometry`)**:
   - Image: `debian_slim` pinned to Python 3.11 with Open3D 0.19, trimesh 4.7, pygltflib, scipy, numpy.
   - Rationale: Open3D does not publish wheels for Python 3.13, making local installation on modern developer systems problematic. Containerizing it in Python 3.11 on Modal ensures 100% reproducibility.
   - Process: Direct ingestion from Volume `reconstruction/` prefix $\rightarrow$ Statistical outlier removal $\rightarrow$ Scale-free kNN normal estimation $\rightarrow$ Poisson surface reconstruction $\rightarrow$ Density quantile vertex trimming $\rightarrow$ Quadric decimation to target triangle budget $\rightarrow$ GLB/PLY/OBJ generation.

---

## 8. CLI Interface & Operational Usage

The command-line interface is powered by Typer and Rich:

### Common Commands
```bash
# 1. Run full reconstruction pipeline on a drone video
python run_pipeline.py --video ./sample.mp4 --mode exact

# 2. Run with custom keyframe density or toggle dense stereo
python run_pipeline.py --video ./sample.mp4 --mode exact --max-keyframes 150 --no-dense

# 3. Resume an interrupted or failed job (skips already completed stages)
python run_pipeline.py resume 20260826-154412-59e7f2

# 4. Force rerun of a specific stage during resume
python run_pipeline.py resume 20260826-154412-59e7f2 --force-stage reconstruction_exact

# 5. Inspect a past job's manifest and metrics
python run_pipeline.py inspect 20260826-154412-59e7f2

# 6. View the ordered stage pipeline
python run_pipeline.py stages --mode exact

# 7. Run system doctor to check local dependencies and Modal connectivity
python run_pipeline.py doctor
```

### Configuration via Environment Variables
All configuration fields in `src/godseye/config.py` can be overridden via `.env` or environment variables using the `GODSEYE_` prefix and double underscores:
```bash
export GODSEYE_MODAL__APP_NAME="godseye"
export GODSEYE_MODAL__VOLUME_NAME="godseye-jobs"
export GODSEYE_FRAMES__SAMPLE_FPS="2.0"
export GODSEYE_KEYFRAMES__TARGET_COUNT="200"
export GODSEYE_RECONSTRUCTION__RUN_DENSE="true"
export GODSEYE_RECONSTRUCTION__MATCHER="auto"  # auto | exhaustive | sequential
export GODSEYE_GEOMETRY__POISSON_DEPTH="10"
```

---

## 9. Current Implementation Status vs. Roadmap

| Phase | Description | Status | Implemented Components |
|-------|-------------|--------|------------------------|
| **Phase 0** | Project Skeleton & Conventions | **Done** | Root structure, `modal_app/`, `src/godseye/`, schemas |
| **Phase 1** | CLI Entrypoint | **Done** | `run_pipeline.py`, Typer app with `run`, `resume`, `doctor` |
| **Phase 2** | Job Manifest & File-Based State | **Done** | Atomic `manifest.json`, `ManifestStore`, `JobPaths` |
| **Phase 3** | Frame Extraction & Keyframe Selection | **Done** | OpenCV candidate extraction, Laplacian variance, novelty |
| **Phase 4** | Modal Integration Foundation | **Done** | `ModalTransport`, Volume upload/download, remote error handling |
| **Phase 5** | Exact Reconstruction Baseline | **Done** | COLMAP worker, sparse & dense stereo, registration gate |
| **Phase 6** | Root Output Packaging | **Done** | Deliverable copy to `outputs/<job_id>/`, scene JSON generation |
| **Phase 7** | Semantic Object Detection | *Planned* | Schema ready; scaffolded as `NotImplementedStage` |
| **Phase 8** | Confidence & Scene Graph | *Partial* | Basic confidence document implemented; scene graph scaffolded |
| **Phase 9** | Depth Enhancement | *Planned* | Schema ready; scaffolded as `NotImplementedStage` |
| **Phase 10**| Generative Reconstruction | *Planned* | Pipeline mode wired; asset mapping scaffolded |
| **Phase 11**| Hardening & Performance | **In Progress** | 56 passing unit tests, resume capability, detailed error provenance |
| **Phase 12**| Advanced Improvements | *Backlog* | Metric scaling, LOD generation, on-prem worker fallback |

---

## 10. Key Insights, Constraints & Considerations

1. **Scale Ambiguity**: Pure SfM without RTK-GPS or ground control targets produces scale-free geometry. The scene coordinate frame is marked in `scene.json` as arbitrary COLMAP world units (`scale_is_metric: false`).
2. **Parallax Requirement**: Drone video that only pans/rotates on a gimbal or moves purely forward along its optical axis will fail triangulation in COLMAP. Keyframe selection and reconstruction parameters (`init_min_tri_angle`, `init_max_forward_motion`) are tuned specifically for oblique aerial sweep footage.
3. **Data Sovereignity & Modal Tradeoff**: The system is designed to be local-first, but Modal execution means video keyframes temporarily reside on cloud volumes. The pipeline and stage interfaces are deliberately abstract (`ExecutionTarget.MODAL` vs `LOCAL`) to allow swapping Modal workers for local or on-premise GPU clusters without altering the orchestration layer.
4. **Resilience without UI**: Because there is no web frontend, the system relies on structured error recording (`error.origin = LOCAL | MODAL`), detailed per-stage logs in `outputs/<job_id>/logs/`, and a comprehensive `run_summary.json` generated on every run (success, failure, or partial).
