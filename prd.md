# Product Requirements Document: God's Eye

## Document Status

- Product: `God's Eye`
- Type: Hackathon PRD
- Date: August 24, 2026
- Status: Draft for implementation
- Primary goal: Build a plug-and-play system that turns a single long drone video into an explorable, semantically understood 3D scene with both faithful reconstruction and AI-assisted completion.

---

## 1. Product Vision

`God's Eye` is an AI-assisted 3D scene reconstruction tool for drone footage. A user uploads one large drone video, waits through a progressive processing pipeline, and receives a navigable 3D scene with object-level understanding, confidence signals, and exportable assets.

The core product promise is:

> Upload one drone video. Get back a usable 3D world model.

For the hackathon, the product should feel:

- Plug-and-play
- Visually impressive
- Easy to demo live
- Technically credible
- Honest about current tradeoffs

The long-term ambition is an on-premise, infrastructure-sovereign spatial intelligence system for mapping, inspection, surveying, defense, disaster response, and site understanding. The hackathon version proves the workflow and the user experience, not full production-grade reconstruction accuracy across every environment.

---

## 2. Positioning

### Problem

Drone operators, analysts, and field teams often have raw aerial video but not a fast way to convert it into a semantically meaningful 3D scene that can be explored, queried, and exported.

Current workflows are usually fragmented:

- Video capture happens in one tool
- Photogrammetry happens in another
- Semantic labeling is manual or absent
- 3D scene understanding is not packaged into a simple UX

### Product Positioning

`God's Eye` sits at the intersection of:

- Drone video processing
- Photogrammetry / 3D reconstruction
- AI-based scene understanding
- Human-friendly visualization

### One-line positioning

`God's Eye` converts long drone footage into an interactive 3D scene with reconstruction, semantic labeling, and AI completion from a single upload.

---

## 3. Product Goals

### Primary goals

- Make the product demoable from one input file and one primary flow.
- Generate a 3D scene from a roughly 10-minute drone video.
- Support two reconstruction modes:
  - `Exact Reconstruction`
  - `Generative Reconstruction`
- Present progress clearly while work happens asynchronously.
- Produce output that is visually compelling enough for a hackathon demo.
- Preserve a clean path from today's architecture to an eventual on-prem production architecture.

### Secondary goals

- Add semantic 3D understanding with toggleable object boxes and class filters.
- Surface confidence and uncertainty instead of pretending ambiguous geometry is exact.
- Export useful assets for downstream use.

---

## 4. Users and Use Cases

### Target users

- Hackathon judges and technical evaluators
- Internal demo users
- Drone operators
- Analysts working with aerial site footage
- Future enterprise buyers needing local or sovereign deployments

### Core use cases

- Upload a single drone video of a site and explore a generated 3D scene.
- Inspect detected semantic objects such as buildings, vehicles, trees, roads, containers, towers, or infrastructure elements.
- Compare faithful reconstruction vs AI-completed reconstruction.
- Export scene assets for downstream visualization or analysis.
- Identify uncertain or hallucinated regions through a quality/confidence overlay.

---

## 5. Product Principles

- `Single giant upload`: the user should not need to manually split or preprocess footage.
- `Progressive disclosure`: the UI should reveal pipeline progress and partial artifacts over time.
- `Two truths`: exact reconstruction and generative completion must remain distinct so users know what is measured vs inferred.
- `Semantic first`: the output should not be just a mesh; it should be an understandable scene.
- `Honest confidence`: ambiguous regions should be visually marked, not hidden.
- `Local-first UX`: the app runs on localhost and stores files locally by default.
- `Production path`: the architecture should be able to replace the current remote GPU backend with an on-prem GPU worker later.

---

## 6. Scope Overview

### P0: Must have for the hackathon MVP

- Local localhost app
- React + TypeScript frontend
- Python + FastAPI backend
- Local filesystem storage
- Single large drone video upload flow
- Asynchronous job creation and progress tracking
- Intelligent frame selection from approximately 10-minute drone video
- Classical reconstruction pipeline using `COLMAP` and `Open3D`
- Two user-selectable modes:
  - `Exact Reconstruction`
  - `Generative Reconstruction`
- AI depth enhancement step to improve weak geometry where possible
- Generative scene completion for ambiguous or blurry objects
- Prebuilt 3D asset library insertion for selected object classes
- Basic semantic 3D object detection
- Toggleable 3D cuboid boxes in the viewer
- Class filtering in the viewer
- Scene graph artifact
- Quality / confidence map overlay
- Export at least one usable scene format such as `glTF/GLB`
- Honest architecture note that Modal means data leaves the local machine

