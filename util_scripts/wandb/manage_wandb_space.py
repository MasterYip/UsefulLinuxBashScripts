#!/usr/bin/env python3
"""
WandB Server Space Management Script
=====================================

Manage wandb server space — list, inspect, and delete artifacts to release
remote storage. Also handles local wandb cache/log cleanup.

Requirements: pip install wandb

Usage:
  # List all artifacts in a project
  ./manage_wandb_space.py list --entity my-org --project my-project

  # List only a specific artifact type
  ./manage_wandb_space.py list --entity my-org --project my-project --type dataset

  # Show artifact sizes (slower — fetches each artifact manifest)
  ./manage_wandb_space.py list --entity my-org --project my-project --sizes

  # Delete a specific artifact version
  ./manage_wandb_space.py delete --entity my-org --project my-project \\
      --name my-dataset --version v3

  # Delete an artifact by alias
  ./manage_wandb_space.py delete --entity my-org --project my-project \\
      --name my-dataset --alias latest

  # Delete ALL versions of a given artifact name
  ./manage_wandb_space.py delete --entity my-org --project my-project \\
      --name my-dataset --all

  # Keep the latest N versions of each artifact type, delete the rest (dry-run first!)
  ./manage_wandb_space.py cleanup --entity my-org --project my-project --keep 3 --dry-run

  # Really delete old versions
  ./manage_wandb_space.py cleanup --entity my-org --project my-project --keep 3

  # Only clean up a specific artifact type
  ./manage_wandb_space.py cleanup --entity my-org --project my-project \\
      --keep 5 --type dataset

  # Delete artifacts older than N days
  ./manage_wandb_space.py cleanup-age --entity my-org --project my-project \\
      --older-than 90 --dry-run

  # Delete EVERYTHING in a project (requires --force)
  ./manage_wandb_space.py nuke --entity my-org --project my-project --force

  # Show storage summary for a project
  ./manage_wandb_space.py usage --entity my-org --project my-project

  # Clean local wandb cache & logs
  ./manage_wandb_space.py clean-local

  # Clean local cache more aggressively (include wandb/ dir in cwd)
  ./manage_wandb_space.py clean-local --aggressive
"""

