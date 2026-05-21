from __future__ import annotations

from pathlib import Path
from typing import Annotated

import sqlite3
import typer

from charkive import __version__
from charkive import db, sanitorium, sandwich
from charkive import sanity as sanity_runner
from charkive.config import BrickCfg, ensure_config_near_root_written, load_config
from charkive.fire_codes import tier_weight
from charkive.paths import forbidden_brick_resolve

san_tp = typer.Typer(help="Operate on SANitorium objects.")


def cfg(path: Path | None):
    try:
        return load_config(path)
    except FileNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(4) from exc


def guard_bricks(configuration):
    if forbidden_brick_resolve(configuration.root, configuration.brick):
        typer.echo("Brick jail refuses this root — mount the export first.")
        raise typer.Exit(5)


def canon_tier(value: str | None) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    slug = value.strip().lower()
    if slug == "11":
        typer.secho('Did you mean --tier gigashyte? Numeric amps are backstage only.', fg=typer.colors.YELLOW)
        raise typer.Exit(2)
    lookup = {"1": "shyte", "5": "kiloshyte", "10": "megashyte"}
    slug = lookup.get(slug, slug)
    if slug not in {"shyte", "kiloshyte", "megashyte", "gigashyte"}:
        typer.echo(f"Unknown tier `{value}`", err=True)
        raise typer.Exit(3)
    return slug


def attach_scan(configuration):
    db_path = configuration.state_db_path()
    conn = sqlite3.connect(db_path)
    db.migrate(conn)
    snapshot = db.latest_scan(conn)
    if not snapshot or snapshot[1] is None:
        conn.close()
        typer.echo("Automatically performing `scan` to refresh metadata...")
        sanity_runner.run_scan(configuration, do_hash=False)
        conn = sqlite3.connect(db_path)
        db.migrate(conn)
        snapshot = db.latest_scan(conn)
        if not snapshot:
            conn.close()
            typer.echo("Still no scans after refresh.", err=True)
            raise typer.Exit(1)
    return conn, int(snapshot[0])


def mandate_tier_confirmation(tier_choice: str | None, *, dry_run: bool) -> None:
    if dry_run or not tier_choice:
        return
    if tier_choice == "megashyte":
        pledge = typer.prompt("Megashyers require acknowledgement (type MEGASHYTE)")
        if pledge.strip().upper() != "MEGASHYTE":
            raise typer.Exit(130)
    if tier_choice == "gigashyte":
        pledge = typer.prompt('Gigashyte requires THESE GO TO ELEVEN verbatim (quotes optional)')
        normalized = "".join(ch for ch in pledge.upper() if ch.isalnum())
        if normalized != "THESEGOTOELEVEN":
            raise typer.Exit(130)


_ConfigOpt = Annotated[
    Path | None,
    typer.Option("--config", exists=True, dir_okay=False, help=".charkive.yml path"),
]


app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=True,
)


@app.callback(invoke_without_command=True)
def dashboard(
    ctx: typer.Context,
    version_requested: Annotated[bool, typer.Option("--version", "-V")] = False,
):
    """Charkive top-level launcher."""
    if version_requested:
        typer.echo(f"Charkive {__version__}")
        typer.echo("All tiers go to 11.")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


@app.command()
def init(
    root: Annotated[
        Path,
        typer.Argument(help="SAN root mount (sandbox universe)"),
    ],
):
    rp = Path(root).expanduser()
    rp.mkdir(parents=True, exist_ok=True)
    resolved = rp.resolve(strict=False)
    if forbidden_brick_resolve(resolved, BrickCfg(enabled=True, forbidden_paths=("/SANDIEGO", "/bricks"))):
        typer.echo("Aborting brick path.")
        raise typer.Exit(5)
    config_path = ensure_config_near_root_written(resolved)
    typer.secho(f"{config_path}", fg=typer.colors.GREEN)


@app.command()
def scan(
    cfg_path: _ConfigOpt = None,
    hashed: Annotated[bool, typer.Option("--hash/--no-hash")] = False,
):
    configuration = cfg(cfg_path)
    guard_bricks(configuration)
    scan_id, stats = sanity_runner.run_scan(configuration, do_hash=hashed)
    typer.secho(f"Scan #{scan_id} committed", fg=typer.colors.GREEN)
    typer.echo(f"skipped symlinks={stats.symlink}, escapes={stats.outside_root}, dirs={stats.unreadable_dir}")


