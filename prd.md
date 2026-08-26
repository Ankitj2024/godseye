# Product Requirements Document: God's Eye

## Document Status

- Product: `God's Eye`
- Type: Hackathon PRD
- Date: August 26, 2026
- Status: Revised for backend-only implementation

---

## 1. Product Vision

`God's Eye` is a backend-only drone-video-to-3D-scene pipeline. The user places a drone video in the project root, runs a Python entry script with the video path, and receives 3D scene outputs back in the root output area.

The product promise is now:

> Give God's Eye one drone video path. Get back a usable 3D world model.

This version intentionally removes the frontend for now so all effort goes into the reconstruction and intelligence pipeline.

---

## 2. Product Positioning

`God's Eye` is a spatial AI and reconstruction pipeline that converts drone footage into:

- faithful 3D reconstruction
- AI-assisted scene completion
- semantic 3D object understanding
- structured scene metadata
- exportable 3D outputs

This hackathon version is backend-first. It proves the core pipeline before any UI work.

---

## 3. Core User Flow

1. Put a drone video in the working/root folder.
2. Run a Python script with the video path and selected mode.
3. Local Python orchestration prepares and tracks the job.
4. Compute-heavy stages run on Modal.
5. Final outputs are written back to the root output folder.

Example target usage:

```bash
python run_pipeline.py --video ./drone.mp4 --mode exact
python run_pipeline.py --video ./drone.mp4 --mode generative
```

---

## 4. Goals

### Primary goals

- Accept one local drone video path as input.
- Run the full pipeline from Python.
- Offload compute-heavy work to Modal.
- Support both:
  - `Exact Reconstruction`
  - `Generative Reconstruction`
- Return final outputs to the root folder.
- Keep all major features from the original concept except the frontend.

### Secondary goals

- Keep the pipeline modular enough for later UI integration.
- Keep local orchestration simple and reproducible.
- Preserve a future path from Modal to on-prem GPU workers.

---

## 5. Scope

## P0

- Python CLI/script entrypoint
- local file path input
- local job folder creation
- Modal-heavy processing pipeline
- intelligent frame selection from approximately 10-minute drone video
- exact reconstruction using `COLMAP` and `Open3D`
- generative reconstruction mode
- AI depth enhancement
- semantic 3D object detection
- 3D cuboid/object metadata output
- scene graph generation
- quality/confidence map generation
- at least one exportable scene output such as `GLB`
- final outputs copied into root output location

## P1

- metric scaling where possible
- multiple output formats
- multiple LODs
- richer scene graph relationships
- asset provenance metadata
- more detailed confidence reporting

## P2

- full on-prem worker replacement for Modal
- multi-video fusion
- richer semantic ontology
- automated benchmarking

---

## 6. Non-Goals

- no frontend
- no React app
- no FastAPI service
- no upload UI
- no live progress dashboard
- no multi-user workflow
- no enterprise auth

For now, the system is a local Python pipeline plus Modal workers.

---

## 7. Functional Requirements

## 7.1 Input

- The system accepts a local drone video path.
- The input video is expected to be around 10 minutes, though shorter clips are allowed.
- The root-level script is the entrypoint.

## 7.2 Modes

### Exact Reconstruction

- prioritize observed geometry
- avoid hallucinated fill where evidence is weak
- preserve sparse or incomplete regions honestly

### Generative Reconstruction

- begin from the exact reconstruction baseline
- fill ambiguous or blurry regions using semantic priors and a prebuilt 3D asset library
- mark inferred content explicitly in metadata

## 7.3 Intelligent Frame Selection

- sample candidate frames from the source video
- rank frames using blur, coverage, spacing, and novelty
- remove duplicates and low-value frames
- produce a curated keyframe set

## 7.4 Classical Reconstruction

- use `COLMAP` for camera pose estimation and structure-from-motion
- use `Open3D` for point cloud and mesh processing
- produce:
  - camera poses
  - sparse point cloud
  - dense point cloud and/or mesh

## 7.5 AI Depth Enhancement

- estimate depth on selected frames
- use depth to improve weak geometry regions
- record when geometry is depth-assisted

## 7.6 Generative Scene Completion

- detect ambiguous regions or weak objects
- use object class predictions and a prebuilt 3D asset library
- place plausible proxy assets into the scene
- preserve provenance and confidence metadata

## 7.7 Semantic 3D Object Detection

- detect object classes in the scene
- estimate 3D cuboid or object proxy metadata
- output:
  - object ID
  - class
  - transform
  - dimensions
  - confidence
  - provenance

## 7.8 Scene Graph

- build node and relationship metadata
- include class, transform, confidence, and provenance

## 7.9 Confidence Map

- produce confidence metadata for observed, assisted, and inferred regions
- distinguish at least:
  - high-confidence observed
  - medium-confidence enhanced
  - low-confidence inferred

## 7.10 Metric Scaling

- estimate metric scale when possible from metadata or priors
- if not possible, clearly mark scale as approximate

## 7.11 Outputs

### Minimum outputs

- `GLB` or `glTF`
- `scene.json`
- object metadata JSON
- scene graph JSON
- confidence metadata JSON
- logs/manifest for the job

### Optional outputs

- `PLY`
- `OBJ`
- preview images
- multiple LOD outputs

---

## 8. Technical Direction

## 8.1 Local Python Responsibilities

- validate inputs
- create job folders
- manage local artifacts
- dispatch Modal tasks
- collect outputs
- package final results
- write outputs to the root folder

## 8.2 Modal Responsibilities

All compute-heavy stages should move to Modal where practical, including:

- frame analysis if expensive
- depth estimation
- semantic detection
- generative completion
- dense processing and any GPU-heavy model inference

If some classical reconstruction stages remain CPU-bound locally at first, they should still be isolated behind clear pipeline functions so they can move later.

## 8.3 Deployment Reality

This is still not fully sovereign because Modal means data leaves the local machine during processing. The future production path remains an on-prem GPU worker.

---

## 9. Storage Model

Suggested local layout:

```text
godseye/
├── run_pipeline.py
├── input_video.mp4
├── outputs/
│   └── <job_id>/
├── work/
│   └── <job_id>/
└── assets/
```

Suggested per-job working layout:

```text
work/<job_id>/
├── input/
├── frames/
├── reconstruction/
├── depth/
├── semantics/
├── completion/
├── exports/
└── manifest.json
```

Final deliverables should be copied into:

```text
outputs/<job_id>/
```

---

## 10. Success Metrics

- one command starts the full pipeline
- one local video path can produce outputs end-to-end
- exact mode works on at least one strong demo video
- generative mode works on at least one strong demo video
- output artifacts are organized and reusable

---

## 11. Risks

- Modal integration may introduce packaging and dependency complexity
- `COLMAP` may be harder to containerize than model inference stages
- long videos may produce too many frames and drive costs up
- generative asset insertion may look fake if not constrained carefully
- without a frontend, debugging relies more heavily on logs and artifacts

---

## 12. Final Recommendation

The product should now be treated as a backend pipeline product, not a web app.

The build priority is:

1. make the single-command pipeline work
2. make exact reconstruction reliable
3. add semantic and confidence outputs
4. add generative completion
5. package clean outputs back to the root folder

That keeps the project aligned with the real value: the reconstruction and intelligence pipeline itself.
