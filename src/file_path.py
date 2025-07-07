import os
import platform

# This will point to the directory where main.py is located
current_directory = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def get_directory():
    global current_directory
    # Convert single backslashes to double backslashes for JavaScript compatibility
    return current_directory.replace('\\', '\\\\')

def browse_directory(new_path):
    global current_directory
    new_path = os.path.expanduser(new_path)
    if os.path.isdir(new_path):
        current_directory = new_path
        # Convert single backslashes to double backslashes for JavaScript compatibility
        return current_directory.replace('\\', '\\\\')
    return False

def get_parent_directory(path, levels=1):
    """
    Returns the parent directory of the given path.
    `levels` specifies how many levels up to go (default is 1).
    """
    if not path:
        raise ValueError("Path cannot be empty.")
    
    path = os.path.abspath(path)
    for _ in range(levels):
        path = os.path.dirname(path)
    
    # Convert single backslashes to double backslashes for JavaScript compatibility
    return path.replace('\\', '\\\\')

def get_child_directories(path):
    """
    Returns a list of full paths to all immediate subdirectories of the given path.
    """
    if not os.path.isdir(path):
        raise ValueError(f"'{path}' is not a valid directory.")

    # Convert each child directory path to use double backslashes
    return [
        os.path.join(path, name).replace('\\', '\\\\')
        for name in os.listdir(path)
        if os.path.isdir(os.path.join(path, name))
    ]