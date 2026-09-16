# God's Eye — Complete Viva Preparation Guide

> **One-liner**: *"Give God's Eye one drone video. Get back a metrically accurate, semantically enriched, textured 3D world model."*

---

## 1. Problem Statement (In Brief)

Traditional 3D reconstruction of terrain, buildings, and infrastructure requires **multiple drone passes**, extensive image overlap, and heavy post-processing. In time-critical scenarios — disaster response, military reconnaissance, infrastructure inspection — you often get **only one chance** to fly over the target.

**God's Eye** solves this by generating a georeferenced, textured, semantically enriched 3D model from a **single-pass drone video**.

---

## 2. System Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────┐
│                    LOCAL MACHINE (Control Plane)             │
│                                                             │
│  CLI + Config (Typer, Rich, Pydantic)                       │
│  Video Probing & Staging (OpenCV)                           │
│  Frame Extraction & Keyframe Selection                      │
│  Manifest Store (Atomic JSON state machine)                 │
│  Pipeline Runner & Stage Transitions                        │
│  Scene Graph Generation                                     │
│  Final Output Packaging                                     │
└───────────────────────┬─────────────────────────────────────┘
                        │ Modal Volume Sync
                        │ (godseye-jobs /jobs prefix)
┌───────────────────────▼─────────────────────────────────────┐
│                    MODAL CLOUD (Compute Plane)               │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ COLMAP SfM   │  │ Open3D Mesh  │  │ Depth-Any-V2 │      │
│  │ (GPU: A10G)  │  │ (CPU: 8-core)│  │ (GPU: A10G)  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ OWLv2 Detect │  │ Semantic Mask│  │ Generative   │      │
│  │ (GPU: A10G)  │  │ (GPU: A10G)  │  │ Completion   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### Key Architectural Decisions

| Decision | Rationale |
|---|---|
| **Local control plane, cloud compute plane** | Keeps orchestration simple; offloads GPU-heavy tasks to Modal serverless GPUs |
| **No database — file-based `manifest.json`** | Each job's lifecycle is a single atomic JSON file. Simple, auditable, no ORM overhead |
| **DAG of stages** | Stages run in strict order, each producing deterministic artifacts. Any stage can be rerun independently |
| **Volume as shared state** | Intermediate results stay on Modal Volume between cloud stages — avoids costly downloads/re-uploads |
| **Exact vs Generative separation** | Measured geometry (`exact_scene.glb`) and AI-inferred geometry (`generative_scene.glb`) are never mixed |

---

## 3. Complete Pipeline (10 Stages)

### Stage 0 — Job Setup (Local, CPU)
- Validates video file (format, existence, codec probe via OpenCV)
- Generates a unique job ID (`YYYYmmdd-HHMMSS-xxxxxx`)
- Creates isolated workspace: `work/<job_id>/`
- Initializes `manifest.json` as the single source of truth

### Stage 1 — Frame Extraction (Local, CPU)
- **Tool**: OpenCV (`cv2.VideoCapture`)
- Decodes video at configurable FPS stride (default: **6 fps**)
- Resizes to max 1920px width
- Writes candidate frames as high-quality JPEGs (quality=95)
- A 10-min 4K video → ~3,600 candidate frames
- **Output**: `frames/candidates/` + `candidates.json`

### Stage 2 — Keyframe Selection (Local, CPU)
- **Goal**: Reduce ~3,600 candidates to ~200 high-quality, non-redundant keyframes
- **Scoring criteria**:
  - **Sharpness**: Laplacian variance (rejects motion blur)
  - **Novelty**: Signature delta between consecutive frames (rejects near-duplicates)
  - **Spacing**: Minimum temporal gap between selected frames
- Adaptive blur threshold: relative to median sharpness (not a fixed value)
- Relaxation loop: if too few frames pass, thresholds are loosened in steps
- **Output**: `frames/selected/` + `selection.json`

### Stage 3 — Semantic Masking (Modal, GPU: A10G)
- **Model**: **OWLv2** (`google/owlv2-base-patch16-ensemble`) — zero-shot object detector
- Detects dynamic objects (vehicles, people) in keyframes
- Generates **binary mask images** (white=keep, black=ignore)
- These masks are fed to COLMAP so it ignores moving objects during reconstruction
- **Why**: Moving cars/people create "ghost" geometry if included in SfM
- **Output**: per-frame `.png` masks on Modal Volume

