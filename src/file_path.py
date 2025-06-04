import os

current_directory = os.path.expanduser("~/Desktop")

def get_directory():
    return current_directory

def browse_directory(new_path):
    global current_directory
    new_path = os.path.normpath(os.path.expanduser(new_path))
    if os.path.exists(new_path) and os.path.isdir(new_path):
        current_directory = new_path
        return True
    return False

def get_parent_directory(current_dir):
    try:
        current_dir = os.path.normpath(os.path.expanduser(current_dir))
        parent = os.path.dirname(current_dir)
        if parent != current_dir:  # Ensure not at root
            return parent
        return None
    except Exception as e:
        print(f"Error getting parent directory: {e}")
        return None

def get_child_directories(current_dir):
    try:
        current_dir = os.path.normpath(os.path.expanduser(current_dir))
        children = []
        for item in os.listdir(current_dir):
            item_path = os.path.join(current_dir, item)
            if os.path.isdir(item_path):
                children.append(item_path)
        return sorted(children)  # Sort for consistent display
    except Exception as e:
        print(f"Error getting child directories: {e}")
        return []