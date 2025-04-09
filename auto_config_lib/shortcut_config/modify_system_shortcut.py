import subprocess
import sys
import json

def list_system_shortcuts():
    """
    List all system shortcuts in GNOME.
    
    :return: Dictionary of all system shortcuts with their current values.
    """
    cmd = "gsettings list-recursively org.gnome.desktop.wm.keybindings"
    try:
        result = subprocess.run(["/bin/bash", "-c", cmd], 
                               capture_output=True, 
                               text=True, 
                               check=True)
        shortcuts = {}
        for line in result.stdout.splitlines():
            parts = line.strip().split(' ', 2)
            if len(parts) == 3:
                _, action, value = parts
                shortcuts[action] = value
        return shortcuts
    except subprocess.CalledProcessError as e:
        print(f"Failed to list shortcuts: {e}")
        return {}

def print_system_shortcuts():
    """
    Print all system shortcuts in a readable format.
    """
    shortcuts = list_system_shortcuts()
    if shortcuts:
        print("System Shortcuts:")
        print("================")
        for action, value in sorted(shortcuts.items()):
            print(f"{action}: {value}")
    else:
        print("No shortcuts found or error occurred.")

def modify_system_shortcut(action, new_shortcut):
    """
    Modify a system shortcut in GNOME.

    :param action: The action name of the system shortcut (e.g., 'close', 'switch-applications').
    :param new_shortcut: The new shortcut key combination (e.g., '<Super>Q').
    """
    key = f"org.gnome.desktop.wm.keybindings {action}"
    cmd = f"gsettings set {key} \"['{new_shortcut}']\""
    try:
        subprocess.run(["/bin/bash", "-c", cmd], check=True)
        print(f"Shortcut for '{action}' updated to '{new_shortcut}'.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to update shortcut for '{action}': {e}")

# Example usage:
# modify_system_shortcut('close', '<Super>Q')
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        print_system_shortcuts()
    else:
        modify_system_shortcut(*sys.argv[1:])