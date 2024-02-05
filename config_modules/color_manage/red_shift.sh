#!/bin/bash
script_dir="$(dirname "$0")"
source $script_dir/../util_lib.sh

install_package redshift
set_custom_shortcut RedShiftEnable "redshift -o 12000" "<Primary><Super>x"
set_custom_shortcut RedShiftEnable "redshift -x" "<Primary><Super>z"