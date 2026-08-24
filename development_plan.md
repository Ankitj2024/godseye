# God's Eye Development Plan

## Document Status

- Product: `God's Eye`
- Type: Step-wise Development Plan
- Date: August 24, 2026
- Goal: Build the product segment by segment in the right order, with each phase producing a usable milestone.

---

## 1. Purpose

This document defines the recommended build order for `God's Eye`. The goal is to avoid building everything at once and instead create the system in stable layers, where each completed segment becomes the foundation for the next one.

This plan is optimized for hackathon execution:

- fastest path to a working demo
- lowest integration risk
- clear dependency ordering
- ability to stop at any stage and still have something demoable

---

## 2. Development Strategy

The system should be built in this order:

1. `Core app skeleton`
2. `Local upload and job flow`
3. `Frame extraction and selection`
4. `Exact reconstruction baseline`
5. `3D viewer integration`
6. `Progressive job UX`
7. `Semantic object layer`
8. `Confidence and scene graph layer`
9. `Generative reconstruction layer`
10. `Export, polish, and demo hardening`

This order matters because:

- there is no point building semantics before a scene exists
- there is no point building generative completion before the exact baseline exists
- there is no point polishing UX before the pipeline contract is stable

---

## 3. Build Philosophy

Every segment should satisfy three rules:

- it should be independently testable
- it should leave behind reusable interfaces
- it should improve the demo, not just the codebase

At the end of each major phase, the team should have:

- something that runs
- something that can be shown
- something that reduces future integration uncertainty

---

## 4. Priority Model

## P0

Must be built first. Without these, the product does not function.

## P1

Build after the core path works. These make the product compelling.

## P2

Build only after the MVP pipeline is stable. These improve quality, depth, or production-readiness.

---

## 5. Phase-by-Phase Plan

## Phase 0: Project Setup and Contracts

Priority: `P0`

### Goal

Create the project skeleton, define interfaces, and remove ambiguity before implementation starts.

### Why this comes first

If the frontend, backend, storage layout, and job model are not agreed early, later integration will become messy.

### Build in this phase

- repo structure
- frontend app bootstrap
- backend app bootstrap
- shared config and environment setup
- local data directory structure
- initial job model
- initial API contract
- artifact naming conventions

### Deliverables

- runnable frontend shell
- runnable backend shell
- empty API endpoints
- agreed directory layout
- basic README/setup instructions

### Exit criteria

- frontend starts locally
- backend starts locally
- backend can return a health check
- the team agrees on job ID and artifact path conventions

---

## Phase 1: Upload and Job Creation

Priority: `P0`

### Goal

Get the first real user flow working: upload one video, create one job, store the file locally, and return job status.

### Why this comes early

This is the entry point of the whole product. Everything else depends on the app reliably accepting the input and creating a persistent job.

### Build in this phase

- video upload UI
- mode selection UI:
  - `Exact Reconstruction`
  - `Generative Reconstruction`
- `POST /api/jobs`
- local video storage
- job manifest creation
- `GET /api/jobs/{job_id}`
- simple job list/status response

### Deliverables

- user can upload a large video
- backend stores it locally
- backend creates a stable job record
- frontend can show created job status

### Exit criteria

- one upload works end-to-end
- large file handling is stable enough for demo usage
- uploaded file lands in the expected local directory
- job metadata persists and is reloadable

---

## Phase 2: Job State and Progress Framework

Priority: `P0`

### Goal

Create the progress architecture before heavy processing starts.

### Why this comes before reconstruction

Long-running work without progress visibility is hard to debug and hard to demo. The progress model should exist before compute stages are added.

### Build in this phase

- job state machine
- progress stages
- status polling endpoint
- local progress persistence
- failure state handling
- frontend progress view

### Suggested minimum stages

- uploaded
- analyzing
- selecting_frames
- reconstructing
- enhancing
- detecting
- packaging
- completed
- failed

### Deliverables

- a job can move through mocked stages
- UI reflects stage updates correctly
- failures can be surfaced to the user

### Exit criteria

- mocked background jobs can update progress
- frontend reflects stage transitions cleanly
- job state survives page refresh

---

## Phase 3: Frame Extraction and Intelligent Selection

Priority: `P0`

### Goal

Turn the long drone video into a usable set of keyframes for reconstruction.

### Why this comes before reconstruction

This stage reduces compute cost and directly affects the quality of everything that follows.

### Build in this phase

