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

# Set Home folder shortcut to Ctrl+E
python3 "$MODIFY_SCRIPT" "home" "<Control>e"

echo "Basic shortcuts configured successfully."