import re 

# Helper function for getting next filename (since original is imported, but adapted here)
def get_next_filename(ext, files, base):
    pattern = re.compile(r'^' + re.escape(base) + r'_(\d{3})' + re.escape(ext) + '$')
    max_num = 0
    for f in files:
        match = pattern.match(f)
        if match:
            num = int(match.group(1))
            max_num = max(max_num, num)
    next_num = max_num + 1
    return f"{base}_{next_num:03d}{ext}"