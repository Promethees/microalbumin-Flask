import io
import pandas as pd
import re

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
        with open(file_path, 'r') as f:
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
            
        df = pd.read_csv(io.StringIO("\n".join(data_lines)))
        
        # Validation
        if 'Timestamp' in columns_to_remove:
            return False, "Cannot remove 'Timestamp' column"
            
        if 'Timestamp' not in df.columns:
            return False, "CSV must contain a 'Timestamp' column for this operation"
            
        value_cols = [col for col in df.columns if col.startswith('Value:')]
        if not value_cols:
            return False, "No 'Value:' columns found. This feature is for data CSVs."
            
        # Filter columns to remove to only those that exist
        existing_cols_to_remove = [col for col in columns_to_remove if col in df.columns]
        
        # Check if we are removing all Value: columns
        remaining_value_cols = [col for col in value_cols if col not in existing_cols_to_remove]
        if not remaining_value_cols:
            return False, "Cannot remove all 'Value:' columns. At least one must remain."
            
        # Remove columns
        df = df.drop(columns=existing_cols_to_remove)
        
        # Renumber remaining Value: columns
        current_value_cols = [col for col in df.columns if col.startswith('Value:')]
        
        rename_map = {}
        for i, col in enumerate(current_value_cols, 1):
            rename_map[col] = f"Value:{i}"
            
        df = df.rename(columns=rename_map)
        
        # Reconstruct and write back to file
        with open(file_path, 'w') as f:
            for line in metadata:
                f.write(line + "\n")
            df.to_csv(f, index=False)
            
        return True, "Columns removed successfully"
        
    except Exception as e:
        return False, str(e)
