import pandas as pd
import io

def merge_csv_contents(content1, content2):
    """
    Merges two CSV contents (passed as strings) with optional metadata.
    """
    def parse_with_metadata(content):
        metadata = []
        data_lines = []
        for line in content.strip().split('\n'):
            if line.startswith('#'):
                metadata.append(line)
            else:
                data_lines.append(line)
        
        if not data_lines:
            return metadata, pd.DataFrame()
            
        df = pd.read_csv(io.StringIO('\n'.join(data_lines)))
        return metadata, df

    meta1, df1 = parse_with_metadata(content1)
    meta2, df2 = parse_with_metadata(content2)

    if df1.empty: return False, "File 1 is empty or invalid"
    if df2.empty: return False, "File 2 is empty or invalid"

    # Identify join key
    if 'Timestamp' in df1.columns and 'Timestamp' in df2.columns:
        join_key = 'Timestamp'
    elif 'Concentration' in df1.columns and 'Concentration' in df2.columns:
        join_key = 'Concentration'
    else:
        return False, "Could not find common key column (Timestamp or Concentration)"

    # Merge logic based on the detected key
    if join_key == 'Timestamp':
        # Measured data: Rename Value:x columns and perform outer join
        df1_value_cols = [c for c in df1.columns if c.startswith('Value:')]
        df2_value_cols = [c for c in df2.columns if c.startswith('Value:')]
        
        n = len(df1_value_cols)
        rename_map = {}
        for i, col in enumerate(df2_value_cols, 1):
            rename_map[col] = f"Value:{n + i}"
        df2 = df2.rename(columns=rename_map)
        
        merged_df = pd.merge(df1, df2, on='Timestamp', how='outer')
    else:
        # Calibration data: Concatenate rows to maintain format
        merged_df = pd.concat([df1, df2], ignore_index=True)

    merged_df = merged_df.sort_values(by=join_key)
    merged_df = merged_df.fillna("NONE")

    # Metadata Combination (Unique lines)
    combined_meta = []
    seen_meta = set()
    for line in meta1 + meta2:
        if line not in seen_meta:
            combined_meta.append(line)
            seen_meta.add(line)

    # Convert to CSV string
    output = io.StringIO()
    for line in combined_meta:
        output.write(line + '\n')
    merged_df.to_csv(output, index=False)
    
    return True, output.getvalue()
