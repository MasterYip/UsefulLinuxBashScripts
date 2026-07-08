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


def _get_entity(api, args: argparse.Namespace) -> str:
    """Return the entity from --entity flag or the logged-in default."""
    if args.entity:
        return args.entity
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


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(api, args: argparse.Namespace) -> None:
    """List artifacts in a project."""
    entity = args.entity or _get_entity(api, args)
    project_name = args.project
    artifact_type = args.type

    print(f"=== Artifacts in {entity}/{project_name} ===")

    try:
        artifact_types = api.artifact_types(
            project_name, entity_name=entity,
        )
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
                for art in coll.versions():
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
    entity = args.entity or _get_entity(api, args)

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
        at = api.artifact_type(artifact_type_name, project=args.project, entity=entity)
    except Exception as exc:
        print(f"Error: artifact type '{artifact_type_name}' not found: {exc}", file=sys.stderr)
        sys.exit(1)

    versions_to_delete = []

    for coll in at.collections():
        if coll.name != artifact_name:
            continue
        for art in coll.versions():
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
    entity = args.entity or _get_entity(api, args)

    try:
        artifact_types = api.artifact_types(args.project, entity_name=entity)
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
                for art in coll.versions():
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
    entity = args.entity or _get_entity(api, args)
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.older_than)

    try:
        artifact_types = api.artifact_types(args.project, entity_name=entity)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    to_delete: list = []

    for at in artifact_types:
        if args.type and at.name != args.type:
            continue

        try:
            for coll in at.collections():
                for art in coll.versions():
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


def cmd_nuke(api, args: argparse.Namespace) -> None:
    """Delete ALL artifacts in a project. Requires --force."""
    entity = args.entity or _get_entity(api, args)

    if not args.force:
        print(
            "Error: this deletes ALL artifacts in the project. Use --force to proceed.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        artifact_types = api.artifact_types(args.project, entity_name=entity)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    all_versions = []
    for at in artifact_types:
        try:
            for c in at.collections():
                for art in c.versions():
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
    """Show storage usage summary for a project."""
    entity = args.entity or _get_entity(api, args)

    try:
        artifact_types = api.artifact_types(args.project, entity_name=entity)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    grand_total_size = 0
    grand_total_count = 0
    per_type: list[tuple[str, int, int]] = []  # (type_name, count, total_bytes)

    for at in artifact_types:
        type_count = 0
        type_size = 0
        collections_seen = 0
        try:
            for coll in at.collections():
                collections_seen += 1
                for art in coll.versions():
                    type_count += 1
                    type_size += getattr(art, "size", 0) or 0
        except Exception as exc:
            print(f"  Skipping type '{at.name}': {exc}", file=sys.stderr)
            continue

        if type_count:
            per_type.append((at.name, type_count, type_size))
            grand_total_count += type_count
            grand_total_size += type_size

    print(f"\n=== Storage Usage for {entity}/{args.project} ===\n")
    print(f"{'Type':<30} {'Versions':>10} {'Size':>12}")
    print("-" * 54)
    for type_name, count, size in sorted(per_type, key=lambda x: x[2], reverse=True):
        print(f"{type_name:<30} {count:>10} {_human_bytes(size):>12}")
    print("-" * 54)
    print(f"{'TOTAL':<30} {grand_total_count:>10} {_human_bytes(grand_total_size):>12}")
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

    # ---- usage ----
    p_usage = sub.add_parser("usage", help="Show storage usage summary for a project")
    p_usage.add_argument("--project", "-p", required=True, help="Project name")

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

    command_map = {
        "list": cmd_list,
        "delete": cmd_delete,
        "cleanup": cmd_cleanup,
        "cleanup-age": cmd_cleanup_age,
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
