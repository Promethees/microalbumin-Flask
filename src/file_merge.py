import pandas as pd
import io

def merge_csv_contents(contents):
    """
    Merges multiple CSV contents (list of strings) with optional metadata.
    Handles measured data (Value:n via outer join) and calibration data (concat).
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

    parsed = [parse_with_metadata(c) for c in contents]

    for i, (_, df) in enumerate(parsed):
        if df.empty:
            return False, f"File {i + 1} is empty or invalid"

    if all('Timestamp' in df.columns for _, df in parsed):
        join_key = 'Timestamp'
    elif all('Concentration' in df.columns for _, df in parsed):
        join_key = 'Concentration'
    else:
        return False, "Could not find common key column (Timestamp or Concentration)"

    if join_key == 'Timestamp':
        value_offset = 0
        dfs_renamed = []
        for _, df in parsed:
            value_cols = [c for c in df.columns if c.startswith('Value:')]
            rename_map = {col: f"Value:{value_offset + i + 1}" for i, col in enumerate(value_cols)}
            dfs_renamed.append(df.rename(columns=rename_map))
            value_offset += len(value_cols)

        merged_df = dfs_renamed[0]
        for df in dfs_renamed[1:]:
            merged_df = pd.merge(merged_df, df, on='Timestamp', how='outer')
    else:
        merged_df = pd.concat([df for _, df in parsed], ignore_index=True)

    merged_df = merged_df.sort_values(by=join_key)
    merged_df = merged_df.fillna("NONE")

    combined_meta = []
    seen_meta = set()
    for meta, _ in parsed:
        for line in meta:
            if line not in seen_meta:
                combined_meta.append(line)
                seen_meta.add(line)

    output = io.StringIO()
    for line in combined_meta:
        output.write(line + '\n')
    merged_df.to_csv(output, index=False)

    return True, output.getvalue()
