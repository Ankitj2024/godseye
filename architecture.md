# God's Eye Architecture

## Document Status

- Product: `God's Eye`
- Type: System Architecture
- Date: August 24, 2026
- Scope: Hackathon MVP with production direction

---

## 1. Purpose

This document defines the system architecture for `God's Eye`, a local-first drone-video-to-3D-scene application. It translates the PRD into a concrete technical design that the team can build during the hackathon while preserving a path to a future fully on-prem deployment.

The architecture is designed around one primary workflow:

> A user uploads one large drone video and receives a semantically enriched 3D scene through a staged asynchronous pipeline.

---

## 2. Architecture Goals

- Keep the user experience simple: one upload, one job, progressive results.
- Run the app locally on `localhost`.
- Store source files and generated artifacts on the local filesystem.
- Offload heavy compute to `Modal` for the hackathon.
- Separate faithful reconstruction from AI-assisted completion.
- Surface uncertainty explicitly through confidence signals.
- Keep the system modular enough to replace remote compute with an on-prem GPU worker later.

---

## 3. Architecture Principles

- `Local-first app`: frontend, backend, and storage live on the user's machine.
- `Async by default`: reconstruction is a job pipeline, not a synchronous request.
- `Pipeline clarity`: every major stage should produce status, logs, and artifacts.
- `Composable outputs`: exact reconstruction, semantic annotations, and generative completion should be layered rather than tightly fused.
- `Honest sovereignty`: current remote compute means the system is not yet fully sovereign.
- `Replaceable compute`: heavy processing should sit behind worker interfaces so Modal can be swapped later.

---

## 4. High-Level System

```text
┌────────────────────────────────────────────────────────────┐
│                     User Machine                           │
│                                                            │
│  ┌─────────────────────┐       ┌────────────────────────┐  │
│  │ React + TypeScript  │ <---- │ FastAPI Backend        │  │
│  │ Frontend            │       │ API + Orchestrator     │  │
│  └─────────────────────┘       └────────────────────────┘  │
│             |                              |                │
│             |                              v                │
│             |                    ┌───────────────────────┐  │
│             |                    │ Local Filesystem      │  │
│             |                    │ uploads/jobs/outputs  │  │
│             |                    └───────────────────────┘  │
│             |                              |                │
│             |                              v                │
│             |                    ┌───────────────────────┐  │
│             |                    │ Local Job State       │  │
│             |                    │ progress/artifacts    │  │
│             |                    └───────────────────────┘  │
└─────────────|──────────────────────────────|────────────────┘
              |                              |
              |                              v
              |                    ┌───────────────────────┐
              |                    │ Modal GPU Workers     │
              |                    │ heavy compute stages  │
              |                    └───────────────────────┘
              |
              v
      3D Scene Viewer
```

---

## 5. Major Components

## 5.1 Frontend

Technology:

- `React`
- `TypeScript`

Responsibilities:

- accept one large video upload
- allow mode selection:
  - `Exact Reconstruction`
  - `Generative Reconstruction`
- create and monitor jobs
- show pipeline stages and progress
- preview intermediate artifacts where available
- render final 3D scene
- expose semantic toggles:
  - 3D cuboid boxes
  - class filters
  - confidence overlay
  - exact vs generative views
- trigger exports

Recommended frontend modules:

- upload flow
- job status dashboard
- artifact preview panel
- 3D scene viewer
- semantic controls panel
- export/download actions

## 5.2 Backend API

Technology:

- `Python`
- `FastAPI`

Responsibilities:

- receive uploads
- persist files locally
- create job records
- manage stage progression
- dispatch worker tasks
- aggregate artifacts and metadata
- provide APIs for progress, scene loading, detections, confidence, and downloads

The backend is the control plane of the system. It should remain lightweight and orchestration-focused rather than doing all heavy reconstruction inline.

## 5.3 Local Filesystem Storage

Responsibilities:

- store uploaded video
- store candidate frames and selected keyframes
- store reconstruction outputs
- store semantic metadata
- store generated previews
- store scene exports
- store job manifest and stage state

This is the storage of record for the hackathon application.

## 5.4 Worker Layer

Current implementation:

- `Modal` serverless GPU workers

Responsibilities:

- frame analysis
- depth estimation
- semantic detection
- optional generative completion
- any other compute-heavy stage