### Stage 4 — Exact Reconstruction (Modal, GPU: A10G)
- **Tool**: **COLMAP** (official CUDA image)
- This is the **core 3D reconstruction engine**. Three sub-steps:

| Sub-step | What it does | Detail |
|---|---|---|
| **Feature Extraction** | Detects SIFT keypoints in every keyframe | Up to 40,000 features per image |
| **Feature Matching** | Finds corresponding points across image pairs | Exhaustive for ≤150 images, sequential otherwise |
| **Sparse Mapping (SfM)** | Triangulates camera poses + 3D points from matches | Produces sparse point cloud + camera intrinsics/extrinsics |

- **Dense Stereo** (optional): Runs PatchMatch multi-view stereo to generate a high-density point cloud
- **Registration Quality Gate**: If <50% of keyframes register or <5 images register → fails early with actionable advice (e.g. "footage lacks parallax")
- **Aerial-specific tuning**: `init_min_tri_angle=4°` (relaxed from default 16°) because drone footage often has small baseline triangulation angles
- **Output**: `sparse_points.ply`, `dense_points.ply`, camera poses (`cameras.txt`, `images.txt`, `points3D.txt`)

### Stage 5 — Geometry Post-Processing (Modal, CPU: 8-core)
- **Tool**: **Open3D** (v0.19) + **trimesh**
- Takes the raw COLMAP point cloud and produces a clean, textured mesh:

| Step | Method | Purpose |
|---|---|---|
| Voxel downsample | Auto-enabled if >8M points | Reduces density for tractable meshing |
| Statistical outlier removal | 30 neighbors, 1.5σ | Removes floating/noisy points |
| Normal estimation | kNN=50 (scale-free) | SfM output has no metric scale, so radius-based normals would fail |
| **Poisson surface reconstruction** | depth=12 | Fits a smooth implicit surface through the point cloud |
| Density trimming | 12th percentile | Removes low-confidence extrapolated surface regions |
| Quadric decimation | Target: 1M triangles | Keeps mesh viewable in real-time |
| **KD-Tree color transfer** | kNN=1 | Poisson mesh loses vertex colors; this projects them back from the source cloud |

- **Output**: `exact_scene.glb`, `mesh.ply`, `mesh.obj`, `pointcloud_clean.ply`

### Stage 6 — Depth Enhancement (Modal, GPU: A10G)
- **Model**: **Depth-Anything-V2-Small** (HuggingFace Transformers pipeline)
- Estimates per-pixel monocular depth on keyframes
- **Critical innovation — Metric Alignment via Least-Squares**:
  1. Projects known COLMAP 3D points into each camera frame
  2. Samples the monocular depth at those pixel locations
  3. Solves `z_colmap = scale × z_mono + shift` via least-squares
  4. Applies the scale+shift to anchor the entire depth map to COLMAP's metric coordinate system
- Unprojects aligned depth maps (every 4th pixel) into 3D world coordinates
- **Purpose**: Fills in **textureless regions** (flat roofs, roads, water) where COLMAP's feature-based stereo fails
- **Output**: `depth_pointcloud.ply` + sample depth map previews

### Stage 7 — Semantic Detection (Modal, GPU: A10G)
- **Model**: **OWLv2** (`google/owlv2-base-patch16-ensemble`) — zero-shot object detection
- **Target classes**: vehicle, building, tree, road, person
- Detection → 3D projection pipeline:
  1. Runs OWLv2 on ~15 evenly-spaced keyframes
  2. For each 2D bounding box, projects the box center into 3D using the COLMAP camera pose
  3. Estimates depth by finding COLMAP points that fall inside the bounding box
  4. Computes 3D world coordinates: `X_world = R^T × (X_cam - T)`
  5. Estimates 3D dimensions from box size and depth: `dim = box_pixels × depth / focal_length`
  6. **Cross-frame merging**: Clusters detections within 3 scene units into a single object
- **Output**: `objects.json` with object ID, class, 3D center, dimensions, confidence, provenance

### Stage 8 — Scene Graph Generation (Local, CPU)
- **Input**: `objects.json` from semantic detection
- Builds a **topological graph** of spatial relationships:
  - **Nodes**: Terrain (ground context) + every detected object
  - **Edges**:
    - `supports`: terrain → object (every object rests on ground)
    - `near`: objects within combined footprint + 3m buffer
    - `above`: vertically stacked objects with horizontal overlap
