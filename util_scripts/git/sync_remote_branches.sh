#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 <destination-remote> [source-remote]" >&2
  echo "Example: $0 backup origin" >&2
  exit 1
fi

destination_remote="$1"
source_remote="${2:-origin}"

git fetch "$source_remote" --prune

git for-each-ref --format='%(refname:short)' "refs/remotes/$source_remote" | while IFS= read -r refname; do
  branch_name="${refname#${source_remote}/}"

  if [[ "$branch_name" == "HEAD" || -z "$branch_name" ]]; then
    continue
  fi

  git push "$destination_remote" "refs/remotes/$source_remote/$branch_name:refs/heads/$branch_name"
done