Some classical stages may still run locally if simpler to integrate, but the architecture should isolate these as pipeline tasks rather than hardcode them into request handlers.

## 5.5 Reconstruction Layer

Primary tools:

- `COLMAP`
- `Open3D`

Responsibilities:

- camera pose estimation
- sparse reconstruction
- dense geometry generation
- mesh or point cloud post-processing
- cleanup and packaging

## 5.6 AI Enhancement Layer

Responsibilities:

- learned depth estimation
- semantic object detection
- ambiguity scoring
- generative scene completion using constrained 3D assets

## 5.7 Scene Representation Layer

Responsibilities:

- unify raw geometry with semantic annotations
- maintain scene graph
- store confidence information
- package viewer-ready scene outputs

---

## 6. Logical Architecture

```text
Upload Layer
  -> Ingest Layer
  -> Job Orchestrator
  -> Processing Pipeline
     -> Frame Selection
     -> Exact Reconstruction
     -> Depth Enhancement
     -> Semantic Detection
     -> Scene Graph Builder
     -> Generative Completion
     -> Output Packaging
  -> Viewer APIs
  -> Export Layer
```

This separates user-facing actions from compute-heavy processing and keeps pipeline stages independently testable.

---

## 7. Deployment Architecture

## 7.1 Hackathon Deployment

```text
Localhost Frontend
    |
    v
Localhost FastAPI
    |
    +--> Local Filesystem
    |
    +--> Local Job State
    |
    +--> Modal Workers
```

Properties:

- simplest to develop quickly
- consistent with local/on-prem UX
- avoids early cloud hosting complexity
- not fully sovereign because processing can leave the machine

## 7.2 Production Direction

```text
Localhost or Customer-Hosted Frontend
    |
    v
Customer-Controlled API
    |
    +--> Customer Storage
    |
    +--> On-Prem Job Queue
    |
    +--> On-Prem GPU Worker Pool
```

Properties:

- full or near-full data sovereignty
- deployable inside customer environment
- same user-facing product model
- better enterprise posture

---

## 8. Data Flow

## 8.1 End-to-End Processing Flow

```text
1. Upload video
2. Save file locally
3. Create job record
4. Generate candidate frames
5. Select keyframes
6. Run exact reconstruction
7. Run depth enhancement
8. Run semantic detection
9. Build scene graph
10. Optionally run generative completion
11. Package outputs
12. Load scene in viewer
13. Export artifacts
```

## 8.2 Detailed Stage Flow

### Stage 1: Ingest

Inputs:

- uploaded video
- mode selection

Outputs:

- local video file
- job manifest
- extracted video metadata

### Stage 2: Frame Analysis and Selection

Inputs:

- local video file

Processing:

- sample candidate frames
- compute blur/sharpness
- compute spacing/overlap heuristics
- remove low-value or duplicate frames

Outputs:

- candidate frame set
- selected keyframe set
- frame selection metadata

### Stage 3: Exact Reconstruction

Inputs:

- selected keyframes

Processing:

- feature extraction and matching
- camera pose solving
- sparse point cloud
- dense geometry
- cleanup / meshing

Outputs:

- camera poses
- sparse point cloud
- dense point cloud or mesh
- reconstruction logs

### Stage 4: Depth Enhancement

Inputs:

- selected frames
- baseline geometry

Processing:

- infer learned depth
- fuse or use depth to improve weak geometry regions

Outputs:

- enhanced geometry or auxiliary depth products
- enhancement metadata

### Stage 5: Semantic Detection

Inputs:

- frames and/or geometry

Processing:

- detect object classes
- estimate approximate 3D location and extents

Outputs:

- semantic object list
- 3D cuboid metadata
- class confidence

### Stage 6: Scene Graph

Inputs:

- geometry
- semantic objects

Processing:

- define nodes
- define relationships
- attach provenance and confidence

Outputs:

- scene graph JSON

### Stage 7: Generative Completion

Inputs:

- exact scene
- ambiguity or low-confidence regions
- detected classes
- asset library

Processing:

- identify incomplete regions
- choose class-matched assets
- place assets into scene with transforms
- mark as inferred

Outputs:

- generative scene variant
- inferred object metadata

### Stage 8: Packaging

Outputs:

- main `GLB` or `glTF`
- `scene.json`
- detections metadata
- confidence metadata
- previews
- download bundle

---

## 9. Exact vs Generative Architecture