- Confidence scores on every edge
- **Output**: `scene_graph.json` — queryable ("what objects are near this building?")

### Stage 9 — Generative Completion (Modal, CPU)
- **Only runs in `--mode generative`**
- Starts from the exact scene baseline
- For each detected semantic object:
  1. Checks `assets/` library for pre-authored `.glb`/`.obj` models
  2. If no match, generates **parametric proxy meshes** (e.g. box+cone for buildings, cylinder+sphere for trees, chassis+cabin for vehicles)
  3. Scales proxy to match detected 3D dimensions
  4. Translates to detected 3D world position
- **Strict separation**: `generative_scene.glb` is always distinct from `exact_scene.glb`
- All inserted objects tagged as `provenance: "inferred"`
- **Output**: `generative_scene.glb`

### Stage 10 — Output Packaging (Local, CPU)
- Downloads all artifacts from Modal Volume
- Generates JSON documents: `scene.json`, `objects.json`, `scene_graph.json`, `confidence.json`, `run_summary.json`
- Copies everything to `outputs/<job_id>/`
- Preserves all logs for post-mortem analysis

---

## 4. AI/ML Models Used — Deep Dive

| Model | Task | Architecture | Why Chosen |
|---|---|---|---|
| **COLMAP** | Structure-from-Motion + Multi-View Stereo | Classical CV (SIFT + bundle adjustment + PatchMatch) | Industry gold standard for metric 3D reconstruction from images |
| **Depth-Anything-V2-Small** | Monocular depth estimation | Vision Transformer (DINOv2 backbone) | State-of-the-art depth prediction; works on single images where stereo fails |
| **OWLv2** | Zero-shot 2D object detection | Vision Transformer with text-conditioned detection | No retraining needed — detects arbitrary classes via text prompts |
| **Open3D** | Point cloud processing + Poisson meshing | Classical computational geometry | Battle-tested for large-scale point clouds; Poisson gives watertight meshes |
| **trimesh** | 3D mesh/scene I/O and GLB export | Utility library | Clean GLB/glTF export for web viewers and downstream tools |

### How COLMAP Works (Viva Depth)

1. **SIFT Feature Extraction**: Detects scale-invariant keypoints + 128-dim descriptors per image
2. **Exhaustive/Sequential Matching**: Finds corresponding keypoints across all image pairs
3. **Incremental SfM (Bundle Adjustment)**:
   - Starts with an initial image pair with enough parallax
   - Triangulates 3D points from matched 2D keypoints
   - Registers new images by solving PnP (Perspective-n-Point)
   - Jointly optimizes all camera poses + 3D point positions (bundle adjustment)
4. **Dense Stereo (PatchMatch)**: For each pixel, finds the best depth by matching small patches across nearby views

### How Depth-Anything-V2 Works (Viva Depth)

- **Backbone**: DINOv2 Vision Transformer (self-supervised pretraining on 142M images)
- **Head**: Dense Prediction Transformer (DPT) decoder
- **Training**: Supervised on massive synthetic + real depth datasets
- **Output**: Relative depth map (not metric) — hence the need for COLMAP-based scale alignment
- **Our alignment**: Least-squares fit converts relative depth → absolute metric depth using known COLMAP 3D points as anchors

### How OWLv2 Works (Viva Depth)

- **Architecture**: ViT image encoder + text encoder
- **Zero-shot**: Provide text labels ("vehicle", "building", "tree") → model outputs bounding boxes + confidence
- **No fine-tuning required**: Works on arbitrary aerial imagery out of the box
- **Our enhancement**: 2D boxes → 3D world coordinates by ray-casting through COLMAP camera models

---

## 5. Desired Output

| Deliverable | Format | Description |
|---|---|---|
| **3D Scene Model** | `.glb` / `.gltf` | Textured mesh of terrain, buildings, infrastructure |
| **Point Cloud** | `.ply` | Dense/sparse colored point cloud |
| **Mesh** | `.ply` / `.obj` | Poisson surface reconstruction |
| **Object Metadata** | `objects.json` | 3D cuboids with class, position, dimensions, confidence |
| **Scene Graph** | `scene_graph.json` | Spatial relationships (near, above, supports) |
| **Confidence Map** | `confidence.json` | Per-region quality tiers: observed / enhanced / inferred |
| **Scene Description** | `scene.json` | Bounds, coordinate system, geometry summary, scale info |
| **Run Summary** | `run_summary.json` | Execution timing, warnings, stage statuses |
| **Depth Maps** | `.png` previews | Monocular depth estimation visualizations |

