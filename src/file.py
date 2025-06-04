import os
from file_path import get_directory

def get_file_list(directory):
    try:
        files = [f for f in os.listdir(directory) if f.lower().endswith('.csv')]
        print(f"Files found in {directory}: {files}")  # Debug print
        return files
    except Exception as e:
        print(f"Error listing files in {directory}: {e}")  # Debug print
        return []