- candidate frame extraction
- blur / sharpness scoring
- overlap / duplication filtering
- frame spacing heuristics
- selected keyframe manifest
- preview thumbnails for selected frames

### Deliverables

- backend can extract candidate frames
- backend can produce a selected keyframe set
- frontend can preview selected frames for a job

### Exit criteria

- a 10-minute video can produce a manageable keyframe subset
- duplicate and poor-quality frames are filtered out
- selected frames are stored and referenced by metadata

---

## Phase 4: Exact Reconstruction Baseline

Priority: `P0`

### Goal

Produce the first true 3D output from selected keyframes using classical reconstruction.

### Why this is the core of the product

This is the baseline truth layer. Every later capability depends on having this working first.

### Build in this phase

- `COLMAP` integration
- camera pose estimation
- sparse reconstruction
- dense point cloud or mesh generation
- `Open3D` post-processing
- scene artifact persistence

### Deliverables

- exact reconstruction pipeline for one job
- output geometry saved locally
- camera poses and mesh/point cloud artifact

### Exit criteria

- at least one test video produces a usable 3D artifact
- output can be loaded from disk reliably
- logs and failures are visible

### Notes

Do not build generative completion before this phase is stable.

---

## Phase 5: Viewer Integration

Priority: `P0`

### Goal

Make the 3D output visible in the product.

### Why it comes now

A reconstruction pipeline is not demoable if users cannot see the result inside the app.

### Build in this phase

- choose and integrate web 3D viewer
- load exact reconstruction artifact
- camera controls
- scene loading state
- error handling for invalid scene artifacts

### Deliverables

- frontend can display the exact reconstruction result
- user can navigate the 3D scene

### Exit criteria

- one job can be opened and viewed in-browser
- viewer loads consistently from the local scene package

---

## Phase 6: End-to-End MVP Flow Hardening

Priority: `P0`

### Goal

Stabilize the complete minimal flow before adding intelligence layers.

### Why this phase matters

If upload, job orchestration, reconstruction, and viewing are not stable together, later features will only compound instability.

### Build in this phase

- cleanup pass on all previous segments
- stronger error handling
- stage timing visibility
- retry or resume strategy where feasible
- better local artifact packaging

### Deliverables

- stable end-to-end exact-mode MVP
- team can run a full demo with the baseline pipeline

### Exit criteria

- the exact-mode workflow can be run from upload to view without manual intervention
- known failure cases are understandable

---

## Phase 7: Semantic Object Detection Layer

Priority: `P1`

### Goal

Add scene understanding on top of the exact 3D output.

### Why this comes after the baseline MVP

Semantic information is valuable, but it should enrich a working scene rather than block the creation of one.

### Build in this phase

- object class detection
- 3D cuboid estimation
- object metadata schema
- class confidence scores
- API endpoint for detections
- frontend box toggles
- frontend class filtering

### Deliverables

- semantic objects appear in the viewer
- user can show/hide boxes
- user can filter by class

### Exit criteria

- at least a limited class taxonomy works reliably enough for demo footage
- detections are stored and reloadable with the job

---

## Phase 8: Confidence Layer and Scene Graph

Priority: `P1`

### Goal

Add explainability and structure to the scene.

### Why it comes here

Once semantics exist, the next most valuable improvement is helping users understand what is certain, what is inferred, and how entities relate.

### Build in this phase

- confidence scoring schema
- confidence metadata export
- confidence overlay in viewer
- scene graph JSON generation
- scene node and relation model
- basic scene graph API endpoint

### Deliverables

- user can inspect confidence regions or categories
- scene graph artifact exists for each processed job

### Exit criteria

- confidence is visible in a meaningful way
- scene graph includes nodes, classes, provenance, and basic relationships

---

## Phase 9: Depth Enhancement

Priority: `P1`

### Goal

Improve weak geometry using learned depth estimation.

### Why it comes after the baseline

Depth enhancement improves quality, but it should not be required for the first working reconstruction.

### Build in this phase

- depth estimation stage
- geometry enhancement or fusion logic
- metadata for depth-assisted regions
- progress stage integration

### Deliverables

- enhanced geometry in weak regions where feasible
- visible metadata distinction between exact and depth-assisted regions

### Exit criteria

- the stage improves at least some demo scenes without breaking the baseline pipeline

---

## Phase 10: Generative Reconstruction Layer

Priority: `P1`

### Goal

Create the second flagship mode: `Generative Reconstruction`.

### Why this comes late

This is a showcase feature, but it is also the easiest place to introduce confusion, instability, and demo risk. It should be built only after the exact path is solid.

