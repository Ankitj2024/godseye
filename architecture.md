# God's Eye Architecture

## Document Status

- Product: `God's Eye`
- Type: Backend-Only System Architecture
- Date: August 26, 2026
- Scope: Python orchestrator + Modal workers

---

## 1. Purpose

This document defines the revised architecture for `God's Eye` after removing the frontend entirely. The system is now a local Python pipeline that takes a video path, orchestrates work, sends compute-heavy stages to Modal, and writes outputs back to the local root folder.

---

## 2. High-Level Architecture

```text
Local Root Folder
   |
   +-- input video
   +-- run_pipeline.py
   +-- outputs/
   +-- work/
   +-- assets/
   |
   v
Local Python Orchestrator
   |
   +-- input validation
   +-- job setup
   +-- manifest/logging
   +-- stage orchestration
   +-- output packaging
   |
   v
Modal Workers
   |
   +-- frame analysis / selection
   +-- reconstruction stages
   +-- depth enhancement
   +-- semantic detection
   +-- generative completion
   +-- artifact packaging
```

---

## 3. Core Architectural Decision

The local machine should do only lightweight orchestration and filesystem management.

Modal should do all compute-heavy work wherever practical.

This means:

- Python locally is the control plane
- Modal is the compute plane
- the local filesystem is the source of truth for input and output artifacts

---

## 4. Major Components

## 4.1 Local Python Orchestrator

Responsibilities:

- parse CLI arguments
- validate video path
- generate job ID
- create working directories
- stage files for remote processing
- invoke Modal functions
- track stage state in local manifests
- collect returned artifacts
- write final outputs to root output folder

The orchestrator should remain thin and predictable.

## 4.2 Modal Worker Layer

Responsibilities:

- run GPU-heavy and CPU-heavy processing that is too expensive or too slow locally
- receive staged inputs
- produce deterministic artifacts per stage
- return file outputs or stage results back to the local pipeline

Recommended Modal worker groupings:

- video preprocessing worker
- reconstruction worker
- depth worker
- semantic worker
- generative completion worker
- export worker

## 4.3 Asset Library

Responsibilities:

- provide class-matched 3D assets for generative completion
- maintain metadata for asset class, dimensions, and provenance

Suggested local location:

```text
assets/
```

## 4.4 Output Packaging Layer

Responsibilities:

- normalize stage outputs
- package final scene outputs
- copy deliverables into root output folder

---

## 5. Working Directory Layout

Recommended root layout:

```text
godseye/
├── run_pipeline.py
├── sample_video.mp4
├── outputs/
├── work/
├── assets/
├── modal/
└── src/
```

Recommended working structure:

```text
work/<job_id>/
├── input/
│   └── video.mp4
├── frames/
│   ├── candidates/
│   └── selected/
├── reconstruction/
├── depth/
├── semantics/
├── scene_graph/
├── completion/
├── exports/
├── logs/
└── manifest.json
```

Final deliverables should land in:

```text
outputs/<job_id>/
```

---

## 6. Pipeline Architecture

The pipeline should be stage-based and file-oriented.

## 6.1 Stage Order

1. input validation
2. job creation
3. frame extraction
4. intelligent keyframe selection
5. exact reconstruction
6. depth enhancement
7. semantic 3D detection
8. scene graph generation
9. generative completion
10. export packaging

## 6.2 Stage Contracts

Each stage should:

- take explicit input files and metadata
- write output artifacts into its own folder
- update `manifest.json`
- be rerunnable independently if possible

---

## 7. Exact vs Generative Layering

The architecture should treat exact reconstruction as the baseline layer.

### Exact path

- selected frames
- `COLMAP`
- `Open3D`
- honest geometry output

### Generative path

- consume exact output
- inspect low-confidence or ambiguous regions
- use semantic classes plus asset priors
- insert inferred assets into a second scene variant

Outputs should stay separate:

- `exact_scene.*`
- `generative_scene.*`

This keeps measured and inferred content clearly distinguishable.

---

## 8. Modal Boundary

## 8.1 What should move to Modal

Priority Modal stages:

- frame analysis at scale
- dense reconstruction if practical
- depth estimation
- semantic model inference
- generative completion

## 8.2 What can stay local

- CLI parsing
- directory setup
- manifest writing
- output copying
- final root-folder packaging

## 8.3 Practical caveat

`COLMAP` and some reconstruction dependencies may be operationally tricky in Modal. If needed, treat them as separate worker containers or isolate them behind one reconstruction service boundary so they can move later without changing the pipeline contract.

---

## 9. Manifest and State Tracking

The pipeline should avoid a database for now and use file-based manifests.

Suggested manifest fields:

- job ID
- input video path
- mode
- created timestamp
- current stage
- completed stages
- failed stages
- artifact paths
- timings
- notes

Suggested files:

```text
work/<job_id>/manifest.json
work/<job_id>/logs/
```

---

## 10. Output Contract

Minimum final outputs:

- `exact_scene.glb` or `exact_scene.gltf`
- `generative_scene.glb` or `generative_scene.gltf` when requested
- `scene.json`
- `objects.json`
- `scene_graph.json`
- `confidence.json`
- `run_summary.json`

Optional outputs:

- `pointcloud.ply`
- `mesh.obj`
- preview renders

These should be copied into:

```text
outputs/<job_id>/
```

---

## 11. Error Handling

The system should be resilient without a frontend.

Required behaviors:

- fail with readable local logs
- preserve intermediate artifacts when useful
- allow exact mode to succeed even if generative mode fails
- surface whether failure happened locally or in Modal

---

## 12. Security and Privacy

This architecture is local-first but not fully sovereign.

Why:

- source video is local
- outputs are local
- but heavy processing on Modal means data leaves the local machine

Future production direction:

- swap Modal workers for on-prem GPU workers
- keep the same file-based and stage-based local orchestration shape

---

## 13. Recommended Code Layout

```text
src/
├── cli/
├── orchestrator/
├── pipeline/
├── stages/
├── artifacts/
├── assets/
├── utils/
└── schemas/

modal/
├── preprocess/
├── reconstruction/
├── depth/
├── semantics/
├── completion/
└── export/
```

Suggested root entrypoint:

```text
run_pipeline.py
```

---

## 14. Final Summary

The right architecture now is:

- one local Python entrypoint
- one local root folder for inputs and outputs
- one file-based job model
- one stage-based pipeline
- Modal for heavy compute

This keeps the system simple enough to build fast while preserving all major product capabilities.
