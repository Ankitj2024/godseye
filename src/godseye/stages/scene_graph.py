"""Stage: scene graph generation (Local).

Ingests detected 3D semantic objects (objects.json) and spatial bounds, reasons
about topological and geometric relationships (above, near, contains, supports),
and generates a queryable scene graph document (scene_graph.json).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from godseye.pipeline.context import StageContext
from godseye.pipeline.stage import Stage, StageOutcome
from godseye.schemas.enums import ArtifactKind, ExecutionTarget, Provenance, StageName
from godseye.schemas.scene import (
    ObjectsDocument,
    SceneGraphDocument,
    SceneGraphEdge,
    SceneGraphNode,
)
from godseye.utils.fs import atomic_write_text, ensure_dir


class SceneGraphStage(Stage):
    name = StageName.SCENE_GRAPH
    target = ExecutionTarget.LOCAL
    description = "Scene graph nodes and spatial relationships from detected objects."

    def run(self, ctx: StageContext) -> StageOutcome:
        log = ctx.logger(self.name)
        paths = ctx.paths
        output_dir = ensure_dir(paths.scene_graph_dir)
        objects_path = paths.semantics_dir / "objects.json"

        objects_doc: ObjectsDocument | None = None
        if objects_path.exists():
            try:
                data = json.loads(objects_path.read_text(encoding="utf-8"))
                objects_doc = ObjectsDocument.model_validate(data)
            except Exception as exc:
                log.warning("Could not parse objects.json: %s", exc)

        if not objects_doc or not objects_doc.generated or not objects_doc.objects:
            log.info("No semantic objects available; emitting minimal scene graph")
            graph_doc = SceneGraphDocument(
                job_id=ctx.job_id,
                generated=False,
                reason="No semantic objects available from detection stage.",
            )
            out_file = output_dir / "scene_graph.json"
            atomic_write_text(out_file, graph_doc.model_dump_json(indent=2) + "\n")
            outcome = StageOutcome(
                metrics={"node_count": 0, "edge_count": 0, "generated": False},
                notes=["No objects to construct scene graph relationships from."],
            )
            outcome.add_artifact(out_file, ArtifactKind.METADATA, compute_hash=False)
            return outcome

        objects = objects_doc.objects
        log.info("Building scene graph from %d objects", len(objects))

        nodes: list[SceneGraphNode] = []
        edges: list[SceneGraphEdge] = []

        # 1. Environment context node
        terrain_node = SceneGraphNode(
            node_id="node_terrain",
            node_type="context",
            label="terrain",
            confidence=1.0,
            provenance=Provenance.OBSERVED,
            metadata={"description": "Ground plane / terrain surface"},
        )
        nodes.append(terrain_node)

        # 2. Object nodes
        for obj in objects:
            node = SceneGraphNode(
                node_id=f"node_{obj.object_id}",
                node_type="object",
                label=obj.object_class,
                object_id=obj.object_id,
                confidence=obj.confidence,
                provenance=obj.provenance,
                metadata={
                    "translation": obj.transform.translation.model_dump(),
                    "dimensions": obj.dimensions.model_dump(),
                    "supporting_frames_count": len(obj.supporting_frames),
                },
            )
            nodes.append(node)

            # Ground support edge
            edges.append(
                SceneGraphEdge(
                    edge_id=f"edge_support_{obj.object_id}",
                    source="node_terrain",
                    target=f"node_{obj.object_id}",
                    relationship="supports",
                    confidence=0.9,
                )
            )

        # 3. Pairwise spatial relationships
        edge_index = 0
        for i in range(len(objects)):
            for j in range(i + 1, len(objects)):
                a = objects[i]
                b = objects[j]

                ta = a.transform.translation
                tb = b.transform.translation
                da = a.dimensions
                db = b.dimensions

                dx = ta.x - tb.x
                dy = ta.y - tb.y
                dz = ta.z - tb.z

                dist_3d = math.sqrt(dx * dx + dy * dy + dz * dz)
                dist_xy = math.sqrt(dx * dx + dy * dy)

                # Proximity / adjacency: within combined footprint plus buffer
                reach = (da.x + da.y + db.x + db.y) / 4.0 + 3.0
                if dist_xy < reach:
                    conf = round(max(0.2, 1.0 - (dist_xy / reach)), 3)
                    edges.append(
                        SceneGraphEdge(
                            edge_id=f"edge_{edge_index:04d}_near",
                            source=f"node_{a.object_id}",
                            target=f"node_{b.object_id}",
                            relationship="near",
                            confidence=conf,
                        )
                    )
                    edge_index += 1

                # Vertical stacking / above
                if abs(dz) > 0.5 and dist_xy < max(da.x, da.y, db.x, db.y):
                    upper, lower = (a, b) if dz > 0 else (b, a)
                    edges.append(
                        SceneGraphEdge(
                            edge_id=f"edge_{edge_index:04d}_above",
                            source=f"node_{upper.object_id}",
                            target=f"node_{lower.object_id}",
                            relationship="above",
                            confidence=0.85,
                        )
                    )
                    edge_index += 1

        graph_doc = SceneGraphDocument(
            job_id=ctx.job_id,
            generated=True,
            reason=None,
            nodes=nodes,
            edges=edges,
        )

        out_file = output_dir / "scene_graph.json"
        atomic_write_text(out_file, graph_doc.model_dump_json(indent=2) + "\n")
        log.info("Wrote %s with %d nodes and %d edges", out_file.name, len(nodes), len(edges))

        outcome = StageOutcome(
            metrics={
                "node_count": len(nodes),
                "edge_count": len(edges),
                "generated": True,
            },
            notes=[f"Built scene graph with {len(nodes)} nodes and {len(edges)} spatial edges."],
        )
        outcome.add_artifact(out_file, ArtifactKind.METADATA, compute_hash=False)
        return outcome
