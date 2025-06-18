import os
import platform

os_name = platform.system().lower()
if "window" in os_name:
    current_directory = os.path.expanduser("~\\Desktop\\")
else:
    current_directory = os.path.expanduser("~/Desktop/")

def get_directory():
    global current_directory
    return current_directory

def browse_directory(new_path):
    global current_directory
    new_path = os.path.expanduser(new_path)
    if os.path.isdir(new_path):
        current_directory = new_path
        return True
    return False

def get_parent_directory(current_dir):
    parent = os.path.dirname(current_dir)
    # Avoid returning root directory as parent if already at root
    if parent == current_dir:
        return None
    # Check if parent directory is hidden
    if parent and os.path.basename(parent).startswith('.'):
        return get_parent_directory(parent)  # Recursively get the non-hidden parent
    return parent

def get_child_directories(current_dir):
    try:
        # List directories, excluding hidden ones (starting with '.')
        dirs = [os.path.join(current_dir, d) for d in os.listdir(current_dir)
                if os.path.isdir(os.path.join(current_dir, d)) and not d.startswith('.')]
        dirs.sort()  # Sort alphabetically
        return dirs
    except Exception as e:
        print(f"Error listing child directories: {e}")
        return []