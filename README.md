# God's Eye

**God's Eye** is an advanced 3D Scene Explorer and reconstruction pipeline. It ingests standard monocular drone/aerial video and produces highly detailed, metrically accurate, semantically enriched 3D environments. 

The system uses a hybrid architecture: a local control plane orchestrates heavy GPU and computer vision workloads executed dynamically on [Modal](https://modal.com/).

---

## 🛠 Tech Stack

### Core Technologies
- **Python 3.11**: Primary language for both the local orchestrator and remote workers.
- **Modal**: Serverless GPU infrastructure (A10G, T4) used for accelerating all heavy computer vision and 3D processing tasks on-demand.
- **Pydantic**: Heavily utilized for strongly-typed configuration (`config.py`) and explicit contract schemas (`schemas/remote.py`) crossing the local/cloud boundary.

### 3D & Vision Modules
- **COLMAP**: Industry-standard Structure-from-Motion (SfM) and PatchMatch dense stereo fusion. Responsible for generating the foundational, metrically accurate point cloud and camera poses.
- **Open3D**: Point cloud processing, statistical outlier removal, KD-Tree color transfer, and Poisson surface reconstruction (meshing).
- **Hugging Face Transformers**: 
  - **Depth-Anything-V2**: Monocular depth estimation (aligned via least-squares to COLMAP's metric scale).
  - **OWLv2**: Zero-shot 2D object detection (projected into 3D world coordinates).
- **OpenCV**: Video decoding, frame extraction, and Laplacian variance (blur) detection.

---

## 🏗 System Architecture & Pipeline

The pipeline is modeled as a Directed Acyclic Graph (DAG) of **Stages**. Stages run either locally or remotely on Modal depending on compute requirements. Data flows seamlessly between local storage and Modal Volumes.

You can trigger the pipeline using:
```bash
python3 run_pipeline.py --video ./sample.mp4 --mode exact
```

### The Pipeline Stages

#### 1. Frame Extraction (Local, CPU)
- **Module**: `src/godseye/stages/frame_extraction.py`
- **What it does**: Decodes the input `.mp4` video using OpenCV and extracts evenly spaced candidate frames based on a configured FPS stride (default: 6.0 fps).

#### 2. Keyframe Selection (Local, CPU)
- **Module**: `src/godseye/stages/keyframe_selection.py`
- **What it does**: Scores candidate frames based on sharpness (Laplacian variance) and visual novelty. Filters out blurry or redundant frames to curate an optimal set of ~200 high-quality keyframes for 3D reconstruction.

#### 3. Exact Reconstruction (Modal, GPU: A10G)
- **Module**: `src/godseye/stages/reconstruction_exact.py` → `modal_app/reconstruction/worker.py`
- **What it does**: Uploads keyframes to Modal and executes **COLMAP**. 
  - Sparse reconstruction (SIFT feature extraction and matching) to determine camera poses.
  - Dense patch-match stereo to generate a high-density, metrically accurate point cloud.

#### 4. Geometry Post-Processing (Modal, GPU: A10G)
- **Module**: `src/godseye/stages/geometry_postprocess.py` → `modal_app/geometry/worker.py`
- **What it does**: Uses **Open3D** to clean and mesh the raw COLMAP point cloud. 
  - Applies statistical outlier removal.
  - Computes Poisson surface reconstruction (depth=12 for high fidelity).
  - Decimates the mesh to a target triangle count (1M) for performance.
  - **Vertex Color Transfer**: Projects sharp colors from the source point cloud back onto the Poisson mesh using a KD-Tree nearest-neighbor lookup.

#### 5. Depth Enhancement (Modal, GPU: A10G)
- **Module**: `src/godseye/stages/depth_enhancement.py` → `modal_app/depth/worker.py`
- **What it does**: Uses **Depth-Anything-V2** to estimate monocular depth for keyframes.
  - **Metric Alignment**: Projects known COLMAP 3D points into the camera frame and uses a least-squares solver to find the scale and shift required to anchor the monocular depth exactly to the COLMAP metric coordinate system.
  - Unprojects the aligned depth maps to create a dense, structure-enhancing point cloud for textureless regions (like flat roofs or roads).

#### 6. Semantic Detection (Modal, GPU: A10G)
- **Module**: `src/godseye/stages/semantic_detection.py` → `modal_app/semantics/worker.py`
- **What it does**: Uses **OWLv2** to detect objects (vehicles, buildings, trees) in 2D frames. It then intersects these 2D bounding boxes with the COLMAP 3D point cloud rays to estimate exact 3D world coordinates and dimensions, merging duplicates across frames into distinct 3D objects.

#### 7. Scene Graph Generation (Local, CPU)
- **Module**: `src/godseye/stages/scene_graph.py`
- **What it does**: Ingests the 3D objects and performs spatial reasoning. It calculates distance, adjacency ("near"), and vertical stacking ("above", "supports") to build a queryable, topological graph of the environment (`scene_graph.json`).

#### 8. Output Packaging (Local, CPU)
- **Module**: `src/godseye/stages/output_packaging.py`
- **What it does**: Downloads all final deliverables (GLB meshes, point clouds, JSON metadata, logs) from the Modal Volume and packages them neatly into a local `outputs/<job_id>` directory.

---

## 📁 Repository Structure

- `src/godseye/` — Local control plane. Contains configuration, schemas, pipeline orchestrator, and local stage definitions.
- `modal_app/` — Remote worker codebase. Contains the Docker image definitions, Volume mounts, and Python workers that execute on Modal GPUs.
- `viewer/` — Web-based UI (HTML/JS) for interacting with the generated 3D scenes and scene graphs.
- `outputs/` — Generated output artifacts for completed runs.
- `work/` — Temporary working directory for active pipeline runs.

## ⚙️ Configuration
The pipeline is highly tunable. Quality and performance defaults are located in `src/godseye/config.py`. Key levers include:
- `sample_fps` & `target_count`: Controls how many frames are sent to COLMAP.
- `dense_max_image_size`: Resolution of dense stereo (lower = faster, higher = sharper).
- `poisson_depth`: Resolution of the generated 3D surface mesh.