import argparse
import collections
import fnmatch
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_wandb():
    """Ensure wandb is installed and the user is logged in."""
    try:
        import wandb  # noqa: F811
    except ImportError:
        print("Error: wandb is not installed. Run:  pip install wandb", file=sys.stderr)
        sys.exit(1)

    try:
        wandb.Api().viewer  # triggers auth check
    except wandb.errors.AuthenticationError:
        print(
            "Error: not logged in to wandb. Run:  wandb login",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:
        print(f"Warning: could not verify wandb login ({exc})", file=sys.stderr)


def _resolve_entity(api, cli_entity: Optional[str]) -> str:
    """Return the effective entity: CLI flag wins, else API default."""
    if cli_entity:
        return cli_entity
    # api.default_entity is the canonical way (wandb SDK ≥0.12)
    try:
        return api.default_entity
    except AttributeError:
        pass
    # Fallback: extract from the viewer User object
    try:
        viewer = api.viewer
        if hasattr(viewer, "entity"):
            return viewer.entity
    except Exception:
        pass
    print("Error: could not determine wandb entity. Use --entity to specify it.", file=sys.stderr)
    sys.exit(1)




def _human_bytes(n: int) -> str:
    """Return a human-readable byte size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _age_str(dt: datetime) -> str:
    """Human-readable age, e.g. '3d ago', '90d ago'."""
    delta = datetime.now(timezone.utc) - dt
    days = delta.days
    if days == 0:
        return "today"
    if days < 7:
        return f"{days}d ago"
    if days < 60:
        return f"{days // 7}w ago"
    if days < 365:
        return f"{days // 30}mo ago"
    return f"{days // 365}y ago"


def _parse_size(s: str) -> int:
    """Parse a human-readable size string like '10MB', '1.5GB' into bytes."""
    s = s.strip().upper()
    multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    for suffix, mult in sorted(multipliers.items(), key=lambda x: len(x[0]), reverse=True):
        if s.endswith(suffix):
            try:
                return int(float(s[: -len(suffix)]) * mult)
            except ValueError:
                pass
    # No suffix — try as raw bytes
    try:
        return int(s)
    except ValueError:
        pass
    print(f"Warning: could not parse size '{s}', treating as 0", file=sys.stderr)
    return 0


def _run_created(run) -> Optional[datetime]:
    """Extract created_at from a run as a timezone-aware datetime, or None."""
    created = getattr(run, "created_at", None)
    if created is None:
        return None
    if isinstance(created, datetime):
        return created
    try:
        return datetime.fromisoformat(str(created).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(api, args: argparse.Namespace) -> None:
    """List artifacts in a project."""
    entity = args._entity
    project_name = args.project
    artifact_type = args.type

    print(f"=== Artifacts in {entity}/{project_name} ===")

    try:
        artifact_types = api.artifact_types(args.project)
    except Exception as exc:
        print(f"Error listing artifact types: {exc}", file=sys.stderr)
        sys.exit(1)

    total_count = 0
    total_size = 0

    for at in artifact_types:
        if artifact_type and at.name != artifact_type:
            continue

        type_size = 0
        type_count = 0
        print(f"\n{'─' * 60}")
        print(f"  Type: {at.name}")

        try:
            for coll in at.collections():
                for art in coll.artifacts():
                    type_count += 1
                    size = getattr(art, "size", 0) or 0
                    type_size += size

                    created = (
                        datetime.fromisoformat(art.created_at.replace("Z", "+00:00"))
                        if getattr(art, "created_at", None)
                        else None
                    )
                    age = _age_str(created) if created else "unknown"

                    aliases = (
                        ", ".join(a for a in getattr(art, "aliases", []) or [])
                        or "(none)"
                    )

                    if args.sizes:
                        print(
                            f"    {art.name}:v{art.version}  "
                            f"[{_human_bytes(size):>8}]  "
                            f"aliases: {aliases}  ({age})"
                        )
                    else:
                        print(
                            f"    {art.name}:v{art.version}  "
                            f"aliases: {aliases}  ({age})"
                        )
        except Exception as exc:
            print(f"    (error enumerating: {exc})", file=sys.stderr)

        if type_count:
            size_str = _human_bytes(type_size) if args.sizes else "? B"
            print(f"  ── {type_count} versions, ~{size_str} total ──")
            total_count += type_count
            total_size += type_size

    print(f"\nTotal: {total_count} artifact versions", end="")
    if args.sizes:
        print(f", ~{_human_bytes(total_size)}", end="")
    print()


def cmd_delete(api, args: argparse.Namespace) -> None:
    """Delete specific artifact versions."""
    entity = args._entity

    if args.all:
        # Delete every version of the named artifact
        try:
            artifact_type_name, artifact_name = _resolve_artifact_name(args.name)
        except ValueError:
            print(
                "Error: --name should be <type>/<name> or just <name> when --type is given",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        artifact_type_name = args.type
        artifact_name = args.name

    if not artifact_type_name:
        print(
            "Error: --type is required (or use <type>/<name> with --name)",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        at = api.artifact_type(artifact_type_name, project=args.project)
    except Exception as exc:
        print(f"Error: artifact type '{artifact_type_name}' not found: {exc}", file=sys.stderr)
        sys.exit(1)

    versions_to_delete = []

    for coll in at.collections():
        if coll.name != artifact_name:
            continue
        for art in coll.artifacts():
            versions_to_delete.append(art)

    if not versions_to_delete:
        print(f"No versions found for {artifact_type_name}/{artifact_name}")
        sys.exit(0)

    if args.version:
        versions_to_delete = [v for v in versions_to_delete if f"v{args.version}" == f"v{v.version}"]
        if not versions_to_delete:
            print(f"Version v{args.version} not found")
            sys.exit(1)

    if args.alias:
        versions_to_delete = [v for v in versions_to_delete if args.alias in (v.aliases or [])]
        if not versions_to_delete:
            print(f"No version with alias '{args.alias}' found")
            sys.exit(1)

    if not versions_to_delete:
        print("No matching versions found.")
        sys.exit(0)

    print(f"Will delete {len(versions_to_delete)} version(s):")
    for v in versions_to_delete:
        aliases = ", ".join(v.aliases) if v.aliases else "(none)"
        size = _human_bytes(getattr(v, "size", 0) or 0)
        print(f"  {v.name}:v{v.version}  ({size})  aliases: {aliases}")

    if args.dry_run:
        print("\n[Dry-run] No changes made.")
        return

    confirm = input(f"\nType 'yes' to confirm deletion: ")
    if confirm != "yes":
        print("Aborted.")
        return

    for v in versions_to_delete:
        print(f"  Deleting {v.name}:v{v.version} ...", end=" ", flush=True)
        try:
            v.delete()
            print("done")
        except Exception as exc:
            print(f"failed: {exc}")

    print("Done.")


def cmd_cleanup(api, args: argparse.Namespace) -> None:
    """Keep the latest N versions of each artifact, delete the rest."""
    entity = args._entity

    try:
        artifact_types = api.artifact_types(args.project)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    to_delete: list = []

    for at in artifact_types:
        if args.type and at.name != args.type:
            continue

        # Group versions by collection (artifact name)
        grouped = collections.defaultdict(list)
        try:
            for coll in at.collections():
                for art in coll.artifacts():
                    grouped[coll.name].append(art)
        except Exception as exc:
            print(f"  Skipping type '{at.name}': {exc}", file=sys.stderr)
            continue

        for art_name, versions in grouped.items():
            if len(versions) <= args.keep:
                continue

            # Sort by created_at descending, keep newest N
            def _sort_key(a):
                created = getattr(a, "created_at", None)
                if created:
                    return datetime.fromisoformat(created.replace("Z", "+00:00"))
                return datetime.min.replace(tzinfo=timezone.utc)

            versions.sort(key=_sort_key, reverse=True)
            keep = versions[: args.keep]
            remove = versions[args.keep :]

            keep_ids = {f"{v.name}:v{v.version}" for v in keep}
            to_delete.extend(remove)

            print(f"\n{at.name}/{art_name}: {len(versions)} versions → keep {len(keep)}, delete {len(remove)}")
            for v in keep:
                size = _human_bytes(getattr(v, "size", 0) or 0)
                print(f"  KEEP  {v.name}:v{v.version}  ({size})")
            for v in remove:
                size = _human_bytes(getattr(v, "size", 0) or 0)
                print(f"  DEL   {v.name}:v{v.version}  ({size})")

    if not to_delete:
        print("\nNothing to delete.")
        return

    total_size = sum(getattr(v, "size", 0) or 0 for v in to_delete)
    print(f"\n{len(to_delete)} version(s) to delete (~{_human_bytes(total_size)})")

    if args.dry_run:
        print("[Dry-run] No changes made.")
        return

    confirm = input("Type 'yes' to confirm deletion: ")
    if confirm != "yes":
        print("Aborted.")
        return

    for v in to_delete:
        print(f"  Deleting {v.name}:v{v.version} ...", end=" ", flush=True)
        try:
            v.delete()
            print("done")
        except Exception as exc:
            print(f"failed: {exc}")

    print("Done.")


def cmd_cleanup_age(api, args: argparse.Namespace) -> None:
    """Delete artifacts older than N days."""
    entity = args._entity
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.older_than)

    try:
        artifact_types = api.artifact_types(args.project)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    to_delete: list = []

    for at in artifact_types:
        if args.type and at.name != args.type:
            continue

        try:
            for coll in at.collections():
                for art in coll.artifacts():
                    created_str = getattr(art, "created_at", None)
                    if not created_str:
                        continue
                    created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    if created < cutoff:
                        to_delete.append(art)
        except Exception as exc:
            print(f"  Skipping type '{at.name}': {exc}", file=sys.stderr)
            continue

    if not to_delete:
        print(f"No artifacts older than {args.older_than} days.")
        return

    print(f"Found {len(to_delete)} artifact(s) older than {args.older_than} days:")
    for v in to_delete:
        created_str = getattr(v, "created_at", "unknown")
        size = _human_bytes(getattr(v, "size", 0) or 0)
        print(f"  {v.name}:v{v.version}  ({size})  created: {created_str}")

    if args.dry_run:
        print("\n[Dry-run] No changes made.")
        return

    confirm = input("\nType 'yes' to confirm deletion: ")
    if confirm != "yes":
        print("Aborted.")
        return

    for v in to_delete:
        print(f"  Deleting {v.name}:v{v.version} ...", end=" ", flush=True)
        try:
            v.delete()
            print("done")
        except Exception as exc:
            print(f"failed: {exc}")

    print("Done.")


def cmd_run_files(api, args: argparse.Namespace) -> None:
    """List files stored inside runs — checkpoints, logs, code, etc."""
    entity = args._entity
    path = f"{entity}/{args.project}"

    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=args.older_than)
        if args.older_than
        else None
    )

    print(f"=== Run files in {path} ===", flush=True)
    if args.pattern:
        print(f"  Pattern: {args.pattern}")
    if cutoff:
        print(f"  Older than: {args.older_than} days")

    total_size = 0
    total_files = 0
    runs_scanned = 0
    runs_with_matches = 0
    per_pattern: dict[str, tuple[int, int]] = collections.defaultdict(
        lambda: (0, 0)
    )  # ext → (count, total_size)

    for run in api.runs(path):
        runs_scanned += 1

        if cutoff:
            created = _run_created(run)
            if created and created >= cutoff:
                continue

        matched = []
        try:
            for f in run.files():
                sz = f.size or 0
                if args.pattern and not fnmatch.fnmatch(f.name, args.pattern):
                    continue
                if args.min_size and sz < args.min_size:
                    continue
                matched.append(f)
                total_size += sz
                total_files += 1
                # Track by extension
                ext = os.path.splitext(f.name)[1].lower() or "(noext)"
                cnt, sz_sum = per_pattern[ext]
                per_pattern[ext] = (cnt + 1, sz_sum + sz)
        except Exception as exc:
            if runs_scanned <= 3:
                print(f"  (skipping run {run.name}: {exc})", file=sys.stderr)
            continue

        if matched:
            runs_with_matches += 1
            age = (_age_str(rc) if (rc := _run_created(run)) else "?")
            match_size = sum(f.size or 0 for f in matched)
            print(
                f"\n  [{runs_scanned}] {run.name}  "
                f"({getattr(run, 'state', '?')}, {age})  "
                f"{len(matched)} file(s) → {_human_bytes(match_size)}"
            )
            for f in matched[:5]:
                print(f"    {f.name}  {_human_bytes(f.size or 0)}")
            if len(matched) > 5:
                more = len(matched) - 5
                more_sz = sum(f.size or 0 for f in matched[5:])
                print(f"    ... and {more} more ({_human_bytes(more_sz)})")

        if args.limit and runs_scanned >= args.limit:
            print(f"\n  (stopped after --limit {args.limit} runs)")
            break

        if runs_scanned % 50 == 0:
            print(
                f"  [{runs_scanned} runs scanned, {total_files} files matched, "
                f"{_human_bytes(total_size)} so far]",
                flush=True,
            )

    print(f"\n{'─' * 60}")
    print(
        f"Runs scanned: {runs_scanned}  |  "
        f"Runs with matches: {runs_with_matches}  |  "
        f"Files matched: {total_files}  |  "
        f"Total: {_human_bytes(total_size)}"
    )

    if per_pattern:
        print("\nBy file type:")
        for ext, (cnt, sz) in sorted(
            per_pattern.items(), key=lambda x: x[1][1], reverse=True
        ):
            print(f"  {ext:<12} {cnt:>6} files  {_human_bytes(sz):>12}")


def cmd_clean_run_files(api, args: argparse.Namespace) -> None:
    """Delete run files matching a pattern (e.g. *.ckpt)."""
    entity = args._entity
    path = f"{entity}/{args.project}"

    if not args.pattern:
        print(
            "Error: --pattern is required (e.g. '*.ckpt', '*.pt')",
            file=sys.stderr,
        )
        sys.exit(1)

    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=args.older_than)
        if args.older_than
        else None
    )

    print(f"=== Clean run files in {path} ===")
    print(f"  Pattern: {args.pattern}")
    if cutoff:
        print(f"  Older than: {args.older_than} days")
    print("  Scanning runs ...", flush=True)

    to_delete: list[tuple] = []  # (run_name, file_obj)
    runs_scanned = 0

    for run in api.runs(path):
        runs_scanned += 1

        if cutoff:
            created = _run_created(run)
            if created is None or created >= cutoff:
                continue

        try:
            for f in run.files():
                if fnmatch.fnmatch(f.name, args.pattern):
                    to_delete.append((run, f))
        except Exception:
            continue

        if runs_scanned % 50 == 0:
            print(
                f"  [{runs_scanned} runs scanned, {len(to_delete)} files queued]",
                flush=True,
            )

    if not to_delete:
        print(f"\nNo files matching '{args.pattern}' found.")
        if cutoff:
            print("(Try without --older-than to see all matching files.)")
        return

    total_size = sum(f.size or 0 for _, f in to_delete)
    runs_affected = len({r.id for r, _ in to_delete})

    print(f"\nFound {len(to_delete)} file(s) across {runs_affected} run(s)")
    print(f"Total: ~{_human_bytes(total_size)}\n")

    # Show preview
    for run, f in to_delete[:25]:
        name = getattr(run, "name", "?")
        age = (_age_str(rc) if (rc := _run_created(run)) else "?")
        print(
            f"  {name}/{f.name}  {_human_bytes(f.size or 0)}  ({age})"
        )
    if len(to_delete) > 25:
        print(f"  ... and {len(to_delete) - 25} more")

    if args.dry_run:
        print("\n[Dry-run] No changes made.")
        return

    confirm = input(f"\nType 'yes' to permanently delete these {len(to_delete)} files: ")
    if confirm != "yes":
        print("Aborted.")
        return

    deleted = 0
    failed = 0
    for run, f in to_delete:
        name = getattr(run, "name", "?")
        print(f"  Deleting {name}/{f.name} ...", end=" ", flush=True)
        try:
            f.delete()
            print("done")
            deleted += 1
        except Exception as exc:
            print(f"failed: {exc}")
            failed += 1

    print(f"\nDone.  Deleted: {deleted}, Failed: {failed}")


def cmd_nuke(api, args: argparse.Namespace) -> None:
    """Delete ALL artifacts in a project. Requires --force."""
    entity = args._entity

    if not args.force:
        print(
            "Error: this deletes ALL artifacts in the project. Use --force to proceed.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        artifact_types = api.artifact_types(args.project)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    all_versions = []
    for at in artifact_types:
        try:
            for c in at.collections():
                for art in c.artifacts():
                    all_versions.append(art)
        except Exception as exc:
            print(f"  Skipping type '{at.name}': {exc}", file=sys.stderr)

    if not all_versions:
        print("No artifacts in this project.")
        return

    total_size = sum(getattr(v, "size", 0) or 0 for v in all_versions)
    print(
        f"WARNING: About to delete ALL {len(all_versions)} artifact versions "
        f"(~{_human_bytes(total_size)}) from {entity}/{args.project}!"
    )
    confirm = input("Type the full project name to confirm: ")
    if confirm != args.project:
        print("Aborted.")
        return

    for v in all_versions:
        print(f"  Deleting {v.name}:v{v.version} ...", end=" ", flush=True)
        try:
            v.delete()
            print("done")
        except Exception as exc:
            print(f"failed: {exc}")

    print("Done.")


def cmd_usage(api, args: argparse.Namespace) -> None:
    """Show storage usage summary for a project — artifacts + run files."""
    entity = args._entity
    path = f"{entity}/{args.project}"

    # ------------------------------------------------------------------
    # 1. Artifact storage (wandb-history, wandb-events, datasets, models...)
    # ------------------------------------------------------------------
    try:
        artifact_types = api.artifact_types(args.project)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    artifact_total_size = 0
    artifact_total_count = 0
    per_type: list[tuple[str, int, int]] = []  # (type_name, count, total_bytes)

    for at in artifact_types:
        type_count = 0
        type_size = 0
        try:
            for coll in at.collections():
                for art in coll.artifacts():
                    type_count += 1
                    type_size += getattr(art, "size", 0) or 0
        except Exception as exc:
            print(f"  Skipping type '{at.name}': {exc}", file=sys.stderr)
            continue

        if type_count:
            per_type.append((at.name, type_count, type_size))
            artifact_total_count += type_count
            artifact_total_size += type_size

    # ------------------------------------------------------------------
    # 2. Run-file storage (checkpoints, logs, saved files, code snapshots...)
    # ------------------------------------------------------------------
    run_files_size = 0
    run_files_count = 0
    runs_scanned = 0
    runs_skipped = 0
    per_run_ext: dict[str, tuple[int, int]] = collections.defaultdict(
        lambda: (0, 0)
    )  # ext → (count, total_bytes)

    if not args.artifacts_only:
        print(f"Scanning runs in {path} ...", end=" ", flush=True)
        for run in api.runs(path):
            runs_scanned += 1
            try:
                for f in run.files():
                    sz = f.size or 0
                    run_files_size += sz
                    run_files_count += 1
                    ext = os.path.splitext(f.name)[1].lower() or "(noext)"
                    cnt, sz_sum = per_run_ext[ext]
                    per_run_ext[ext] = (cnt + 1, sz_sum + sz)
            except Exception:
                runs_skipped += 1
                continue

            if runs_scanned % 50 == 0:
                print(
                    f"\n  [{runs_scanned} runs scanned, "
                    f"{run_files_count} files, "
                    f"{_human_bytes(run_files_size)} so far]",
                    end=" ",
                    flush=True,
                )

        print(f"done ({runs_scanned} runs", end="")
        if runs_skipped:
            print(f", {runs_skipped} skipped)", end="")
        print(")")

    # ------------------------------------------------------------------
    # 3. Print combined report
    # ------------------------------------------------------------------
    print(f"\n=== Storage Usage for {entity}/{args.project} ===\n")

    # -- Artifact section --
    print(f"{'Artifact Type':<30} {'Versions':>10} {'Size':>12}")
    print("-" * 54)
    for type_name, count, size in sorted(per_type, key=lambda x: x[2], reverse=True):
        print(f"{type_name:<30} {count:>10} {_human_bytes(size):>12}")
    print("-" * 54)
    print(f"{'Artifacts subtotal':<30} {artifact_total_count:>10} {_human_bytes(artifact_total_size):>12}")
    print()

    # -- Run files section --
    if not args.artifacts_only and per_run_ext:
        print(f"{'Run File Type':<30} {'Files':>10} {'Size':>12}")
        print("-" * 54)
        for ext, (cnt, sz) in sorted(
            per_run_ext.items(), key=lambda x: x[1][1], reverse=True
        ):
            print(f"{ext:<30} {cnt:>10} {_human_bytes(sz):>12}")
        print("-" * 54)
        print(f"{'Run files subtotal':<30} {run_files_count:>10} {_human_bytes(run_files_size):>12}")
        print()
    elif not args.artifacts_only:
        print("(No run files found)\n")

    # -- Grand total --
    total_all_count = artifact_total_count + run_files_count
    total_all_size = artifact_total_size + run_files_size
    print(f"{'TOTAL (combined)':<30} {total_all_count:>10} {_human_bytes(total_all_size):>12}")
    print()

    # Show which entity we're operating as
    print(f"WandB entity: {entity}")


def cmd_clean_local(args: argparse.Namespace) -> None:
    """Clean local wandb cache, logs, and temporary files."""
    wandb_dir = Path.home() / ".wandb"
    if not wandb_dir.exists():
        print("No ~/.wandb directory found.")
        return

    artifacts_cache = wandb_dir / "artifacts"
    logs_dir = wandb_dir / "logs"

    cleaned_size = 0
    removed_dirs = 0

    for path, label in [(artifacts_cache, "artifact cache"), (logs_dir, "old logs")]:
        if path.exists():
            size_before = _dir_size(path)
            if args.aggressive:
                shutil.rmtree(path, ignore_errors=True)
                path.mkdir(parents=True, exist_ok=True)
                if size_before:
                    cleaned_size += size_before
                    removed_dirs += 1
                    print(f"Cleared {label}: {_human_bytes(size_before)}")
            else:
                # Clean only old subdirectories (older than 7 days)
                cutoff = datetime.now() - timedelta(days=7)
                for subdir in path.iterdir():
                    if subdir.is_dir():
                        mtime = datetime.fromtimestamp(subdir.stat().st_mtime)
                        if mtime < cutoff:
                            s = _dir_size(subdir)
                            shutil.rmtree(subdir, ignore_errors=True)
                            if s:
                                cleaned_size += s
                                removed_dirs += 1
                                print(f"  Removed old {label} entry: {subdir.name} ({_human_bytes(s)})")

    # Also clean ./wandb/ in CWD
    cwd_wandb = Path.cwd() / "wandb"
    if args.aggressive and cwd_wandb.exists():
        s = _dir_size(cwd_wandb)
        shutil.rmtree(cwd_wandb, ignore_errors=True)
        if s:
            cleaned_size += s
            removed_dirs += 1
            print(f"Removed ./wandb/ ({_human_bytes(s)})")

    if cleaned_size:
        print(f"\nCleaned {removed_dirs} item(s), freed ~{_human_bytes(cleaned_size)}")
    else:
        print("Nothing to clean.")


def _dir_size(path: Path) -> int:
    """Total size of all files under path, in bytes. Returns 0 on error."""
    total = 0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    except OSError:
        pass
    return total


def _resolve_artifact_name(name: str) -> tuple[str, str]:
    """Resolve 'type/name' or just 'name' into (type, name)."""
    if "/" in name:
        parts = name.split("/", 1)
        return parts[0], parts[1]
    raise ValueError("name must be in <type>/<name> format when --all is used")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage wandb server space — list and delete artifacts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Global flags
    parser.add_argument(
        "--entity", "-e",
        help="WandB entity (user or team). Defaults to your logged-in entity.",
    )

    sub = parser.add_subparsers(dest="command", help="Subcommand")

    # ---- list ----
    p_list = sub.add_parser("list", help="List artifacts in a project")
    p_list.add_argument("--project", "-p", required=True, help="Project name")
    p_list.add_argument("--type", "-t", help="Filter by artifact type")
    p_list.add_argument("--sizes", action="store_true", help="Show artifact sizes (slower)")

    # ---- delete ----
    p_del = sub.add_parser("delete", help="Delete specific artifact versions")
    p_del.add_argument("--project", "-p", required=True, help="Project name")
    p_del.add_argument("--name", "-n", required=True, help="Artifact name (or <type>/<name>)")
    p_del.add_argument("--type", "-t", help="Artifact type (if not included in --name)")
    p_del.add_argument("--version", "-v", help="Delete a specific version")
    p_del.add_argument("--alias", "-a", help="Delete the version with this alias")
    p_del.add_argument("--all", action="store_true", help="Delete ALL versions of this artifact")
    p_del.add_argument("--dry-run", action="store_true", help="Preview only, don't delete")

    # ---- cleanup (keep latest N) ----
    p_clean = sub.add_parser("cleanup", help="Keep latest N versions of each artifact, delete the rest")
    p_clean.add_argument("--project", "-p", required=True, help="Project name")
    p_clean.add_argument("--keep", "-k", type=int, required=True, help="Number of latest versions to keep")
    p_clean.add_argument("--type", "-t", help="Only clean a specific artifact type")
    p_clean.add_argument("--dry-run", action="store_true", help="Preview only, don't delete")

    # ---- cleanup-age ----
    p_age = sub.add_parser("cleanup-age", help="Delete artifacts older than N days")
    p_age.add_argument("--project", "-p", required=True, help="Project name")
    p_age.add_argument("--older-than", "-d", type=int, required=True, help="Delete artifacts older than this many days")
    p_age.add_argument("--type", "-t", help="Only clean a specific artifact type")
    p_age.add_argument("--dry-run", action="store_true", help="Preview only, don't delete")

    # ---- nuke ----
    p_nuke = sub.add_parser("nuke", help="Delete ALL artifacts in a project")
    p_nuke.add_argument("--project", "-p", required=True, help="Project name")
    p_nuke.add_argument("--force", action="store_true", help="Required to proceed")

    # ---- run-files ----
    p_rf = sub.add_parser("run-files", help="List files stored inside runs (checkpoints, logs, etc.)")
    p_rf.add_argument("--project", "-p", required=True, help="Project name")
    p_rf.add_argument("--pattern", help="Filename glob, e.g. '*.ckpt' or '*.pt'")
    p_rf.add_argument("--min-size", help="Minimum file size, e.g. '10MB'")
    p_rf.add_argument("--older-than", "-d", type=int, help="Only show runs older than N days")
    p_rf.add_argument("--limit", type=int, help="Max runs to scan (for testing)")

    # ---- clean-run-files ----
    p_crf = sub.add_parser("clean-run-files", help="Delete run files matching a pattern")
    p_crf.add_argument("--project", "-p", required=True, help="Project name")
    p_crf.add_argument("--pattern", required=True, help="Filename glob, e.g. '*.ckpt' or '*.pt'")
    p_crf.add_argument("--older-than", "-d", type=int, required=True, help="Only delete files from runs older than N days")
    p_crf.add_argument("--dry-run", action="store_true", help="Preview only, don't delete")

    # ---- usage ----
    p_usage = sub.add_parser("usage", help="Show storage usage summary for a project")
    p_usage.add_argument("--project", "-p", required=True, help="Project name")
    p_usage.add_argument("--artifacts-only", action="store_true", help="Skip scanning run files (faster, but misses checkpoints & saved files)")

    # ---- clean-local ----
    p_local = sub.add_parser("clean-local", help="Clean local wandb cache and logs")
    p_local.add_argument("--aggressive", action="store_true", help="Remove all cache including recent files and ./wandb/")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Commands that don't need the wandb API
    if args.command == "clean-local":
        cmd_clean_local(args)
        return

    # All other commands need wandb + login
    _check_wandb()

    import wandb as _wb

    api = _wb.Api()
    entity = _resolve_entity(api, args.entity)
    args._entity = entity  # stash for display in subcommands

    # Parse human-readable --min-size if provided (run-files only)
    if getattr(args, "min_size", None):
        args.min_size = _parse_size(args.min_size)

    # Note: wandb API always uses the logged-in entity.  To query another
    # entity's artifacts, set WANDB_ENTITY before running:
    #   WANDB_ENTITY=<other-entity> ./manage_wandb_space.py usage -p <project>

    command_map = {
        "list": cmd_list,
        "delete": cmd_delete,
        "cleanup": cmd_cleanup,
        "cleanup-age": cmd_cleanup_age,
        "run-files": cmd_run_files,
        "clean-run-files": cmd_clean_run_files,
        "nuke": cmd_nuke,
        "usage": cmd_usage,
    }

    fn = command_map.get(args.command)
    if fn:
        fn(api, args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
