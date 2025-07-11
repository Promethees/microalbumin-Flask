import os
import glob
import re
# Generic helper function to get_next_filename

def get_next_filename(fileType, base_dir, base_name):
        pattern = os.path.join(base_dir, f"{base_name}_*[0-9]{fileType}")
        existing_files = glob.glob(pattern)
        number_pattern = re.compile(rf"{base_name}_(\d+){fileType}$")
        numbers = []
        for file in existing_files:
            match = number_pattern.search(os.path.basename(file))
            if match:
                numbers.append(int(match.group(1)))
        next_number = max(numbers, default=-1) + 1
        return os.path.join(base_dir, f"{base_name}_{next_number}{fileType}")