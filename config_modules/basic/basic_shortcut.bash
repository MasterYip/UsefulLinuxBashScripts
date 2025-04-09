#!/bin/bash

# Basic shortcut configurations
echo "Setting up basic shortcuts..."

# Path to the shortcut modification script
MODIFY_SCRIPT="$PRJ_ROOT/auto_config_lib/shortcut_config/modify_system_shortcut.py"

# Check if we just want to list shortcuts
if [ "$1" = "list" ]; then
    echo "Listing all system shortcuts..."
    python3 "$MODIFY_SCRIPT" list
    exit 0
fi

# Set Home folder shortcut to Super+E
echo "Setting Home folder shortcut to Super+E..."
python3 "$MODIFY_SCRIPT" "home" "<Super>e" "org.gnome.settings-daemon.plugins.media-keys"

# Set area-screenshot-clip shortcut to Alt+Q
echo "Setting area-screenshot-clip shortcut to Alt+Q..."
python3 "$MODIFY_SCRIPT" "area-screenshot-clip" "<Alt>q" "org.gnome.settings-daemon.plugins.media-keys"

# Set workspace navigation shortcuts
echo "Setting workspace navigation shortcuts..."
# Switch to workspace down/up
python3 "$MODIFY_SCRIPT" "switch-to-workspace-down" "<Control><Super>Right" "org.gnome.desktop.wm.keybindings"
python3 "$MODIFY_SCRIPT" "switch-to-workspace-up" "<Control><Super>Left" "org.gnome.desktop.wm.keybindings"

# Move window to workspace down/up
python3 "$MODIFY_SCRIPT" "move-to-workspace-down" "<Control><Shift><Super>Right" "org.gnome.desktop.wm.keybindings"
python3 "$MODIFY_SCRIPT" "move-to-workspace-up" "<Control><Shift><Super>Left" "org.gnome.desktop.wm.keybindings"

echo "All shortcuts configured successfully."