### P1: Strong stretch goals

- Metric scaling where possible
- Multiple LOD outputs
- Additional export formats such as `PLY`, `OBJ`, `scene.json`
- Richer scene graph relationships
- Side-by-side comparison between exact and generative outputs
- Thumbnail previews and partial artifacts during processing
- Region-level confidence drill-down
- Better semantic taxonomy

### P2: Nice-to-have / future work

- Multi-video fusion
- Live map alignment / georegistration
- Collaborative annotations
- Query interface over the scene graph
- On-prem GPU worker replacement for Modal
- Enterprise auth and audit controls
- Training or fine-tuning specialized detection models

---

## 7. Non-Goals

The hackathon MVP will not aim to provide:

- Fully sovereign or air-gapped deployment
- Survey-grade accuracy guarantees
- Real-time reconstruction while the drone is flying
- Full SLAM stack for every environment
- Manual scene editing workflows
- Multi-user collaboration
- Production-grade access control
- Support for all drone camera types and metadata edge cases
- Perfect geometry in textureless, occluded, or motion-blurred areas

---

## 8. User Experience

## 8.1 Primary UX Flow

1. User opens local web app on localhost.
2. User uploads one large drone video.
3. User chooses mode:
   - `Exact Reconstruction`
   - `Generative Reconstruction`
4. User starts processing.
5. UI shows progressive pipeline stages and status.
6. When available, the UI reveals intermediate outputs:
   - frame extraction status
   - selected keyframes preview
   - sparse point cloud preview
   - dense reconstruction / mesh progress
   - detected semantic classes
   - scene completion progress
7. User opens final 3D scene viewer.
8. User toggles:
   - semantic cuboid boxes
   - class filters
   - confidence overlay
   - exact vs generative mode results
9. User exports outputs.

## 8.2 UX Requirements

- The upload experience should feel simple and non-technical.
- The app should communicate that large videos can take time.
- Progress should be broken into meaningful stages instead of showing only one loading bar.
- The generative completion output must be clearly labeled as inferred content.
- Low-confidence regions must be discoverable visually.

## 8.3 Progressive UI Stages

Suggested stages:

1. `Video ingest`
2. `Frame analysis`
3. `Keyframe selection`
4. `Camera pose reconstruction`
5. `Dense geometry generation`
6. `Depth enhancement`
7. `Semantic object detection`
8. `Scene graph construction`
9. `Generative completion` (mode-dependent)
10. `Packaging outputs`

---

## 9. Functional Requirements

## 9.1 Input Handling

- Accept a single drone video upload, expected around 10 minutes.
- Support large file handling without freezing the UI.
- Save uploads to the local filesystem.
- Create a job record on upload.
- Associate all derived artifacts to a stable job ID.

### Assumptions

- Preferred input: MP4 or MOV
- Drone footage is primarily aerial and forward/downward looking
- Footage quality may vary in sharpness, altitude, and overlap

## 9.2 Intelligent Frame Selection

The system should automatically select a useful subset of frames from the long video for downstream reconstruction.

### Requirements

- Downsample the video into candidate frames.
- Score frames based on signals such as:
  - blur / sharpness
  - overlap / novelty
  - camera motion spacing
  - texture richness
  - exposure quality
- Avoid near-duplicate frames.
- Preserve enough coverage for reconstruction.
- Produce a reviewable keyframe set artifact.

### Desired outcome

The user uploads one long video, but the reconstruction stack only receives a curated subset that balances quality, diversity, and compute cost.

## 9.3 Reconstruction Modes

### Exact Reconstruction Mode

Purpose:

- Produce the most faithful geometry possible from available evidence.

Requirements:

- Use classical reconstruction methods as the primary geometry source.
- Prioritize observed structure over inferred fill.
- Allow empty, incomplete, or sparse regions if evidence is insufficient.
- Surface confidence so the user knows what is weak.

Expected pipeline:

- keyframe extraction
- feature matching
- `COLMAP` sparse reconstruction
- dense reconstruction / point cloud
- surface generation / cleanup in `Open3D`
- texture or color assignment where feasible

### Generative Reconstruction Mode

Purpose:

- Produce a more visually complete and semantically legible scene by filling uncertain, blurry, or occluded regions.

