import csv

import tempfile
import shutil

def remove_csv_columns(file_path, columns_to_remove):
    """
    Remove specified columns from a CSV file and renumber 'Value:n' columns.
    Uses O(1) memory by streaming data from input to a temporary output file.
    
    Args:
        file_path (str): The absolute path to the CSV file.
        columns_to_remove (list): List of column names to remove.
        
    Returns:
        tuple: (success (bool), message (str))
    """
    import os
    try:
        if not os.path.exists(file_path):
            return False, "File does not exist"

        fd, temp_path = tempfile.mkstemp(suffix='.csv', text=True)
        
        with open(file_path, 'r', encoding='utf-8') as f_in, os.fdopen(fd, 'w', encoding='utf-8', newline='') as f_out:
            writer = csv.writer(f_out)
            metadata_written_count = 0
            
            def iter_data_lines():
                nonlocal metadata_written_count
                for line in f_in:
                    stripped = line.strip()
                    if stripped.startswith('#'):
                        f_out.write(line)
                        metadata_written_count += 1
                    elif stripped:
                        yield line
            
            line_generator = iter_data_lines()
            try:
                raw_headers_line = next(line_generator)
                headers = [h.strip() for h in next(csv.reader([raw_headers_line]))]
            except StopIteration:
                os.remove(temp_path)
                return False, "No data found in CSV"
                
            # Validation
            if 'Timestamp' in columns_to_remove:
                os.remove(temp_path)
                return False, "Cannot remove 'Timestamp' column"
                
            if 'Timestamp' not in headers:
                os.remove(temp_path)
                return False, "CSV must contain a 'Timestamp' column for this operation"
                
            value_cols = [col for col in headers if col.startswith('Value:')]
            if not value_cols:
                os.remove(temp_path)
                return False, "No 'Value:' columns found. This feature is for data CSVs."
                
            # Filter columns to remove to only those that exist
            existing_cols_to_remove = [col for col in columns_to_remove if col in headers]
            
            # Check if we are removing all Value: columns
            remaining_value_cols = [col for col in value_cols if col not in existing_cols_to_remove]
            if not remaining_value_cols:
                os.remove(temp_path)
                return False, "Cannot remove all 'Value:' columns. At least one must remain."
                
            # Get indices of columns to keep
            cols_to_keep_indices = [i for i, h in enumerate(headers) if h not in existing_cols_to_remove]
            new_headers = [headers[i] for i in cols_to_keep_indices]
            
            # Renumber remaining Value: columns in new_headers
            value_col_count = 1
            final_headers = []
            for h in new_headers:
                if h.startswith('Value:'):
                    new_h = f"Value:{value_col_count}"
                    final_headers.append(new_h)
                    value_col_count += 1
                else:
                    final_headers.append(h)
                    
            writer.writerow(final_headers)
            
            reader = csv.reader(line_generator)
            for row in reader:
                # Provide empty strings if the row is short
                row_extended = row + [''] * max(0, len(headers) - len(row))
                new_row = [row_extended[i] for i in cols_to_keep_indices]
                writer.writerow(new_row)
                
        # Replace the original file with the new file
        shutil.move(temp_path, file_path)
        return True, "Columns removed successfully"
        
    except Exception as e:
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        return False, str(e)
