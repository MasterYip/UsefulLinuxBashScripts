#!/bin/bash
script_dir="$(dirname "$0")"
source $script_dir/../util_lib.sh
install_package xcalib
set_shortcut ColorInvert "xcalib -invert -alter" "<Primary><Super>c"
