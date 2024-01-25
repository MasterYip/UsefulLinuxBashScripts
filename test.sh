# Fetch script dir using dirname cmd
script_dir="$(dirname "$0")"
echo "$script_dir/config.sh"
source $script_dir/config.sh

echo $PASSWORD