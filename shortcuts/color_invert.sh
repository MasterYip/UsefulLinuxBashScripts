#!/bin/bash
script_dir="$(dirname "$0")"
source $script_dir/../util_lib.sh
install_package xcalib
# set_custom_shortcut ColorInvert "xcalib -invert -alter" "<Primary><Super>c"
python3 $script_dir/set_custom_shortcut.py ColorInvert "xcalib -invert -alter" "<Primary><Super>c"
