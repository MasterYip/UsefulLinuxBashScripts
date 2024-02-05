#!/bin/bash
# script_dir="$(dirname "$0")"
# source $script_dir/../util_lib.sh
source $PRJ_ROOT/config_lib/utils/install_package.bash
install_package xcalib
# set_custom_shortcut ColorInvert "xcalib -invert -alter" "<Primary><Super>c"
python3 $PRJ_ROOT/config_lib/shortcut_config/set_custom_shortcut.py ColorInvert "xcalib -invert -alter" "<Primary><Super>c"