The architecture should treat `Exact Reconstruction` as the baseline truth layer and `Generative Reconstruction` as an augmentation layer.

### Exact path

- only uses observed evidence plus deterministic reconstruction/post-processing
- preserves gaps where evidence is weak
- prioritizes geometric faithfulness

### Generative path

- starts from the exact path outputs
- uses semantic context and prior assets to fill incomplete areas
- stores provenance so inferred content is distinguishable

### Why this matters

- avoids mixing measured and inferred geometry without traceability
- enables side-by-side comparison
- improves trust during demos and future enterprise use

---

## 10. Job Architecture

## 10.1 Job Lifecycle

```text
created
-> ingesting
-> selecting_frames
-> reconstructing
-> enhancing_depth
-> detecting_semantics
-> building_scene_graph
-> completing_scene
-> packaging
-> completed
```

Failure state:

```text
failed
```

Optional recovery state:

```text
partial_success
```

## 10.2 Job Record

Each job should store:

- job ID
- mode
- file metadata
- stage statuses
- percent complete
- human-readable stage messages
- artifact paths
- timings
- error details
- final summary

## 10.3 Progress Delivery

Preferred options:

- polling for simplicity in MVP
- SSE as a better progressive option if time allows

WebSockets are optional and not necessary for the hackathon.

---

## 11. API Architecture

Recommended public API shape:

