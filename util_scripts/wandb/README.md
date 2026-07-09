# WandB Space Management

[manage_wandb_space.py](manage_wandb_space.py) — list, inspect, and delete wandb artifacts to release remote storage. Also handles local cache/log cleanup.

## Requirements

- Python 3.8+
- `wandb` (`pip install wandb`)
- Logged in via `wandb login`

## Quick Start

```bash
# See what's taking up space
./manage_wandb_space.py usage -p my-project

# List all artifacts (optionally with sizes)
./manage_wandb_space.py list -p my-project --sizes

# Preview what would be cleaned (keep latest 3 versions per artifact)
./manage_wandb_space.py cleanup -p my-project --keep 3 --dry-run

# Actually delete old versions
./manage_wandb_space.py cleanup -p my-project --keep 3

# Delete everything older than 90 days
./manage_wandb_space.py cleanup-age -p my-project --older-than 90 --dry-run

# Free local wandb cache
./manage_wandb_space.py clean-local
```

## Commands

### `usage` — Storage summary

```bash
./manage_wandb_space.py usage -p my-project [-e my-entity]
```

Prints a combined storage report that includes:

- **Artifacts** (wandb-history, datasets, models, etc.) — version count and size per type
- **Run files** (checkpoints, logs, `wandb.save()` files, code snapshots) — file count and size grouped by extension
- **Grand total** of both categories combined

This gives you the full picture of what's using your wandb storage — not just
the automatically-tracked artifact types.

```bash
# See which specific collections/artifacts are the largest within each type:
./manage_wandb_space.py usage -p my-project --verbose

# Same but show ALL collections (default is top 25 per type):
./manage_wandb_space.py usage -p my-project -v --show-all

# Skip the run-file scan (faster, for artifact-only stats):
./manage_wandb_space.py usage -p my-project --artifacts-only
```

The run-file scan iterates every run in the project and lists its stored files,
so it can be slow for projects with many runs. Progress is printed every 50 runs.

### `list` — Browse artifacts

```bash
./manage_wandb_space.py list -p my-project [-t dataset] [--sizes]
```

Lists every artifact version with aliases and creation age. `--sizes` fetches individual sizes (slower).

### `delete` — Delete specific versions

```bash
# Delete by version number
./manage_wandb_space.py delete -p my-project -n my-dataset -v 3

# Delete by alias (e.g. the "latest" tagged version)
./manage_wandb_space.py delete -p my-project -n my-dataset -a latest

# Delete every version of an artifact
./manage_wandb_space.py delete -p my-project -n my-dataset --all

# Use type/name shorthand
./manage_wandb_space.py delete -p my-project -n dataset/my-dataset --all

# Always preview first
./manage_wandb_space.py delete -p my-project -n my-dataset --all --dry-run
```

### `cleanup` — Keep latest N, delete the rest

```bash
# Keep the 3 newest versions of each artifact
./manage_wandb_space.py cleanup -p my-project --keep 3

# Only clean a specific artifact type
./manage_wandb_space.py cleanup -p my-project --keep 5 -t model
```

This is the primary space-saving workflow. It keeps recent versions so nothing breaks, while removing the accumulation of old checkpoints/datasets/models.

### `cleanup-age` — Delete by age

```bash
# Delete artifacts older than 90 days
./manage_wandb_space.py cleanup-age -p my-project --older-than 90
```

### `nuke` — Delete everything

```bash
./manage_wandb_space.py nuke -p my-project --force
```

Deletes **all** artifacts in the project. Prompts for the project name as confirmation.

### `run-files` — Find large run files (checkpoints, logs, etc.)

```bash
# List all checkpoint files in a project
./manage_wandb_space.py run-files -p my-project --pattern '*.ckpt'

# Find large files over 50 MB
./manage_wandb_space.py run-files -p my-project --min-size 50MB

# Only show files from runs older than 30 days
./manage_wandb_space.py run-files -p my-project --pattern '*.pt' -d 30

# Limit scan to first 10 runs (quick test)
./manage_wandb_space.py run-files -p my-project --pattern '*.ckpt' --limit 10
```

Lists files stored **inside runs** (not artifacts). This is where checkpoints, uploaded logs, and `wandb.save()` files live. Grouped by file extension with total sizes.

### `clean-run-files` — Delete run files by pattern

```bash
# Preview what would be deleted
./manage_wandb_space.py clean-run-files -p my-project --pattern '*.ckpt' -d 30 --dry-run

# Delete old checkpoints (runs older than 30 days)
./manage_wandb_space.py clean-run-files -p my-project --pattern '*.ckpt' -d 30
```

Deletes files matching a glob pattern from runs older than the specified number of days. **Always use `--dry-run` first.**

### `clean-local` — Free local disk space

```bash
# Remove cache entries older than 7 days (safe)
./manage_wandb_space.py clean-local

# Aggressive: clear everything including ./wandb/
./manage_wandb_space.py clean-local --aggressive
```

Cleans `~/.wandb/artifacts`, `~/.wandb/logs`, and (with `--aggressive`) `./wandb/` in the current directory.

## Common Workflows

### Routine cleanup (keep recent, discard old)

```bash
# 1. Check what you have
./manage_wandb_space.py usage -p my-project

# 2. Preview the cleanup
./manage_wandb_space.py cleanup -p my-project --keep 3 --dry-run

# 3. Execute
./manage_wandb_space.py cleanup -p my-project --keep 3
```

### Aggressive space reclamation

```bash
# Delete old artifacts, clean local cache
./manage_wandb_space.py cleanup-age -p my-project --older-than 60
./manage_wandb_space.py clean-local --aggressive
```

### Target a specific artifact

```bash
./manage_wandb_space.py list -p my-project -t model --sizes
./manage_wandb_space.py delete -p my-project -n old-experiment-model --all --dry-run
./manage_wandb_space.py delete -p my-project -n old-experiment-model --all
```

### Clean up old checkpoints (run files)

```bash
# 1. Audit: how many checkpoints and total size?
./manage_wandb_space.py run-files -p my-project --pattern '*.ckpt'

# 2. Preview deletion for runs older than 30 days
./manage_wandb_space.py clean-run-files -p my-project --pattern '*.ckpt' -d 30 --dry-run

# 3. Execute
./manage_wandb_space.py clean-run-files -p my-project --pattern '*.ckpt' -d 3
```
