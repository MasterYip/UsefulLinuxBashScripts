# Ubuntu 24.04 Setup Guide

- Install NVIDIA Driver

```bash
sudo apt update
sudo apt install nvidia-driver-580
# for RTX 5090, use nvidia-driver-580-open
```

- Perform basic setup

```bash
source ./settings.bash
source ./setup.bash
# Coding toolsets
source ./config_modules/vscode.bash
source ./config_modules/github_cli.bash
source ./config_modules/conda_forge.bash
```

- Perform basic configuration

```bash
git config --global user.name MasterYip
git config --global user.email raymon-yip@qq.com
```