Requirements:

- Start from the exact reconstruction output wherever possible.
- Detect semantic object classes.
- For ambiguous or blurry objects, use a prebuilt 3D asset library to place plausible geometry.
- Use generative completion only where the exact pipeline is incomplete or low confidence.
- Mark inferred areas distinctly in metadata and optionally in UI.

Expected behavior:

- Buildings may have completed roofs or walls if partially reconstructed.
- Vehicles, trees, poles, or containers may be represented by class-matched proxy assets when raw geometry is weak.
- The scene should remain grounded in observed camera poses and spatial layout as much as possible.

## 9.4 Classical Reconstruction

- Use `COLMAP` for structure-from-motion and camera pose estimation.
- Use `Open3D` for point cloud processing, meshing, cleanup, and spatial utilities.
- Produce at minimum:
  - camera poses
  - sparse point cloud
  - dense point cloud or mesh

## 9.5 AI Depth Enhancement

Purpose:

- Improve reconstruction quality in areas where classical geometry is thin but still visually recoverable.

Requirements:

- Run a monocular or learned depth estimation stage on selected frames.
- Fuse or use estimated depth to enhance geometry quality where feasible.
- Avoid claiming survey-grade precision.
- Record that geometry has been depth-assisted when applicable.

## 9.6 Generative Scene Completion

Purpose:

- Fill in ambiguous scene regions using semantics and prior 3D assets.

Requirements:

- Detect candidate semantic classes from frames and/or 3D features.
- Maintain a prebuilt class-to-asset library.
- Insert approximate assets for objects that are:
  - blurry
  - partially observed
  - hard to reconstruct photogrammetrically
- Preserve transform metadata:
  - position
  - scale
  - orientation
  - asset source
  - confidence

Example object classes:

- building
- house
- road
- vehicle
- truck
- tree
- pole
- tower
- container
- fence

## 9.7 Semantic 3D Object Detection

Requirements:

- Detect semantic objects in the scene.
- Represent detections as 3D cuboid boxes or equivalent proxies.
- Expose object class labels and confidence.
- Support toggling boxes on/off in the viewer.
- Support filtering by class in the viewer.

Minimum object metadata:

- object ID
- class label
- confidence score
- position
- size / dimensions
- orientation
- source mode:
  - exact
  - inferred

## 9.8 Scene Graph

The system should build a scene graph describing objects and their relationships.

### Minimum scene graph contents

- nodes for detected or reconstructed entities
- node type or class
- transforms
- confidence
- provenance
- relationships where feasible, such as:
  - `on`
  - `adjacent_to`
  - `inside`
  - `part_of`
  - `connected_to`
  - `near`

### Purpose

- Support explainability
- Make future querying possible
- Structure the scene beyond a raw mesh

## 9.9 Quality / Confidence Map

The product must visualize or expose uncertainty.

Requirements:

- Produce a confidence artifact for geometry quality and/or semantic confidence.
- Support viewer overlay or region highlighting.
- Distinguish at least three categories:
  - high confidence observed
  - medium confidence assisted
  - low confidence inferred / ambiguous

## 9.10 Metric Scaling

The system should estimate metric scale where possible.

Possible sources:

- drone metadata
- altitude / camera parameters
- known object priors
- ground plane assumptions

Requirements:

- If metric scale can be estimated credibly, apply it.
- If not, clearly mark output as approximate scale.

## 9.11 Output Formats and LODs

### P0 outputs

- `GLB` or `glTF` scene for viewing
- `scene.json` metadata
- point cloud or mesh artifact
- object detection metadata
- confidence metadata

### P1 outputs

- `PLY`
- `OBJ`
- multiple levels of detail
- preview images
- packaged export bundle per job

### Scene metadata should include

- job ID
- mode
- timestamps
- pipeline version
- file references
- object list
- scene graph
- confidence summaries
- scale status

---

## 10. Technical Architecture

## 10.1 Current Hackathon Architecture

- Frontend: `React` + `TypeScript`
- Backend API: `Python` + `FastAPI`
- Local storage: filesystem directories on the host machine
- Compute backend: `Modal` serverless GPU for heavy AI / reconstruction stages
- Viewer: web-based 3D scene viewer in the frontend

### Important deployment note

The application is locally hosted and stores files locally, but it is **not fully sovereign today** because the current compute backend uses `Modal`. That means uploaded video frames and derived data may leave the local machine during processing.

