# !/bin/bash
# Fetch script dir using dirname cmd
script_dir="$(dirname "$0")"
source $script_dir/config.sh

function install_package(){
    # $1: package name
    # $2: package installation command
    if ! command -v $1 > /dev/null; then
        echo "$1 is not installed. Installing..."
        echo $PASSWORD | sudo apt install $1
    else
        echo "$1 is already installed."
    fi
}

function set_shortcut(){
    # $1: shortcut name
    # $2: shortcut command
    # $3: shortcut binding
    echo "Setting system shortcut $1"
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/ name "$1"
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/ command "$2"
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/ binding "$3"

    echo "Done! Shortcut is set to $3."
}
