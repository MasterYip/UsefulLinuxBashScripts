# !/bin/bash

PASSWORD="0"

# Fetch script dir using dirname cmd
# script_dir="$(dirname "$0")"
# source $script_dir/config.sh

function install_package(){
    # $1: package name
    # $2: package installation command
    if ! command -v $1 > /dev/null; then
        echo "$1 is not installed. Installing..."
        echo $PASSWORD | sudo -S apt install $1
    else
        echo "$1 is already installed."
    fi
}

# function set_shortcut(){
#     # $1: shortcut name
#     # $2: shortcut command
#     # $3: shortcut binding
#     echo "Setting system shortcut $1"
#     # 列出已存在的自定义快捷键
#     existing_custom_keys=$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings)
#     # num_existing_custom_keys=$(grep -o "," <<< "$existing_custom_keys" | wc -l)
#     num_existing_custom_keys=$(grep -o "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings" <<< "$existing_custom_keys" | wc -l)
#     echo "Number of existing custom keybindings: $num_existing_custom_keys"

#     gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom2/ name "$1"
#     gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom2/ command "$2"
#     gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom2/ binding "$3"

#     echo "Done! Shortcut is set to $3."
# }

function set_shortcut(){
    # 定义要使用的键和字符串
    key="org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
    subkey1="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"
    subkey1=${subkey1%?}":"
    firstname="custom"

    # 获取当前自定义快捷键列表
    array_str=$(gsettings get "$key")

    # 如果数组为空，移除注释提示
    command_result=${array_str//@as/}
    current=($(eval "$command_result"))

    # 确保新的快捷键不是重复的
    n=1
    while true; do
        new="$item_s$firstname$n/"
        if [[ " ${current[@]} " =~ " $new " ]]; then
            ((n++))
        else
            break
        fi
    done

    # 将新的快捷键添加到列表中
    current+=("$new")

    # 创建快捷键，设置名称、命令和快捷键
    cmd0="gsettings set $key '$(printf "%s\n" "${current[@]}")'"
    cmd1="gsettings set $key:$subkey1$new name '$1'"
    cmd2="gsettings set $key:$subkey1$new command '$2'"
    cmd3="gsettings set $key:$subkey1$new binding '$3'"

    # 执行命令
    for cmd in "$cmd0" "$cmd1" "$cmd2" "$cmd3"; do
        eval "$cmd"
    done
}