This must be stated clearly in the PRD, the demo, and any architecture explanation.

## 10.2 Production Direction

Target future production architecture:

- same local-first UX
- same React/FastAPI app boundary
- same local or customer-controlled storage
- replace `Modal` with an on-prem GPU worker or customer VPC worker

This future state would support a truly sovereign deployment story.

## 10.3 High-Level Component Diagram

```text
User
  |
  v
React + TypeScript Frontend (localhost)
  |
  v
FastAPI Backend (localhost)
  |
  +--> Local Filesystem Storage
  |      - uploads/
  |      - frames/
  |      - jobs/
  |      - outputs/
  |      - assets/
  |
  +--> Job Queue / Orchestrator
  |
  +--> Modal GPU Worker (current)
         - frame analysis
         - depth estimation
         - semantic detection
         - optional generative completion
         - heavy processing
```

---

## 11. Data Flow

## 11.1 End-to-End Flow

1. User uploads drone video through frontend.
2. Backend stores file locally and creates job metadata.
3. Backend extracts lightweight video metadata.
4. Backend generates candidate frames.
5. Frame selection module picks useful keyframes.
6. Reconstruction pipeline runs classical SfM and geometry creation.
7. Depth enhancement stage refines or supplements geometry.
8. Semantic detection produces object candidates and classes.
9. Scene graph builder structures objects and relationships.
10. If `Generative Reconstruction` mode is selected, ambiguous regions are completed using assets and/or generative priors.
11. Outputs are written locally.
12. Frontend polls or subscribes for progress and renders final artifacts.

## 11.2 Job Artifact Flow

Suggested artifact chain:

- uploaded video
- extracted candidate frames
- selected keyframes
- camera pose data
- sparse point cloud
- dense point cloud / mesh
- depth estimates
- semantic object detections
- scene graph
- exact scene package
- generative scene package
- previews and exports

---

## 12. Storage Design

## 12.1 Storage Decision

For the hackathon MVP, local filesystem storage is preferred over object storage because:

- the app runs on localhost
- the desired product direction is on-prem
- it reduces infrastructure complexity
- it improves developer velocity for the hackathon

## 12.2 Storage Layout

Suggested structure:

```text
godseye/
├── frontend/
├── backend/
├── modal/
├── data/
│   ├── uploads/
│   ├── frames/
│   ├── processing/
│   ├── jobs/
│   ├── outputs/
│   └── assets/
└── shared/
```

Suggested per-job structure:

```text
data/jobs/<job_id>/
├── input/
│   └── video.mp4
├── frames/
├── reconstruction/
├── semantics/
├── completion/
├── previews/
├── exports/
└── job.json
```

---

## 13. Job and Progress Architecture

## 13.1 Job Model

Each upload should create a durable local job record containing:

- job ID
- input file info
- mode
- creation time
- current stage
- progress percentage
- stage logs
- artifact paths
- error state
- result summary

## 13.2 Execution Model

Recommended model:

- FastAPI receives request
- creates job record
- enqueues background orchestration
- orchestration dispatches heavy tasks to workers
- frontend polls or streams progress updates

## 13.3 Progress Model

Progress should be stage-based, not only percentage-based.

Each stage should include:

- stage name
- status:
  - pending
  - running
  - completed
  - failed
- human-readable description
- optional preview artifact

## 13.4 Failure Handling

- If one stage fails, the job should surface a clear error message.
- Partial artifacts should remain inspectable for debugging.
- Exact mode may still succeed even if generative completion fails.

---

## 14. API Outline

This is an implementation-oriented outline, not a locked contract.

## 14.1 Core Endpoints

### `POST /api/jobs`

Create a job from an uploaded drone video.

Inputs:

- multipart file upload
- reconstruction mode
- optional config overrides

Returns:

- job ID
- initial status

### `GET /api/jobs/{job_id}`

Return job summary, stage states, and artifact references.

### `GET /api/jobs/{job_id}/progress`

Return detailed pipeline progress.

### `GET /api/jobs/{job_id}/artifacts`

Return artifact manifest for the job.

### `GET /api/jobs/{job_id}/scene`

Return the main scene package metadata for viewer loading.

### `GET /api/jobs/{job_id}/detections`

Return semantic object detection data and filterable classes.

### `GET /api/jobs/{job_id}/scene-graph`

Return scene graph JSON.

### `GET /api/jobs/{job_id}/confidence`

