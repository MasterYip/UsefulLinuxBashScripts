import subprocess
import sys
import json

def list_system_shortcuts():
    """
    List all system shortcuts in GNOME from all relevant schemas.
    
    :return: Dictionary of all system shortcuts with their current values.
    """
    # These are the main schemas that contain keyboard shortcuts in GNOME
    schemas = [
        "org.gnome.desktop.wm.keybindings",
        "org.gnome.settings-daemon.plugins.media-keys",
        "org.gnome.shell.keybindings",
        "org.gnome.mutter.keybindings"
    ]
    
    shortcuts = {}
    for schema in schemas:
        cmd = f"gsettings list-recursively {schema}"
        try:
            result = subprocess.run(["/bin/bash", "-c", cmd], 
                                  capture_output=True, 
                                  text=True, 
                                  check=True)
            for line in result.stdout.splitlines():
                parts = line.strip().split(' ', 2)
                if len(parts) == 3:
                    schema_name, action, value = parts
                    shortcuts[f"{schema_name} {action}"] = value
        except subprocess.CalledProcessError as e:
            print(f"Failed to list shortcuts for schema {schema}: {e}")
    
    return shortcuts

def print_system_shortcuts():
    """
    Print all system shortcuts in a readable format, grouped by schema.
    """
    shortcuts = list_system_shortcuts()
    if shortcuts:
        print("System Shortcuts:")
        print("================")
        
        # Group shortcuts by schema
        schemas = {}
        for key, value in shortcuts.items():
            schema, action = key.rsplit(' ', 1)
            if schema not in schemas:
                schemas[schema] = []
            schemas[schema].append((action, value))
        
        # Print shortcuts grouped by schema
        for schema, actions in sorted(schemas.items()):
            print(f"\n{schema}:")
            print("-" * len(schema) + ":")
            for action, value in sorted(actions):
                print(f"  {action}: {value}")
    else:
        print("No shortcuts found or error occurred.")

def modify_system_shortcut(action, new_shortcut, schema="org.gnome.desktop.wm.keybindings"):
    """
    Modify a system shortcut in GNOME.

    :param action: The action name of the system shortcut (e.g., 'close', 'switch-applications').
    :param new_shortcut: The new shortcut key combination (e.g., '<Super>Q').
    :param schema: The gsettings schema containing the shortcut (default: org.gnome.desktop.wm.keybindings).
    """
    key = f"{schema} {action}"
    cmd = f"gsettings set {key} \"['{new_shortcut}']\""
    try:
        subprocess.run(["/bin/bash", "-c", cmd], check=True)
        print(f"Shortcut for '{action}' in schema '{schema}' updated to '{new_shortcut}'.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to update shortcut for '{action}': {e}")

# Example usage:
# modify_system_shortcut('close', '<Super>Q')
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        print_system_shortcuts()
    elif len(sys.argv) >= 3:
        if len(sys.argv) >= 4:
            # If schema is provided
            modify_system_shortcut(sys.argv[1], sys.argv[2], sys.argv[3])
        else:
            # Use default schema
            modify_system_shortcut(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python3 modify_system_shortcut.py [list | action new_shortcut [schema]]")
        print("Examples:")
        print("  python3 modify_system_shortcut.py list")
        print("  python3 modify_system_shortcut.py home '<Control>e'")
        print("  python3 modify_system_shortcut.py home '<Control>e' org.gnome.settings-daemon.plugins.media-keys")