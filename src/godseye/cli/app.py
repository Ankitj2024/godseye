"""God's Eye command-line interface.

Commands:

* ``run``     - execute the pipeline on a video (default command)
* ``resume``  - continue or rerun stages of an existing job
* ``stages``  - show the pipeline for a mode
* ``inspect`` - summarise a job manifest
* ``doctor``  - verify local deps and the Modal compute plane
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from godseye import __version__
from godseye.config import PipelineConfig, load_config
from godseye.errors import GodsEyeError
from godseye.orchestrator import ManifestError, ManifestStore, PipelineRunner, prepare_job
from godseye.orchestrator.job import JobPaths
from godseye.pipeline.registry import build_pipeline
from godseye.schemas.enums import JobStatus, PipelineMode, StageName, StageStatus
from godseye.utils.fs import human_bytes
from godseye.utils.logging import console, setup_logging

app = typer.Typer(
    name="godseye",
    help="Turn one drone video into a 3D world model.",
    no_args_is_help=True,
    add_completion=False,
)

_STATUS_STYLE = {
    StageStatus.COMPLETED: "green",
    StageStatus.RUNNING: "yellow",
    StageStatus.FAILED: "red",
    StageStatus.SKIPPED: "dim",
    StageStatus.PENDING: "dim",
}


def _parse_force(values: list[str] | None) -> set[StageName]:
    if not values:
        return set()
    forced: set[StageName] = set()
    valid = {s.value for s in StageName}
    for raw in values:
        for token in raw.split(","):
            name = token.strip()
            if not name:
                continue
            if name not in valid:
                raise typer.BadParameter(
                    f"Unknown stage '{name}'. Valid stages: {', '.join(sorted(valid))}"
                )
            forced.add(StageName(name))
    return forced


def _build_config(
    output_dir: Optional[Path],
    log_level: str,
    max_keyframes: Optional[int],
    dense: Optional[bool],
) -> PipelineConfig:
    config = load_config(log_level=log_level)
    if output_dir is not None:
        # An absolute --output-dir wins naturally: Path("/root") / "/abs" == "/abs".
        config.outputs_dirname = str(output_dir)
    if max_keyframes is not None:
        config.keyframes.target_count = max_keyframes
        config.keyframes.max_count = max(max_keyframes, config.keyframes.min_count)
    if dense is not None:
        config.reconstruction.run_dense = dense
    return config


def _execute(config: PipelineConfig, prepared, force: set[StageName]) -> int:
    stages = build_pipeline(prepared.mode)
    runner = PipelineRunner(
        config=config,
        mode=prepared.mode,
        paths=prepared.paths,
        store=prepared.store,
        stages=stages,
        force_stages=force,
    )
    report = runner.run()
    _print_report(report, prepared.paths)
    return 0 if report.status == JobStatus.COMPLETED else 1


def _print_report(report, paths: JobPaths) -> None:
    table = Table(title=f"Job {report.manifest.job_id}", show_lines=False)
    table.add_column("Stage")
    table.add_column("Target")
    table.add_column("Status")
    table.add_column("Duration", justify="right")

    for record in report.manifest.stages.values():
        duration = f"{record.duration_seconds:.1f}s" if record.duration_seconds else "-"
        style = _STATUS_STYLE.get(record.status, "")
        table.add_row(
            record.name.value,
            record.target.value,
            f"[{style}]{record.status.value}[/{style}]" if style else record.status.value,
            duration,
        )

    console.print(table)

    status_style = {
        JobStatus.COMPLETED: "bold green",
        JobStatus.PARTIAL: "bold yellow",
        JobStatus.FAILED: "bold red",
    }.get(report.status, "bold")

    lines = [f"[{status_style}]{report.status.value.upper()}[/{status_style}]"]
    lines.append(f"Outputs:  {paths.output_dir}")
    lines.append(f"Work dir: {paths.job_dir}")
    lines.append(f"Logs:     {paths.pipeline_log_path}")

    for record in report.manifest.stages.values():
        if record.status == StageStatus.FAILED and record.error:
            lines.append("")
            lines.append(
                f"[red]{record.name.value} failed ({record.error.origin.value}):[/red] "
                f"{record.error.message}"
            )
            if record.error.failed_command:
                lines.append(f"[dim]command:[/dim] {record.error.failed_command}")

    if report.status != JobStatus.COMPLETED:
        lines.append("")
        lines.append(
            f"[dim]Resume with:[/dim] python run_pipeline.py resume {report.manifest.job_id}"
        )

    console.print(Panel("\n".join(lines), title="Result", expand=False))


@app.command()
def run(
    video: Path = typer.Option(..., "--video", "-v", help="Path to the drone video."),
    mode: PipelineMode = typer.Option(
        PipelineMode.EXACT, "--mode", "-m", help="Reconstruction mode."
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", "-o", help="Where deliverables are written (default: ./outputs)."
    ),
    max_keyframes: Optional[int] = typer.Option(
        None, "--max-keyframes", help="Target number of keyframes to send to COLMAP."
    ),
    dense: Optional[bool] = typer.Option(
        None, "--dense/--no-dense", help="Run COLMAP dense stereo (default: on)."
    ),
    force: Optional[list[str]] = typer.Option(
        None, "--force-stage", help="Stage(s) to rerun even if completed. Repeatable."
    ),
    no_hash: bool = typer.Option(
        False, "--no-input-hash", help="Skip hashing the input video (faster for huge files)."
    ),
    log_level: str = typer.Option("INFO", "--log-level", help="Console log level."),
) -> None:
    """Run the full pipeline on a video."""
    config = _build_config(output_dir, log_level, max_keyframes, dense)
    forced = _parse_force(force)

    try:
        prepared = prepare_job(
            config, video=video, mode=mode, hash_input=not no_hash
        )
    except GodsEyeError as exc:
        console.print(f"[red]Input error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    setup_logging(config.log_level, prepared.paths.pipeline_log_path)
    console.print(
        Panel(
            f"job:   {prepared.paths.job_id}\n"
            f"video: {video}\n"
            f"mode:  {mode.value}",
            title="God's Eye",
            expand=False,
        )
    )

    raise typer.Exit(code=_execute(config, prepared, forced))


@app.command()
def resume(
    job_id: str = typer.Argument(..., help="Existing job id under work/."),
    mode: Optional[PipelineMode] = typer.Option(
        None, "--mode", "-m", help="Override the recorded mode."
    ),
    force: Optional[list[str]] = typer.Option(
        None, "--force-stage", help="Stage(s) to rerun even if completed. Repeatable."
    ),
    dense: Optional[bool] = typer.Option(None, "--dense/--no-dense", help="Run dense stereo."),
    log_level: str = typer.Option("INFO", "--log-level", help="Console log level."),
) -> None:
    """Continue an existing job, reusing completed stages."""
    config = _build_config(None, log_level, None, dense)
    forced = _parse_force(force)

    try:
        prepared = prepare_job(config, job_id=job_id, mode=mode or PipelineMode.EXACT)
    except GodsEyeError as exc:
        console.print(f"[red]Cannot resume:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    setup_logging(config.log_level, prepared.paths.pipeline_log_path)
    raise typer.Exit(code=_execute(config, prepared, forced))


@app.command()
def stages(
    mode: PipelineMode = typer.Option(PipelineMode.EXACT, "--mode", "-m"),
) -> None:
    """Show the stage order for a mode, including unimplemented stages."""
    table = Table(title=f"Pipeline ({mode.value})")
    table.add_column("#", justify="right")
    table.add_column("Stage")
    table.add_column("Runs on")
    table.add_column("Built")
    table.add_column("Description")

    for index, stage in enumerate(build_pipeline(mode), start=1):
        built = "[green]yes[/green]" if stage.implemented else f"[dim]{stage.planned_phase}[/dim]"
        table.add_row(str(index), stage.name.value, stage.target.value, built, stage.description)

    console.print(table)


@app.command(name="inspect")
def inspect_job(
    job_id: str = typer.Argument(..., help="Job id under work/."),
) -> None:
    """Summarise a job's manifest."""
    config = load_config()
    paths = JobPaths(job_id=job_id, work_root=config.work_root, outputs_root=config.outputs_root)

    try:
        store = ManifestStore.load(paths)
    except ManifestError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc

    manifest = store.manifest
    video = manifest.video

    header = [
        f"status:   {manifest.status.value}",
        f"mode:     {manifest.mode.value}",
        f"created:  {manifest.created_at.isoformat()}",
        f"duration: {manifest.total_duration_seconds():.1f}s",
    ]
    if video:
        header.append(f"video:    {video.source_path}")
        header.append(
            f"          {human_bytes(video.size_bytes)}, "
            f"{video.duration_seconds or 0:.1f}s @ {video.fps or 0:.2f} fps"
        )
    console.print(Panel("\n".join(header), title=f"Job {job_id}", expand=False))

    table = Table(title="Stages")
    table.add_column("Stage")
    table.add_column("Status")
    table.add_column("Duration", justify="right")
    table.add_column("Key metrics")

    for record in manifest.stages.values():
        style = _STATUS_STYLE.get(record.status, "")
        duration = f"{record.duration_seconds:.1f}s" if record.duration_seconds else "-"
        metrics = ", ".join(
            f"{k}={v}"
            for k, v in list(record.metrics.items())[:3]
            if not isinstance(v, (dict, list))
        )
        table.add_row(
            record.name.value,
            f"[{style}]{record.status.value}[/{style}]" if style else record.status.value,
            duration,
            metrics or "-",
        )
    console.print(table)

    if manifest.artifacts:
        artifacts = Table(title=f"Artifacts ({len(manifest.artifacts)})")
        artifacts.add_column("Kind")
        artifacts.add_column("Path")
        artifacts.add_column("Size", justify="right")
        for record in list(manifest.artifacts.values())[:25]:
            artifacts.add_row(
                record.kind.value, record.relative_path, human_bytes(record.size_bytes)
            )
        console.print(artifacts)