---

## 6. Evaluation Criteria

| Criterion | Metric | Target |
|---|---|---|
| **Geometric Accuracy** | Chamfer distance / RMSE to ground truth LiDAR | < 2% of scene diagonal |
| **Completeness** | % of ground truth surface covered by reconstruction | > 80% from single pass |
| **Texture Quality** | SSIM / PSNR of reprojected textures | SSIM > 0.85 |
| **Object Detection Accuracy** | mAP@50 for detected 3D objects | > 0.6 for primary classes |
| **Registration Ratio** | % keyframes successfully registered by COLMAP | > 50% (hard minimum) |
| **Processing Time** | Wall-clock time for full pipeline | < 30 min for 10-min 4K video |
| **Mesh Quality** | Triangle count, manifold-ness, no degenerate faces | 1M triangles, manifold |
| **Scale Consistency** | Depth alignment residual (COLMAP vs monocular) | R² > 0.9 |
| **Semantic Correctness** | Precision/Recall for 3D object classes | Precision > 0.7 |
| **Scene Graph Validity** | Topological consistency of spatial relationships | No contradictions |

---

## 7. Key Challenges & How God's Eye Addresses Them

| Challenge | How We Handle It |
|---|---|
| **(i) Limited viewing angles** | COLMAP aerial tuning: relaxed `init_min_tri_angle=4°`, increased `init_num_trials=400`, depth enhancement fills gaps |
| **(ii) Motion blur** | Keyframe selection rejects blurry frames via Laplacian variance scoring |
| **(iii) Variable illumination** | SIFT features are invariant to illumination; Depth-Anything is trained on diverse lighting |
| **(iv) Dynamic objects** | Semantic masking (OWLv2) generates per-frame masks → COLMAP ignores masked pixels |
| **(v) GPS inaccuracies** | Currently scale-free (no GCPs). Future: RTK/PPK corrections for metric scale |
| **(vi) Real-time processing** | Cloud GPU parallelism on Modal; near-real-time with staged processing |
| **(vii) Occluded surfaces** | Depth enhancement fills textureless regions; generative completion inserts proxy assets |
| **(viii) Metric accuracy without GCPs** | Monocular depth aligned to COLMAP via least-squares; `scale_is_metric: false` flagged honestly |

---

## 8. Tech Stack Summary

| Layer | Technology | Purpose |
|---|---|---|
| Language | **Python 3.11** | Both local orchestrator and cloud workers |
| Cloud GPU | **Modal** (A10G, T4) | Serverless GPU infrastructure for heavy compute |
| CLI | **Typer + Rich** | Beautiful terminal UI with progress tracking |
| Config | **Pydantic + pydantic-settings** | Strongly typed, env-var overridable configuration |
| Video I/O | **OpenCV** | Frame extraction, blur detection, video probing |
| 3D Reconstruction | **COLMAP** | SfM + dense stereo |
| Point Cloud Processing | **Open3D** | Outlier removal, normals, Poisson mesh, color transfer |
| Depth Estimation | **Depth-Anything-V2** (HuggingFace) | Monocular depth for textureless regions |
| Object Detection | **OWLv2** (HuggingFace) | Zero-shot 2D detection → 3D projection |
| 3D Export | **trimesh + pygltflib** | GLB/glTF scene packaging |
| 3D Viewer | **Three.js** (standalone HTML) | Browser-based GLB viewer with orbit controls |

---

## 9. Two Reconstruction Modes

### Exact Mode (`--mode exact`)
- **Philosophy**: Only geometry directly observed and triangulated from cameras
- Missing/occluded regions are left empty (honest gaps)
- Output: `exact_scene.glb`
- **Use case**: Measurement, surveying, legal documentation

### Generative Mode (`--mode generative`)
- **Philosophy**: Usability over purity — fill gaps for simulation/visualization
- Starts from exact baseline, then inserts proxy 3D assets for detected objects
- All inferred content tagged `provenance: "inferred"` for traceability
- Output: `generative_scene.glb` (separate from exact)
- **Use case**: Digital twins, simulation, mission planning

