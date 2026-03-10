#!/bin/bash

# This script installs OpenClaw dependencies and sets up the environment

set -e

# Update package lists and install prerequisites
sudo apt update
sudo apt install -y git curl build-essential python3 python3-pip

# Clone the OpenClaw repository
git clone https://github.com/openclaw/openclaw.git ~/openclaw

# Change to the OpenClaw directory
cd ~/openclaw

# Run the OpenClaw bootstrap process
pip3 install -r requirements.txt

# Inform the user
echo "Installation complete. To start OpenClaw, navigate to ~/openclaw and follow the README instructions."