# !/bin/bash
export PASSWORD=0
export PRJ_ROOT="$(pwd)"

case "$(uname -m)" in
	x86_64|amd64) export PLATFORM=amd64 ;;
	aarch64|arm64) export PLATFORM=aarch64 ;;
	*) echo "Unsupported architecture: $(uname -m)" >&2; return 1 2>/dev/null || exit 1 ;;
esac