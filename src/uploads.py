import pandas as pd 
UPLOAD_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in UPLOAD_EXTENSIONS

def process_csv_file(file):
    """Process uploaded CSV file and return DataFrame"""
    try:
        # Read CSV with flexible parameters
        df = pd.read_csv(file, encoding='utf-8')
        return df
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(file, encoding='latin-1')
            return df
        except Exception as e:
            raise Exception(f"Error reading CSV: {str(e)}")
    except Exception as e:
        raise Exception(f"Error processing CSV: {str(e)}")