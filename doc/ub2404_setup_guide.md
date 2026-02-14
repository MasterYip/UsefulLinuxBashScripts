# Ubuntu 24.04 Setup Guide

**Install NVIDIA Driver**

```bash
sudo apt update
sudo apt install nvidia-driver-580
# for RTX 5090, use nvidia-driver-580-open
```

**Perform basic setup**

```bash
source ./settings.bash
source ./setup.bash
# Coding toolsets
source ./config_modules/coding_toolsets/vscode.bash
source ./config_modules/coding_toolsets/github_cli.bash
source ./config_modules/coding_toolsets/conda_forge.bash
```

**Perform basic configuration**

Set up Git configuration
```bash
git config --global user.name MasterYip
git config --global user.email raymon-yip@qq.com
gh auth login
# Follow the prompts to authenticate with GitHub CLI
```

Proxychains
```bash
code /etc/proxychains.conf
# Add the following line at the end of the file:
socks4 127.0.0.1 7890
https  127.0.0.1 7890
http   127.0.0.1 7890
```