---

## 10. Potential Applications

| Domain | Application |
|---|---|
| **Defence & Security** | Border mapping, strategic area surveillance, military reconnaissance |
| **Disaster Response** | Rapid damage assessment, search-and-rescue planning |
| **Urban Planning** | Smart city modeling, zoning analysis |
| **Infrastructure** | Bridge/dam/powerline inspection, construction progress monitoring |
| **Archaeology** | Site documentation, cultural heritage preservation |
| **Digital Twins** | Full 3D replicas for simulation, IoT integration |
| **Agriculture** | Crop monitoring, terrain analysis, irrigation planning |

---

## 11. Future Scope & Upcoming Improvements

| Enhancement | Description | Impact |
|---|---|---|
| **RTK/PPK GPS Integration** | Use high-precision GPS corrections for metric-accurate georeferencing | Enables real measurement (distances, volumes) |
| **NeRF/3D Gaussian Splatting** | Replace mesh with neural radiance fields for photorealistic view synthesis | Higher visual quality, especially for vegetation |
| **Real-time SLAM Integration** | Process video frames during flight, not just after landing | True real-time situational awareness |
| **Multi-Video Fusion** | Stitch reconstructions from multiple flights/drones | Larger area coverage, temporal change detection |
| **On-Premise GPU Workers** | Replace Modal cloud with local GPU cluster | Full data sovereignty for classified/sensitive data |
| **Automatic GCP Detection** | Detect survey markers in imagery for auto-calibration | Metric accuracy without manual GCPs |
| **LOD (Level-of-Detail) Generation** | Multiple mesh resolutions for different zoom levels | Smooth streaming for large models |
| **Richer Semantic Ontology** | Fine-grained classes: roof types, road surfaces, damage levels | Better scene understanding for domain-specific use |
| **Temporal Change Detection** | Compare reconstructions over time | Construction monitoring, disaster evolution tracking |
| **Edge Deployment** | Run lightweight pipeline on drone companion computer | In-field processing without internet |

---

## 12. Viva Q&A — Wide-Range Questions and Answers

### Architecture & Design

**Q1: Why did you choose a local+cloud hybrid architecture instead of running everything locally?**
> COLMAP dense stereo and transformer-based models (Depth-Anything, OWLv2) require GPU acceleration. Running locally would need an expensive NVIDIA GPU and complex CUDA setup. Modal provides on-demand A10G GPUs that spin up in seconds and shut down when done — pay-per-use, no idle cost. The local machine handles lightweight orchestration, file management, and the final output packaging.

**Q2: Why is there no database? Isn't that risky?**
> For a pipeline that processes one job at a time, a file-based `manifest.json` is simpler, more auditable (you can read it with any text editor), and eliminates ORM/migration complexity. The manifest tracks every stage's status, timings, and artifact paths atomically. If we scaled to multi-user concurrent jobs, we'd add a database then.

**Q3: Why separate exact and generative outputs instead of one combined model?**
> Measurement and legal use cases demand knowing exactly what was observed vs. inferred. Mixing them would destroy trust. By keeping `exact_scene.glb` and `generative_scene.glb` separate with provenance tags, downstream consumers always know the confidence level of every piece of geometry.

**Q4: Why use Modal instead of AWS/GCP?**
> Modal is purpose-built for Python workloads with GPU. Container definition is inline Python (not Dockerfiles), function invocation is a Python call, and Volume management is simple. For a hackathon/research project, this reduces DevOps overhead to near zero compared to managing EC2 instances or GKE pods.

**Q5: What happens if a stage fails mid-pipeline?**
> The pipeline supports `resume`. Every completed stage is marked `COMPLETED` in the manifest. On resume, the runner skips completed stages and reruns from the failed one. You can also force-rerun a specific stage with `--force-stage`. Logs and intermediate artifacts are preserved even on failure.

---

### 3D Reconstruction

**Q6: What is Structure-from-Motion (SfM) and how does COLMAP implement it?**
> SfM recovers 3D structure and camera motion from a set of 2D images. COLMAP implements incremental SfM:
> 1. Extract SIFT features (keypoints + descriptors) per image
> 2. Match features across image pairs (exhaustive or sequential)
> 3. Initialize with a two-view reconstruction (epipolar geometry)
> 4. Incrementally register new images via PnP (Perspective-n-Point)
> 5. Triangulate new 3D points from newly matched features
> 6. Run bundle adjustment to jointly optimize all cameras + points
> The result is a sparse 3D point cloud + camera poses.

