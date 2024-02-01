#!/bin/bash
script_dir="$(dirname "$0")"
source $script_dir/../util_lib.sh

install_package redshift
# set_custom_shortcut RedShiftEnable "redshift -o 12000" "<Primary><Super>x"
# set_custom_shortcut RedShiftEnable "redshift -x" "<Primary><Super>z"
python3 $script_dir//set_custom_shortcut.py RedShiftEnable "redshift -O 2000" "<Primary><Super>x"
python3 $script_dir//set_custom_shortcut.py RedShiftDisable "redshift -x" "<Primary><Super>z"