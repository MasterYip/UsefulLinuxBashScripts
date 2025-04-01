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

| Module            | Description                                 |
| ----------------- | ------------------------------------------- |
| `basic_software`  | Install basic software.                     |
| `coding_toolsets` | Install coding toolsets.                    |
| `color_manage`    | Manage color settings.                      |
| `input_sharing`   | Set up input sharing.                       |
| `network_setup`   | Set up network.                             |
| `remote_ctrl`     | Set up remote control.                      |

## Get Started

1.Update your passward in `settings.bash`, and source it.

2.Source corresponding bash script in `config_modules` to apply configs to Ubuntu.

> Or, you can edit `setup.bash` to apply custommed configurations.