@app.command()
def doctor(
    remote: bool = typer.Option(
        True, "--remote/--local-only", help="Also check the Modal compute plane."
    ),
) -> None:
    """Check that the local and remote halves of the system are usable."""
    config = load_config()
    setup_logging(config.log_level)

    table = Table(title="God's Eye doctor")
    table.add_column("Check")
    table.add_column("Result")
    table.add_column("Detail")

    ok = True

    table.add_row("version", "[green]ok[/green]", __version__)

    for module, purpose in (
        ("cv2", "frame extraction"),
        ("numpy", "keyframe scoring"),
        ("modal", "remote compute"),
    ):
        try:
            imported = __import__(module)
            version = getattr(imported, "__version__", "unknown")
            table.add_row(module, "[green]ok[/green]", f"{version} ({purpose})")
        except ImportError:
            ok = False
            table.add_row(module, "[red]missing[/red]", f"needed for {purpose}")

    for label, path in (
        ("work dir", config.work_root),
        ("outputs dir", config.outputs_root),
    ):
        exists = path.exists()
        table.add_row(label, "[green]ok[/green]" if exists else "[yellow]missing[/yellow]", str(path))

    if remote:
        from godseye.remote.transport import ModalTransport  # noqa: PLC0415

        transport = ModalTransport(config.modal, job_id="doctor")
        try:
            result = transport.ping()
            worker = result.get("worker", {})
            table.add_row(
                "modal app",
                "[green]ok[/green]",
                f"{config.modal.app_name} on {worker.get('hostname', 'unknown')}",
            )
            metrics = result.get("metrics", {})
            volume_ok = metrics.get("volume_mounted") and metrics.get("volume_writable")
            table.add_row(
                "modal volume",
                "[green]ok[/green]" if volume_ok else "[red]failed[/red]",
                config.modal.volume_name,
            )
            if not volume_ok:
                ok = False
        except GodsEyeError as exc:
            ok = False
            table.add_row("modal app", "[red]failed[/red]", str(exc).splitlines()[0])
            console.print(table)
            console.print(
                Panel(str(exc), title="Modal check failed", border_style="red", expand=False)
            )
            raise typer.Exit(code=1) from exc

    console.print(table)
    if not ok:
        raise typer.Exit(code=1)