**Q7: Why does single-pass drone footage make reconstruction harder?**
> Traditional photogrammetry uses multiple overlapping passes to ensure every surface is seen from many angles. A single pass means limited viewing angles — surfaces are often seen from only 2-3 views. This causes:
> - Fewer triangulation baselines → lower accuracy
> - More occlusions (backsides of buildings are never seen)
> - Small baselines between consecutive frames → poor depth resolution
> Our mitigations: relaxed COLMAP initialization angles, monocular depth enhancement, and intelligent keyframe selection for maximum diversity.

**Q8: What is Poisson Surface Reconstruction and why do you use it?**
> Poisson reconstruction fits a smooth implicit function (indicator function) through the oriented point cloud such that the gradient of this function aligns with the normals. It produces a watertight, smooth mesh even from noisy/sparse point clouds. We use it because:
> - It handles noise well (unlike ball-pivoting or alpha shapes)
> - It fills small gaps between observed points
> - It produces manifold meshes suitable for rendering and measurement
> The downside: it can hallucinate surfaces in poorly observed regions, which is why we apply density-quantile trimming.

**Q9: What is the "registration quality gate" and why is it important?**
> If COLMAP can only register 10% of keyframes, the resulting point cloud is unreliable — but it still produces an output file. Without the gate, you'd get a deceptive "success" with garbage geometry. Our gate requires:
> - At least 5 registered images
> - At least 50% registration ratio
> If either fails, the pipeline reports a structured failure with advice ("footage may lack parallax or be too blurry").

**Q10: Why do you use kNN for normal estimation instead of radius search?**
> SfM output has **arbitrary scale** (no metric reference). A fixed search radius of, say, 0.1m is meaningless when the scene units could be anything from 0.001 to 1000. kNN (k-nearest neighbors) is scale-invariant — it always considers the k closest points regardless of the absolute coordinate scale.

---

### AI/ML Models

**Q11: How does the monocular depth alignment work mathematically?**
> Monocular depth models output *relative* depth (closer vs. farther), not metric depth. We align it using known COLMAP 3D points:
> 1. For each keyframe with a known camera pose, project all COLMAP 3D points into the camera frame: `P_cam = R × P_world + T`
> 2. Keep only points in front of the camera (`z > 0.5`)
> 3. Project to pixel coordinates: `u = fx × x/z + cx`, `v = fy × y/z + cy`
> 4. Sample the monocular depth at those pixel locations
> 5. Solve the linear system: `z_colmap = scale × z_mono + shift` via least-squares (`np.linalg.lstsq`)
> 6. Apply `aligned_depth = scale × raw_depth + shift` to the entire depth map
> This anchors every depth pixel to the COLMAP metric coordinate system.

**Q12: Why did you choose OWLv2 over YOLO or Faster R-CNN for object detection?**
> OWLv2 is a **zero-shot** detector — you give it text labels ("vehicle", "building", "tree") and it detects them without any task-specific training. YOLO/Faster R-CNN require training on labeled aerial datasets. For a flexible system that should work on any scene with any object vocabulary, zero-shot is far more practical. The trade-off is slightly lower accuracy vs. a fine-tuned model, but the generality is worth it.

**Q13: How do you convert 2D bounding boxes into 3D world coordinates?**
> For each 2D detection:
> 1. Get the camera pose (R, T) and intrinsics (fx, fy, cx, cy) from COLMAP
> 2. Estimate depth by projecting COLMAP 3D points into the camera and finding the median depth of points inside the bounding box
> 3. Unproject the box center: `X_cam = [(u-cx)×z/fx, (v-cy)×z/fy, z]`
> 4. Transform to world: `X_world = R^T × (X_cam - T)`
> 5. Estimate 3D dimensions: `dim = box_pixels × depth / focal_length`

**Q14: What is the purpose of semantic masking before reconstruction?**
> Moving objects (cars, pedestrians) that appear in different positions across frames create "ghost" artifacts in SfM — COLMAP tries to triangulate them as static 3D points, producing noisy phantom geometry. By detecting dynamic objects with OWLv2 and masking them (black = ignore pixel), COLMAP only reconstructs the static background scene.