Return quality/confidence map data.

### `GET /api/jobs/{job_id}/download`

Return packaged export bundle.

### `DELETE /api/jobs/{job_id}`

Optional cleanup endpoint for local artifact removal.

## 14.2 Possible Internal Worker Interfaces

- `analyze_video(job_id)`
- `select_keyframes(job_id)`
- `run_colmap(job_id)`
- `run_open3d_postprocess(job_id)`
- `run_depth_enhancement(job_id)`
- `run_semantic_detection(job_id)`
- `run_scene_graph_builder(job_id)`
- `run_generative_completion(job_id)`
- `package_outputs(job_id)`

---

## 15. Repository Structure

Recommended repo structure:

```text
godseye/
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── features/
│   │   │   ├── upload/
│   │   │   ├── jobs/
│   │   │   ├── viewer/
│   │   │   └── semantics/
│   │   ├── lib/
│   │   └── types/
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   ├── services/
│   │   ├── workers/
│   │   ├── pipelines/
│   │   └── utils/
│   ├── tests/
│   └── pyproject.toml
├── modal/
│   ├── workers/
│   ├── images/
│   └── entrypoints/
├── shared/
│   ├── schemas/
│   └── config/
├── data/
│   └── .gitkeep
├── docs/
│   └── PRD.md
└── README.md
```

---

## 16. Implementation Approach

## 16.1 Suggested Pipeline Composition

### P0 processing path

1. ingest upload
2. extract candidate frames
3. score and select keyframes
4. reconstruct camera poses with `COLMAP`
5. generate sparse/dense geometry
6. post-process with `Open3D`
7. run depth enhancement
8. run semantic object detection
9. build scene graph
10. optionally run generative completion
11. package scene and metadata

## 16.2 Exact vs Generative Mode Strategy

Recommended implementation:

- Always compute the classical pipeline first.
- Treat `Exact Reconstruction` as the faithful baseline output.
- Layer `Generative Reconstruction` on top of exact output rather than building a separate independent stack.

This reduces duplication and makes comparison easier.

## 16.3 Asset Library Strategy

The generative completion layer should use a curated, limited 3D asset library for hackathon speed.

Recommended P0 asset coverage:

- building block variants
- vehicles
- trees
- poles / towers
- containers
- fences

Each asset should have:

- class tag
- nominal dimensions
- preview thumbnail if possible
- license metadata

---

## 17. Performance and Computation Targets

These are target ranges for the hackathon, not contractual guarantees.

### Input assumptions

- video length: about 10 minutes
- resolution: likely 1080p to 4K
- selected frames: tens to low hundreds after filtering

### Target experience

- job start acknowledgment: under 5 seconds
- progress updates: every few seconds
- keyframe extraction preview: early in the job
- full pipeline completion: ideally within 10 to 30 minutes for demo-scale inputs, depending on hardware and selected pipeline stages

### Optimization priorities

- aggressively reduce duplicate frames
- cap default selected frame counts
- make generative stages optional or mode-gated
- pre-cache asset library

---

## 18. Security and Privacy Considerations

## 18.1 Current State

- App runs locally
- Files are stored locally
- But compute may be sent to `Modal`

### Required messaging

The product must clearly state:

- local hosting does not currently equal full data sovereignty
- remote compute means some data leaves the local machine

## 18.2 Security Considerations

- keep artifacts in job-scoped directories
- avoid exposing arbitrary filesystem paths via API
- validate uploaded file types and sizes
- add cleanup strategy for large local artifacts
- avoid logging sensitive file contents

## 18.3 Privacy Considerations

- drone footage may contain sensitive imagery
- derived frames and scene assets are also sensitive
- future production version should support fully local GPU execution

---

## 19. Licensing Considerations

The MVP may combine several categories of tools and assets that need review.

### Items requiring license review

- `COLMAP`
- `Open3D`
- any depth estimation model
- any object detection model
- any generative model or weights
- any prebuilt 3D asset library

### Requirements

- maintain a dependency and asset license list
- avoid using assets that cannot be redistributed or demoed
- track provenance for inserted 3D assets

---

## 20. Success Metrics

### Hackathon success metrics

- End-to-end demo works from a single uploaded video
- Final scene is visually understandable and explorable
- Exact and generative modes are both demonstrable
- Semantic boxes and class filters work in the viewer
- Confidence overlay is visible and meaningful
- Architecture explanation is coherent and honest

