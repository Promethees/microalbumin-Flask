import io
import csv

def remove_csv_columns(file_path, columns_to_remove):
    """
    Remove specified columns from a CSV file and renumber 'Value:n' columns.
    
    Args:
        file_path (str): The absolute path to the CSV file.
        columns_to_remove (list): List of column names to remove.
        
    Returns:
        tuple: (success (bool), message (str))
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        lines = content.splitlines()
        metadata = []
        data_lines = []
        
        for line in lines:
            if line.strip().startswith('#'):
                metadata.append(line)
            elif line.strip():
                data_lines.append(line)
        
        if not data_lines:
            return False, "No data found in CSV"
            
        reader = csv.reader(io.StringIO("\n".join(data_lines)))
        headers = [h.strip() for h in next(reader)]
        rows = list(reader)
        
        # Validation
        if 'Timestamp' in columns_to_remove:
            return False, "Cannot remove 'Timestamp' column"
            
        if 'Timestamp' not in headers:
            return False, "CSV must contain a 'Timestamp' column for this operation"
            
        value_cols = [col for col in headers if col.startswith('Value:')]
        if not value_cols:
            return False, "No 'Value:' columns found. This feature is for data CSVs."
            
        # Filter columns to remove to only those that exist
        existing_cols_to_remove = [col for col in columns_to_remove if col in headers]
        
        # Check if we are removing all Value: columns
        remaining_value_cols = [col for col in value_cols if col not in existing_cols_to_remove]
        if not remaining_value_cols:
            return False, "Cannot remove all 'Value:' columns. At least one must remain."
            
        # Get indices of columns to keep
        cols_to_keep_indices = [i for i, h in enumerate(headers) if h not in existing_cols_to_remove]
        new_headers = [headers[i] for i in cols_to_keep_indices]
        
        # Renumber remaining Value: columns in new_headers
        value_col_count = 1
        rename_map = {}
        final_headers = []
        for h in new_headers:
            if h.startswith('Value:'):
                new_h = f"Value:{value_col_count}"
                final_headers.append(new_h)
                value_col_count += 1
            else:
                final_headers.append(h)
        
        # Reconstruct rows with kept columns
        new_rows = []
        for row in rows:
            new_rows.append([row[i] for i in cols_to_keep_indices])
            
        # Reconstruct and write back to file
        with open(file_path, 'w', encoding='utf-8', newline='') as f:
            for line in metadata:
                f.write(line + "\n")
            writer = csv.writer(f)
            writer.writerow(final_headers)
            writer.writerows(new_rows)
            
        return True, "Columns removed successfully"
        
    except Exception as e:
        return False, str(e)
