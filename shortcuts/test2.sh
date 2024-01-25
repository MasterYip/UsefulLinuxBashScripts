# Fetch script dir using dirname cmd
script_dir="$(dirname "$0")"
echo "$script_dir/../test.sh"
source $script_dir/../test.sh

echo $PASSWORD