---

### Data Pipeline & Processing

**Q15: Why do you extract at 6 fps instead of using every frame?**
> A 30fps 4K video produces 18,000 frames in 10 minutes. This is:
> - Too many for COLMAP's exhaustive matcher (O(n²) complexity)
> - Mostly redundant (consecutive frames at 30fps are nearly identical)
> - Wasteful of GPU time
> 6 fps provides sufficient overlap for SfM while keeping the candidate count tractable (~3,600 frames). Keyframe selection further reduces this to ~200.

**Q16: How does the keyframe selection algorithm work?**
> Three-pass scoring:
> 1. **Sharpness filter**: Compute Laplacian variance per frame. Reject frames below `0.5 × median_sharpness` (adaptive, not fixed percentile)
> 2. **Novelty filter**: Compute 32×32 grayscale image "signatures". Reject frames with signature delta < 0.012 from the previous selected frame (removes near-duplicates)
> 3. **Uniform subsampling**: From surviving frames, evenly subsample to target count (200) to ensure temporal/spatial coverage
> 4. **Relaxation**: If too few frames survive, thresholds are loosened in 4 steps to avoid starving COLMAP

**Q17: What is the manifest.json and what does it track?**
> It's the **state machine** of a pipeline run. It records:
> - Job ID, input video path, pipeline mode
> - Status of every stage (PENDING → RUNNING → COMPLETED/FAILED/SKIPPED)
> - Artifact paths and SHA-256 hashes
> - Timing per stage
> - Configuration snapshot (for reproducibility)
> - Error details with origin tracking (LOCAL vs MODAL)
> It's written atomically (write to temp file, then rename) to prevent corruption.

**Q18: How does the pipeline handle the local-to-cloud data boundary?**
> The `ModalTransport` class manages this:
> 1. **Upload**: Keyframe images are uploaded to a Modal Volume (`godseye-jobs`) with concurrent workers (8 parallel uploads)
> 2. **Cloud processing**: Workers read from and write to the Volume directly
> 3. **Download**: After processing, the output packaging stage downloads results from the Volume to local `outputs/`
> Between cloud stages (e.g., reconstruction → geometry), data stays on the Volume — no unnecessary round-trips.

---

### Output & Visualization

**Q19: What is contained in scene.json?**
> The top-level scene descriptor:
> ```json
> {
>   "schema_version": 1,
>   "job_id": "20260915-143000-abc123",
>   "mode": "exact",
>   "units": "unknown",
>   "scale_is_metric": false,
>   "scale_note": "Scale is arbitrary. COLMAP SfM is scale-free...",
>   "coordinate_system": "colmap_world (y-down, right-handed)",
>   "geometry": { "sparse_point_count": 45000, "mesh_triangle_count": 1000000, ... },
>   "exports": { "scene": "exact_scene.glb", "pointcloud": "pointcloud.ply" },
>   "documents": { "objects": "objects.json", "scene_graph": "scene_graph.json" }
> }
> ```

**Q20: How does the 3D viewer work?**
> A standalone HTML file using **Three.js**. User drags and drops a `.glb` file → it's loaded into a WebGL scene with orbit controls, lighting, and a grid. The viewer also displays scene graph data as an overlay panel. No server needed — runs entirely in the browser.

---

### Challenges & Limitations

**Q21: What is the biggest limitation of single-pass reconstruction?**
> **Occlusion**. Surfaces facing away from the flight path (backs of buildings, ground under dense canopy) are never observed. No amount of AI can faithfully reconstruct what was never seen. Generative mode mitigates this with proxy assets, but marks them explicitly as "inferred" — never as ground truth.

**Q22: How do you handle scale ambiguity?**
> Pure SfM from a single camera is **inherently scale-free** — the reconstruction could be 1cm or 1km and be equally valid mathematically. Without GCPs or RTK GPS, we honestly flag `scale_is_metric: false` in scene.json. The depth alignment provides relative consistency (all depths are proportionally correct), but absolute metric scale requires an external reference.