- `POST /api/jobs`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/progress`
- `GET /api/jobs/{job_id}/scene`
- `GET /api/jobs/{job_id}/detections`
- `GET /api/jobs/{job_id}/scene-graph`
- `GET /api/jobs/{job_id}/confidence`
- `GET /api/jobs/{job_id}/artifacts`
- `GET /api/jobs/{job_id}/download`

Recommended backend internal service boundaries:

- upload service
- job service
- frame selection service
- reconstruction service
- depth service
- semantic service
- scene graph service
- completion service
- export service

---

## 12. Storage Architecture

## 12.1 Top-Level Layout

```text
data/
├── uploads/
├── jobs/
├── frames/
├── processing/
├── outputs/
└── assets/
```

## 12.2 Per-Job Layout

```text
data/jobs/<job_id>/
├── input/
│   └── video.mp4
├── metadata/
│   ├── job.json
│   ├── progress.json
│   └── video.json
├── frames/
│   ├── candidates/
│   └── selected/
├── reconstruction/
│   ├── sparse/
│   ├── dense/
│   └── mesh/
├── depth/
├── semantics/
├── scene_graph/
├── completion/
├── previews/
└── exports/
```

## 12.3 Asset Library Layout

```text
data/assets/
├── buildings/
├── vehicles/
├── trees/
├── poles/
├── containers/
└── metadata/
```

Each asset should include:

- model file
- class tag
- dimension hints
- preview image if possible
- license/provenance metadata

---

## 13. Scene Data Architecture

## 13.1 Core Scene Layers

The viewer-ready scene should logically contain:

- geometry layer
- semantic object layer
- scene graph metadata layer
- confidence layer
- inferred-content layer

## 13.2 Scene Metadata Model

`scene.json` should contain at minimum:

- job ID
- reconstruction mode
- creation timestamp
- scale status
- asset references
- object list
- object classes
- confidence summaries
- inferred-region markers
- scene graph references

## 13.3 Object Model

Each detected or inserted object should include:

- object ID
- class
- transform
- dimensions
- confidence
- provenance
- source:
  - observed
  - depth-assisted
  - inferred

---

## 14. Semantic and Confidence Architecture

## 14.1 Semantic Layer

The semantic subsystem should be designed around a constrained taxonomy in P0.

Suggested P0 classes:

- building
- road
- vehicle
- tree
- pole
- tower
- container
- fence

This reduces noise and makes the demo easier to explain.

## 14.2 Confidence Layer

Confidence should be attached to:

- reconstructed regions
- object detections
- inserted generative assets

Suggested confidence buckets:

- high: strongly observed
- medium: observed but enhanced
- low: inferred or ambiguous

## 14.3 Provenance

Every object or region should be traceable to one of:

- classical reconstruction
- depth-assisted reconstruction
- asset-based generative completion

This is critical for trust and future explainability.

---

## 15. Compute Architecture

## 15.1 Why Remote Compute Exists in the MVP

Heavy stages may be too slow or operationally difficult to run entirely on a standard local machine during the hackathon. `Modal` provides practical GPU execution without requiring the team to build a full local GPU orchestration stack.

## 15.2 Remote Compute Boundary

Candidate remote stages:

- depth estimation
- semantic detection
- generative completion
- possibly dense reconstruction or post-processing if needed

Candidate local stages:

- upload handling
- job orchestration
- local artifact packaging
- viewer serving
- possibly some frame extraction and reconstruction steps

## 15.3 Swap Strategy for Future On-Prem Worker

To preserve portability:

- define task interfaces per stage
- avoid embedding Modal-specific assumptions in frontend APIs
- keep artifact contracts filesystem-oriented and serializable
- isolate worker invocation in one service layer

---

## 16. Security and Privacy Architecture

## 16.1 Security Boundaries

- frontend only talks to the local backend
- backend owns local file access
- workers should receive only required job inputs
- outputs should be written back into job-scoped directories

## 16.2 Privacy Reality

The current architecture is not fully sovereign because remote compute may process user-derived data.

Required product messaging:

- local hosting does not guarantee local-only computation
- truly sovereign deployment requires the future on-prem worker architecture

## 16.3 Operational Safeguards

- validate upload format and size
- isolate jobs by directory
- avoid arbitrary path access
- support cleanup of large artifacts
- keep logs metadata-focused

---

## 17. Performance Architecture

## 17.1 Performance Constraints

- long source videos are expensive to process directly
- duplicate frames can explode compute cost
- dense reconstruction and AI stages are the biggest time risks

## 17.2 Performance Strategy

- aggressively reduce frame count early
- stage outputs so the UI can reveal partial progress
- make generative stages conditional by mode
- cache reusable assets
- keep export packaging lightweight

## 17.3 Demo Performance Target

The architecture should support:

- immediate job acknowledgment
- early visible progress
- eventual completion within a demo-friendly time window, ideally 10 to 30 minutes depending on input and settings

---

## 18. Failure and Recovery Design

## 18.1 Failure Modes

- upload too large or invalid
- poor footage causes weak reconstruction
- worker stage timeout
- semantic detection failure
- generative completion failure
- packaging failure

## 18.2 Recovery Strategy

- preserve job logs
- preserve partial artifacts
- allow exact output even if generative completion fails
- expose failure stage clearly in UI

## 18.3 Demo Strategy

The team should prepare:

- one fully precomputed demo job
- one short live demo input
- fallback screenshots or exported outputs

---

## 19. Recommended Repository Structure

```text
godseye/
├── frontend/
│   └── src/
├── backend/
│   └── app/
├── modal/
│   └── workers/
├── shared/
│   └── schemas/
├── data/
├── docs/
│   ├── PRD.md
│   └── ARCHITECTURE.md
└── README.md
```

Suggested backend internal structure:

```text
backend/app/
├── api/
├── core/
├── models/
├── services/
├── workers/
├── pipelines/
└── utils/
```

---

## 20. Build Priorities

## P0

- upload pipeline
- local storage and job state
- progress architecture
- keyframe selection stage
- exact reconstruction integration
- semantic metadata flow
- confidence metadata flow
- generative completion layer
- scene viewer loading contract

## P1

- side-by-side exact vs generative comparison
- richer scene graph
- multiple export formats
- metric scale support

## P2

- full on-prem worker replacement
- multi-video fusion
- advanced querying and collaboration

---

## 21. Open Architecture Questions

- Which stages will run locally vs remotely in the first build?
- What exact viewer stack will render the final scene?
- How should confidence be encoded for geometry regions in the viewer?
- What heuristic determines when a region is eligible for generative completion?
- How will 3D cuboids be estimated from 2D detections and reconstructed geometry?
- Will stage progress be stored in JSON files, a local database, or both?
- What is the minimum viable asset taxonomy for believable scene completion?

---

## 22. Final Architectural Summary

`God's Eye` should be built as a local-first, asynchronous reconstruction system with a clean control plane on the user's machine and replaceable heavy compute behind worker interfaces.

For the hackathon, the architecture should optimize for:

- fast implementation
- demo reliability
- clear stage visibility
- honest distinction between observed and inferred scene content

The most important architectural decision is this:

> Build one exact reconstruction baseline, then layer semantics, confidence, and generative completion on top of it.

That keeps the system understandable, extensible, and credible for both a hackathon demo and a future production path.

