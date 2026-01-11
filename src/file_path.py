import os
from pathlib import Path

# This will point to the directory where main.py is located
current_directory = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def get_directory():
    global current_directory
    # Convert single backslashes to double backslashes for JavaScript compatibility
    # return current_directory.replace('\\', '\\\\')
    return current_directory

def browse_directory(new_path):
    global current_directory
    new_path = os.path.expanduser(new_path)
    if os.path.isdir(new_path):
        current_directory = os.path.abspath(new_path)
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
    Returns list of visible (non-hidden) subdirectory paths with double backslashes.
    """
    path = Path(path).resolve()
    
    if not path.is_dir():
        raise ValueError(f"'{path}' is not a valid directory.")

    return [
        str(p).replace('\\', '\\\\')
        for p in path.iterdir()
        if p.is_dir() and not (p.name.startswith('.') or p.name.startswith('_'))
    ]

def is_multi_value_timeseries_csv_header(header_line: str) -> bool:
    """
    Checks if the header matches the pattern used for raw multi-sensor/time-series data:
    Timestamp,Value:1,Value:2,Value:3,... (with possible extra spaces)
    
    Returns True if this is the kind of file we want to count sources from.
    """
    cleaned = re.sub(r'\s+', '', header_line.strip())
    if not cleaned.startswith('Timestamp,'):
        return False
    
    parts = cleaned.split(',')
    if len(parts) < 2:
        return False
    
    value_parts = parts[1:]  # everything after Timestamp
    return all(part.startswith('Value:') for part in value_parts)