@app.command(name="view")
def view_cmd(
    job_id: Optional[str] = typer.Argument(None, help="Job ID to visualize (defaults to latest)."),
    port: int = typer.Option(8000, "--port", "-p", help="Port to run local 3D viewer server on."),
) -> None:
    """Launch the interactive 3D Scene Explorer in your default browser."""
    import http.server
    import socketserver
    import webbrowser

    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    outputs_dir = repo_root / "outputs"

    if not job_id:
        if outputs_dir.is_dir():
            jobs = sorted(
                [d for d in outputs_dir.iterdir() if d.is_dir() and not d.name.startswith(".")],
                key=lambda d: d.stat().st_mtime,
                reverse=True,
            )
            if jobs:
                job_id = jobs[0].name

    if not job_id:
        console.print("[red]No completed jobs found in outputs/[/red]")
        raise typer.Exit(code=1)

    socketserver.TCPServer.allow_reuse_address = True
    active_port = port
    try:
        httpd = socketserver.TCPServer(("", active_port), http.server.SimpleHTTPRequestHandler)
    except OSError:
        active_port = 8080
        httpd = socketserver.TCPServer(("", active_port), http.server.SimpleHTTPRequestHandler)

    url = f"http://localhost:{active_port}/viewer/?job={job_id}"
    console.print(
        Panel(
            f"[bold green]God's Eye 3D Scene Explorer[/bold green]\n\n"
            f"[dim]Job:[/dim]     [cyan]{job_id}[/cyan]\n"
            f"[dim]Serving:[/dim] [link={url}]{url}[/link]\n\n"
            f"[dim]Press Ctrl+C to close.[/dim]",
            border_style="cyan",
            expand=False,
        )
    )
    webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped viewer server.[/dim]")



def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