**Q23: What happens with very long or very short videos?**
> - **Long videos (>30 min)**: `max_candidates=3000` caps frame extraction. Keyframe selection still targets ~200 frames.
> - **Short videos (<1 min)**: May produce too few keyframes for reliable SfM. The registration gate catches this and reports failure.
> - **Sweet spot**: 5-15 minutes of oblique aerial footage with lateral sweeping motion.

**Q24: How do you ensure data sovereignty for sensitive/military applications?**
> Currently, keyframes temporarily reside on Modal's cloud during processing. For classified data:
> - The architecture is designed for **on-premise GPU worker swap** (Phase 12 roadmap)
> - All stage interfaces are abstract (`ExecutionTarget.MODAL` vs `LOCAL`) — switching is a config change, not a code rewrite
> - Source video and final outputs always remain on the local machine

**Q25: What types of drone footage work best? What fails?**
> **Works best**: Oblique sweeping flight paths (45° camera angle, lateral motion), good lighting, textured surfaces (buildings, roads, vegetation)
> **Fails**: Nadir-only straight-line flights (pure forward motion, no parallax), nighttime, featureless terrain (snow, sand, water), heavy rain/fog, gimbal-only rotation (no translational motion)

---

### Advanced / Research Questions

**Q26: How would you add NeRF or 3D Gaussian Splatting to this pipeline?**
> After COLMAP produces camera poses, feed them into a NeRF trainer (e.g., Nerfacto from Nerfstudio) or 3D Gaussian Splatting. The camera poses from COLMAP are already in the correct format. The output would be a radiance field instead of a mesh — better for novel view synthesis but harder to measure/edit. It would be an additional export format, not a replacement for the mesh.

**Q27: How does this compare to commercial photogrammetry software (Pix4D, Agisoft Metashape)?**
> | Aspect | God's Eye | Commercial |
> |---|---|---|
> | Input | Single-pass video only | Multi-pass planned flights |
> | AI Integration | Depth-Anything, OWLv2, semantic graph | Limited AI |
> | Open Source | Yes | No |
> | Scene Understanding | Semantic objects + scene graph | Point cloud / mesh only |
> | Real-time potential | Cloud GPU pipeline | Desktop batch processing |
> | Accuracy | Lower (single pass) | Higher (planned overlap) |

**Q28: What would real-time processing look like?**
> Replace batch COLMAP with incremental SLAM (e.g., ORB-SLAM3 or DROID-SLAM) running on the drone's companion computer. Stream keyframes to the cloud for depth enhancement and semantic detection. Display a growing 3D model in real-time on the operator's tablet. This requires ~10× optimization of the current pipeline.

**Q29: How would you validate reconstruction accuracy?**
> 1. Fly over a surveyed area with known GCPs (ground control points)
> 2. Reconstruct with God's Eye
> 3. Measure Chamfer distance between reconstruction and LiDAR ground truth
> 4. Measure reprojection error (reproject 3D points back to images, measure pixel deviation)
> 5. Compare detected objects against manual ground truth annotations

**Q30: What are the ethical considerations?**
> - **Surveillance**: System could be misused for unauthorized monitoring. Mitigation: access controls, audit logs.
> - **Military use**: Autonomous target identification raises ethical concerns. Mitigation: human-in-the-loop requirement.
> - **Privacy**: Aerial footage captures private property/people. Mitigation: semantic masking can detect and blur personal data.
> - **Accuracy liability**: Measurements from non-metric reconstructions could be misused. Mitigation: explicit `scale_is_metric: false` warnings.

---

## 13. Quick Reference Card (Print & Carry to Viva)

```
PROJECT:     God's Eye — Single-Pass Drone Video → 3D World Model
COMMAND:     python run_pipeline.py --video ./drone.mp4 --mode exact
STAGES:      10 (Job Setup → Frame Extract → Keyframe Select → Masking →
             COLMAP Recon → Geometry → Depth → Semantics → Scene Graph →
             Generative → Output Package)
AI MODELS:   COLMAP (SfM), Depth-Anything-V2 (depth), OWLv2 (detection)
LIBRARIES:   Open3D, trimesh, OpenCV, HuggingFace Transformers
INFRA:       Local Python + Modal Cloud GPUs (A10G)
OUTPUTS:     exact_scene.glb, pointcloud.ply, mesh.obj, objects.json,
             scene_graph.json, confidence.json, run_summary.json
KEY INNOVATION: Monocular depth aligned to COLMAP via least-squares for
             textureless region densification
```
