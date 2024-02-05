#!/bin/bash
# script_dir="$(dirname "$0")"
# source $script_dir/../util_lib.sh
source $PRJ_ROOT/config_lib/utils/install_package.bash
install_package redshift
# set_custom_shortcut RedShiftEnable "redshift -o 12000" "<Primary><Super>x"
# set_custom_shortcut RedShiftDisable "redshift -x" "<Primary><Super>z"
python3 $PRJ_ROOT/config_lib/shortcut_config/set_custom_shortcut.py RedShiftEnable "redshift -O 3000" "<Primary><Super>x"
python3 $PRJ_ROOT/config_lib/shortcut_config/set_custom_shortcut.py RedShiftDisable "redshift -x" "<Primary><Super>z"