### Product metrics

- time to first progress update
- time to final scene
- keyframe count vs reconstruction quality
- number of detected semantic objects
- number of successful exports
- qualitative demo clarity and judge understanding

---

## 21. Demo Flow

Recommended demo sequence:

1. Introduce the problem: raw drone video is hard to turn into usable spatial intelligence.
2. Upload one large drone video in the local app.
3. Show progressive pipeline stages.
4. Reveal selected keyframes and explain intelligent frame selection.
5. Open `Exact Reconstruction` result and show faithful geometry.
6. Toggle semantic cuboid boxes and class filters.
7. Show scene graph and confidence overlay.
8. Switch to `Generative Reconstruction`.
9. Highlight ambiguous or blurry objects completed using semantic priors and asset library.
10. Export final output package.
11. Close with the architecture roadmap: local-first today, fully on-prem GPU worker tomorrow.

---

## 22. Risks and Mitigations

### Risk: Reconstruction quality is poor on weak footage

Mitigation:

- aggressive keyframe selection
- confidence map
- exact vs generative distinction
- choose a demo video with good overlap and visibility

### Risk: Pipeline takes too long for a live demo

Mitigation:

- prepare cached demo jobs
- cap frame counts
- use shorter demo clip if needed
- show progressive outputs early

### Risk: Generative completion looks fake or misleading

Mitigation:

- clearly label inferred content
- only use generative completion in low-confidence regions
- use constrained asset classes

### Risk: Semantic detection is noisy

Mitigation:

- limit class taxonomy for MVP
- expose confidence values
- allow class filtering and hide low-confidence defaults

### Risk: Data sovereignty claim is challenged

Mitigation:

- explicitly state current remote compute dependency
- position on-prem GPU worker as production roadmap

### Risk: Asset licensing issues

Mitigation:

- use a small reviewed asset set
- track provenance

---

## 23. Milestones

## 23.1 Hackathon Build Plan

### Milestone 1: Core app skeleton

- frontend upload page
- backend job creation
- local storage layout
- progress model

### Milestone 2: Classical reconstruction baseline

- frame extraction
- keyframe selection
- `COLMAP` integration
- `Open3D` post-processing

### Milestone 3: Viewer and semantic layer

- scene viewer
- object boxes
- class filters
- artifact loading

### Milestone 4: Generative mode

- ambiguity detection heuristic
- asset library insertion
- inferred-region labeling

### Milestone 5: Demo hardening

- confidence overlay
- export packaging
- seeded demo inputs
- narrative polish

---

## 24. Open Questions

- What exact 3D viewer stack will be used in the frontend?
- What frame-selection heuristic or model mix is most practical within hackathon time?
- Which depth estimation model offers the best quality-speed tradeoff?
- Will `COLMAP` and related heavy processing run locally, remotely, or split across both?
- What object taxonomy should be included in P0 vs deferred?
- What specific 3D asset sources are approved for hackathon use?
- How will ambiguous-region detection be computed for generative completion triggers?
- How much drone metadata is expected to be available for scale estimation?
- Should exact and generative outputs be separate scene files or one scene with layers?
- Will progress updates use polling, SSE, or WebSockets?

---

## 25. Recommended P0 / P1 / P2 Backlog

## P0

- single-video upload
- local file persistence
- job orchestration
- stage-based progress UI
- keyframe extraction and selection
- `COLMAP` + `Open3D` exact reconstruction
- depth-assisted enhancement
- semantic 3D boxes
- class filtering
- scene graph JSON
- confidence overlay
- generative completion with constrained asset library
- `GLB` export
- clear architecture/privacy note

## P1

- metric scaling
- richer object classes
- side-by-side exact vs generative comparison
- additional export formats
- preview thumbnails
- multi-LOD packaging

## P2

- on-prem GPU worker
- multi-video fusion
- georegistration
- collaboration
- natural-language scene querying

---

## 26. Final Recommendation

For the hackathon, `God's Eye` should be built and presented as:

- a local-first drone-to-3D scene intelligence tool
- with one giant upload and a polished progressive UX
- grounded in classical reconstruction for trust
- enhanced by AI for completeness and usability
- honest about current remote compute tradeoffs
- clearly designed to evolve into a true on-prem production system

The MVP should optimize for one thing above all else:

> A convincing end-to-end demo that turns one drone video into a semantically rich 3D scene with both exact and generative views.

