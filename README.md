# LinuxAutoCfg

Auto configuration modules & useful automation scripts for Linux.

## Repo Guide

### auto_config_lib

`auto_config_lib` is a library for auto configuration utilities, including:

| Module            | Description                                 |
| ----------------- | ------------------------------------------- |
| `shortcut_config` | A utility to create shortcuts for commands. |
| `utils`           | A collection of useful utilities.           |

### config_modules

User defined config modules that set up specific functions/features.

| Module          | Description                                    |
| --------------- | ---------------------------------------------- |
| `basic`         | Install basic software and set shortcuts.      |
| `coding_toolsets`| Install VS Code, GitHub CLI, and Conda.       |
| `color_manage`  | Configure redshift and color inversion.        |
| `input_sharing` | Set up Synergy for sharing keyboard/mouse.     |
| `network_setup` | Configure SSH and network related settings.    |
| `remote_ctrl`   | Install ToDesk and NoMachine remote desktop.   |
| `ros_setup`     | Install and configure ROS Noetic.             |

## Get Started

1. Update your password in `settings.bash`, and source it.

2. Source corresponding bash script in `config_modules` to apply configs to Ubuntu.

> Or, you can edit `setup.bash` to apply customized configurations.

## Startup Applications

1. Clash

```bash
sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0 | echo 0 | sudo -S sysctl -w | kernel.apparmor_restrict_unprivileged_userns=0 | ~/Software/"Clash for Windows-0.20.23-x64-linux/cfw"
```

## Trouble Shooting

1. Ubuntu 24.04 'The SUID sandbox helper binary was found'

```bash
sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0
echo 0 | sudo -S sysctl -w kernel.apparmor_restrict_unprivileged_userns=0
```

2. Repeatitive GPU Reported

nvidia installer: `/etc/vulkan/icd.d/` 
distribution’s driver package: `/usr/share/vulkan/icd.d` (disable this one)

```bash
sudo apt remove mesa-vulkan-drivers
```