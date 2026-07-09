#!/bin/bash
: "${PLATFORM:=$(uname -m)}"

case "$PLATFORM" in
	x86_64|amd64)
		PACKAGE_URL="https://download.nomachine.com/download/8.11/Linux/nomachine_8.11.3_4_amd64.deb"
		PACKAGE_FILE=/tmp/nomachine.deb
		;;
	aarch64|arm64)
		PACKAGE_URL="https://web9001.nomachine.com/download/9.7/Arm/nomachine_9.7.3_1_aarch.tar.gz"
		PACKAGE_FILE=/tmp/nomachine.deb
		;;
	*) echo "Unsupported architecture: $PLATFORM" >&2; exit 1 ;;
esac

wget -O "$PACKAGE_FILE" "$PACKAGE_URL"
echo "$PASSWORD" | sudo -S apt install "$PACKAGE_FILE"