### Build in this phase

- low-confidence / ambiguity detection
- prebuilt asset library integration
- object-class-to-asset mapping
- inferred object placement
- provenance tagging
- separate generative scene package
- UI switch between exact and generative views

### Deliverables

- user can open an AI-completed scene variant
- inferred objects are clearly marked
- exact and generative results can be compared

### Exit criteria

- generative mode works on at least one strong demo scene
- inserted assets are visibly plausible
- inferred content is clearly labeled

---

## Phase 11: Export and Packaging

Priority: `P1`

### Goal

Make outputs portable and easier to demo or share.

### Build in this phase

- export packaging
- `GLB` or `glTF` output contract
- `scene.json`
- detections metadata export
- confidence metadata export
- downloadable artifact bundle

### Deliverables

- user can download a packaged result
- output structure is consistent per job

### Exit criteria

- one-click export works for completed jobs

---

## Phase 12: Demo Hardening and UX Polish

Priority: `P1`

### Goal

Turn the working build into a convincing hackathon demo.

### Build in this phase

- cleaner copy and labeling
- better loading and stage messages
- curated demo assets
- performance tuning
- fallback flows for failed jobs
- side-by-side screenshots or previews if useful

### Deliverables

- polished demo path
- prepared backup demo materials

### Exit criteria

- team can demo the product confidently end-to-end
- judges can understand the difference between exact and generative modes quickly

---

## Phase 13: Advanced Features and Production Direction

Priority: `P2`

### Goal

Add deeper capabilities only after the MVP is fully stable.

### Candidate features

- metric scaling
- multiple LOD outputs
- richer scene graph relationships
- more semantic classes
- better confidence modeling
- multi-video fusion
- on-prem GPU worker replacement for Modal
- enterprise deployment hardening

### Exit criteria

- only pursue these if the MVP and demo are already secure

---

## 6. Recommended Segment Order Summary

If the team wants the shortest possible practical order, build in this sequence:

1. project skeleton
2. upload flow
3. job/progress framework
4. frame extraction and selection
5. exact reconstruction
6. viewer
7. stabilize end-to-end exact MVP
8. semantic detection
9. confidence + scene graph
10. depth enhancement
11. generative reconstruction
12. export and polish

This is the safest dependency order.

---

## 7. What Not to Build Too Early

Do not build these too early:

- advanced semantic taxonomy
- scene graph complexity
- polished export system
- multi-LOD outputs
- metric scaling
- collaboration features
- full on-prem worker replacement

These are valuable, but they should not delay the first working reconstruction demo.

---

## 8. Parallel Work Suggestions

Some work can happen in parallel once the interfaces are defined.

### Parallel track A: Frontend shell

- upload screen
- progress screen
- viewer shell

### Parallel track B: Backend control plane

- jobs API
- local storage
- progress persistence
- artifact manifest logic

### Parallel track C: Reconstruction pipeline

- frame extraction
- keyframe selection
- exact reconstruction

### Parallel track D: Intelligence layer

- semantic schema
- asset library preparation
- confidence schema

Important:

- only parallelize after Phase 0 contracts are agreed
- keep one owner responsible for integration contracts

---

## 9. Suggested Team Execution Model

If the team is small, assign by system layer:

- one owner for frontend and viewer
- one owner for backend and job orchestration
- one owner for reconstruction and AI pipeline

If the team is larger, split into:

- app flow
- reconstruction
- semantics and generative layer
- demo and polish

---

## 10. Milestone Checkpoints

## Checkpoint 1

Upload a video and create a stable local job.

## Checkpoint 2

Show stage-based progress in the UI.

## Checkpoint 3

Generate selected keyframes from a 10-minute video.

## Checkpoint 4

Produce one exact 3D reconstruction artifact.

## Checkpoint 5

View that exact output in the app.

## Checkpoint 6

Overlay semantic boxes and class filters.

## Checkpoint 7

Show confidence and scene graph artifacts.

## Checkpoint 8

Switch between exact and generative reconstruction.

## Checkpoint 9

Export the final packaged result.

---

## 11. Final Recommendation

The team should treat `Exact Reconstruction` as the first product, and `Generative Reconstruction` as the second product layered on top of it.

That means the development order should be:

- first, make the pipeline work
- then, make the scene visible
- then, make the scene understandable
- then, make the scene impressive

In practical terms, build the product until Phase 6 before spending real time on advanced AI completion. That is the point where the foundation is strong enough for the rest of the system to land cleanly.

