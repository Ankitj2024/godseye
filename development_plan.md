# God's Eye Development Plan

## Document Status

- Product: `God's Eye`
- Type: Backend-Only Step-Wise Development Plan
- Date: August 26, 2026

---

## 1. Purpose

This plan defines the build order for the new backend-only version of `God's Eye`.

We are no longer building:

- frontend
- web APIs
- upload flows
- viewer UX

We are now building:

- a local Python pipeline
- a Modal-backed heavy compute system
- a file-based artifact workflow
- a root-folder output contract

The goal is to build the system one segment at a time, with each segment leaving behind a usable foundation.

---

## 2. Recommended Build Order

Build in this order:

1. project skeleton and local file contract
2. CLI/script entrypoint
3. job manifest and stage tracking
4. frame extraction and keyframe selection
5. Modal integration foundation
6. exact reconstruction baseline
7. root output packaging
8. semantic detection outputs
9. confidence and scene graph outputs
10. depth enhancement
11. generative reconstruction
12. polish, performance, and hardening

This order is the safest because it follows the actual dependency graph of the system.

---

## 3. Priority Model

## P0

Required for the pipeline to work at all.

## P1

Required to make the pipeline compelling and aligned with the full feature set.

## P2

Useful improvements after the core system is stable.

---

## 4. Phase-by-Phase Plan

## Phase 0: Local Project Skeleton

Priority: `P0`

### Goal

Set up the codebase around a backend-only pipeline shape.

### Build

- root folder structure
- `src/` package layout
- `modal/` worker layout
- `assets/` folder
- `work/` folder
- `outputs/` folder
- config conventions

### Deliverables

- agreed folder layout
- stub entry script
- stub worker layout

### Exit criteria

- everyone is working against the same directory and artifact structure

---

## Phase 1: CLI Entrypoint

Priority: `P0`

### Goal

Make the system runnable from one local command.

### Build

- `run_pipeline.py`
- CLI argument parsing
- `--video` input
- `--mode exact|generative`
- optional `--output-dir`

### Deliverables

- one command starts the pipeline

### Exit criteria

- the script validates a video path and starts a job successfully

---

## Phase 2: Job Manifest and File-Based State

Priority: `P0`

### Goal

Create stable local tracking before real processing begins.

### Build

- job ID generation
- per-job working directory creation
- `manifest.json`
- stage status updates
- local logs

### Deliverables

- every run creates a stable job folder and manifest

### Exit criteria

- stage state survives failures and reruns

---

## Phase 3: Frame Extraction and Keyframe Selection

Priority: `P0`

### Goal

Reduce the raw video to the useful reconstruction subset.

### Build

- candidate frame extraction
- blur/sharpness scoring
- duplicate removal
- spacing heuristics
- selected frame manifest

### Deliverables

- selected keyframes saved to disk
- selection metadata saved in manifest

### Exit criteria

- a roughly 10-minute video can be reduced to a manageable keyframe set

---

## Phase 4: Modal Integration Foundation

Priority: `P0`

### Goal

Establish the local-to-Modal execution boundary.

### Build

- Modal app structure
- worker invocation helpers
- file staging conventions
- artifact return conventions
- stage-level error handling

### Deliverables

- local orchestrator can invoke a Modal stage and receive a result

### Exit criteria

- one test stage runs remotely and writes output back into the job folder

---

## Phase 5: Exact Reconstruction Baseline

Priority: `P0`

### Goal

Make the first true 3D output work.

### Build

- reconstruction stage contract
- `COLMAP` integration
- sparse reconstruction
- dense point cloud or mesh
- `Open3D` post-processing

### Deliverables

- exact reconstruction artifacts
- reconstruction logs and metadata

### Exit criteria

- one good drone video produces a usable 3D artifact end-to-end

### Important note

Do not start generative work before this phase is stable.

---

## Phase 6: Root Output Packaging

Priority: `P0`

### Goal

Make final outputs appear cleanly in the root output folder.

### Build

- final export folder layout
- copy/package logic
- summary manifest

### Deliverables

- `outputs/<job_id>/` contains clean deliverables

### Exit criteria

- a user can run the script and easily find the final outputs afterward

---

## Phase 7: Semantic Object Detection

Priority: `P1`

### Goal

Add object-level scene understanding.

### Build

- semantic detection worker
- 3D object metadata schema
- cuboid/proxy estimation
- class confidence metadata

### Deliverables

- `objects.json`
- object provenance metadata

### Exit criteria

- at least a small class set works well enough on demo data

---

## Phase 8: Confidence and Scene Graph

Priority: `P1`

### Goal

Add explainability and structure.

### Build

- confidence metadata generation
- scene graph generation
- provenance tags

### Deliverables

- `confidence.json`
- `scene_graph.json`

### Exit criteria

- outputs clearly distinguish observed, enhanced, and inferred content

---

## Phase 9: Depth Enhancement

Priority: `P1`

### Goal

Improve weak geometry without changing the basic architecture.

### Build

- depth worker
- fusion or enhancement step
- depth-assisted provenance markers

### Deliverables

- enhanced geometry outputs
- depth-related metadata

### Exit criteria

- depth enhancement improves at least one strong demo case

---

## Phase 10: Generative Reconstruction

Priority: `P1`

### Goal

Add the second flagship mode on top of the exact baseline.

### Build

- ambiguity detection
- asset library mapping
- inferred object insertion
- separate generative scene package

### Deliverables

- `generative_scene.*`
- inferred object metadata

### Exit criteria

- exact and generative outputs are both available and clearly separated

---

## Phase 11: Hardening and Performance

Priority: `P1`

### Goal

Make the backend pipeline reliable enough for repeated demo runs.

### Build

- better logs
- better failure messages
- optional keep/delete intermediates behavior
- frame count controls
- stage timing summaries

### Deliverables

- stable repeatable runs
- clearer debugging artifacts

### Exit criteria

- the team can run the same demo path without manual cleanup or guessing

---

## Phase 12: Advanced Improvements

Priority: `P2`

### Candidate work

- metric scale estimation
- multiple export formats
- LOD generation
- fuller asset provenance
- richer semantic ontology
- full on-prem worker replacement for Modal

---

## 5. What to Build First, Without Debate

If you want the shortest practical order, build exactly this:

1. local file/folder contract
2. CLI entry script
3. manifest and logs
4. one Modal test stage
5. keyframe selection
6. exact reconstruction
7. root output packaging

Only after that should we spend real time on:

- semantics
- confidence
- depth enhancement
- generative completion

---

## 6. Suggested Parallelization

Once the file contract is fixed, work can split like this:

- Track A: local orchestrator and manifests
- Track B: Modal worker scaffolding
- Track C: reconstruction pipeline
- Track D: semantic and generative schemas

Keep one person responsible for stage contracts and artifact naming so the parts keep fitting together.

---

## 7. Final Recommendation

The right mindset now is:

- first make it runnable
- then make it reconstruct
- then make it structured
- then make it smart

That order will keep us moving fast without building unstable layers on top of an unfinished core.