@app.command(name="sanity")
def sanity_summary(
    cfg_path: _ConfigOpt = None,
    tier_focus: Annotated[str | None, typer.Option("--tier")] = None,
):
    configuration = cfg(cfg_path)
    guard_bricks(configuration)
    try:
        alerts = sanity_runner.gluster_warnings(configuration)
        for memo in alerts:
            typer.echo(memo)
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(11) from exc
    tier_slug = canon_tier(tier_focus)
    conn, scan_id = attach_scan(configuration)
    summary_full = db.summary_for_scan(conn, scan_id)
    summary = sanity_runner.summarize_for_tier(summary_full, tier_slug)
    typer.echo(sandwich.render_report(configuration, summary))
    conn.close()


@app.command(name="sanitise")
def sanitise_cmd(
    cfg_path: _ConfigOpt = None,
    tier_pick: Annotated[str | None, typer.Option("--tier")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
):
    configuration = cfg(cfg_path)
    guard_bricks(configuration)
    try:
        for memo in sanity_runner.gluster_warnings(configuration):
            typer.echo(memo)
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(11) from exc
    slug = canon_tier(tier_pick)

    conn, scan_id = attach_scan(configuration)
    worst_tier = slug
    if worst_tier is None:
        rows = conn.execute(
            "SELECT DISTINCT tier FROM artifacts WHERE scan_id=? AND status='candidate' AND tier IS NOT NULL",
            (scan_id,),
        ).fetchall()
        names = [str(r[0]).lower() for r in rows if r[0]]
        if names:
            worst_tier = max(names, key=tier_weight)
    mandate_tier_confirmation(worst_tier, dry_run=dry_run)

    staged_rows, moved_bytes = sanitorium.sanitise_moves(
        configuration,
        conn,
        scan_id=scan_id,
        tier=slug,
        dry_run=dry_run,
    )
    label = slug or "all candidates"
    if dry_run:
        typer.echo(
            f"Dry sanitise[{label}] would move {len(staged_rows)} files (~{sandwich.fmt_bytes(moved_bytes)})."
        )
    else:
        typer.secho(f"Moved cohort into SANitorium ({label}).", fg=typer.colors.YELLOW)
        typer.echo(f"Manifest appended ({len(staged_rows)} restores tracked).")
    conn.close()


@app.command(name="status")
def snapshot_status(cfg_path: _ConfigOpt = None):
    configuration = cfg(cfg_path)
    db_path = configuration.state_db_path()
    conn = sqlite3.connect(db_path)
    db.migrate(conn)
    latest = db.latest_scan(conn)
    if not latest:
        typer.echo("No scans yet.")
        conn.close()
        return
    scan_id = int(latest[0])
    summary = db.summary_for_scan(conn, scan_id)
    conn.close()
    typer.echo(
        f"{configuration.root}: scan #{scan_id}; "
        f"{summary['grand']['files']} files / {sandwich.fmt_bytes(summary['grand']['bytes'])}; "
        f"candidate fluff {sandwich.fmt_bytes(summary['fluff']['bytes'])} "
        f"({summary['fluff']['files']:,})"
    )


@san_tp.command("ls")
def san_ls(cfg_path: _ConfigOpt = None):
    configuration = cfg(cfg_path)
    for line in sanitorium.list_contents(configuration):
        typer.echo(line)


@san_tp.command("purge")
def san_purge():
    typer.echo(sanitorium.purge_note())


@san_tp.command("quench")
def san_quench(
    specimen: Annotated[str, typer.Argument(help="Relative SANitorium path YEAR-W-xx/... ")],
    cfg_path: _ConfigOpt = None,
):
    sanitorium.quench(cfg(cfg_path), specimen)


app.add_typer(san_tp, name="sanitorium")


@app.command("sanitor")
def sanitor_placeholder():
    typer.echo("`charkive sanitor --daemon` Nigel amp not shipped in scaffold — cron/systemd wrappers only.")


@app.command()
def web(
    host: Annotated[str, typer.Option("--host", help="Bind address")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p", help="Listen port")] = 8080,
    cfg_path: Annotated[
        Path | None,
        typer.Option("--config", exists=True, dir_okay=False, help=".charkive.yml path"),
    ] = None,
):
    """Launch the Charkive web dashboard."""
    from charkive.webapp import start_web_server

    typer.secho(f"Charkive Web — http://{host}:{port}", fg=typer.colors.GREEN)
    typer.echo("Press Ctrl+C to stop.")
    start_web_server(host=host, port=port, config_path=str(cfg_path) if cfg_path else None)


def main() -> None:
    """Console script entry."""

    app()
