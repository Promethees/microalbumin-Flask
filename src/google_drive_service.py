"""
Google Drive API service module for Easy OKAPI.
Handles OAuth 2.0 authentication, file operations, and folder management.
"""

import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from io import BytesIO

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from googleapiclient.errors import HttpError

from cryptography.fernet import Fernet, InvalidToken  # NEW: For decryption

from user_data import (
    get_user_data, get_drive_credentials, set_drive_credentials,
    get_drive_folder, set_drive_folder, set_drive_preference
)
from config import Config


def _escape_drive_query(value: str) -> str:
    """Escape a string for safe interpolation into a Drive API query."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def get_drive_service(user_id: str = None):
    """
    Get authenticated Google Drive service for user.
    Returns None if not authenticated.
    """
    creds = get_drive_credentials(user_id)
    
    if not creds:
        return None
    
    # Convert to Credentials object if needed
    if isinstance(creds, str):
        creds = json.loads(creds)
    
    if isinstance(creds, dict):
        creds = Credentials.from_authorized_user_info(creds, Config.GOOGLE_SCOPES)
    
    # Refresh token if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Save refreshed credentials
            set_drive_credentials(creds.to_json(), user_id)
        except Exception as e:
            print(f"Error refreshing credentials: {e}")
            return None
    
    try:
        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        print(f"Error building Drive service: {e}")
        return None


def load_encrypted_credentials() -> Dict:
    """
    Load and decrypt credentials from encrypted file.
    Raises exceptions on failure for security/logging.
    """
    if not Config.GOOGLE_ENCRYPTION_KEY:
        raise ValueError("GOOGLE_ENCRYPTION_KEY not set in environment")

    if not os.path.exists(Config.GOOGLE_CREDENTIALS_FILE):
        raise FileNotFoundError(f"Encrypted credentials file not found: {Config.GOOGLE_CREDENTIALS_FILE}")

    with open(Config.GOOGLE_CREDENTIALS_FILE, 'rb') as f:
        encrypted_data = f.read()

    try:
        fernet = Fernet(Config.GOOGLE_ENCRYPTION_KEY.encode())  # Key must be bytes
        decrypted_data = fernet.decrypt(encrypted_data)
        return json.loads(decrypted_data.decode('utf-8'))
    except (InvalidToken, ValueError) as e:
        raise ValueError(f"Failed to decrypt credentials: Invalid key or corrupted file ({str(e)})")


def create_oauth_flow(redirect_uri: str = None) -> Flow:
    """Create OAuth 2.0 flow for authentication using decrypted credentials."""
    redirect_uri = redirect_uri or Config.GOOGLE_REDIRECT_URI
    
    client_config = load_encrypted_credentials()
    
    flow = Flow.from_client_config(
        client_config,
        scopes=Config.GOOGLE_SCOPES,
        redirect_uri=redirect_uri
    )
    
    return flow


def get_authorization_url(state: str = None) -> Tuple[str, str]:
    """
    Generate OAuth authorization URL.
    Returns (authorization_url, state)
    """
    flow = create_oauth_flow()
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',  # Force consent to get refresh token
        state=state
    )
    
    return authorization_url, state


def exchange_code_for_credentials(code: str, state: str = None) -> Credentials:
    """Exchange authorization code for credentials."""
    flow = create_oauth_flow()
    
    if state:
        flow.fetch_token(code=code)
    else:
        flow.fetch_token(code=code)
    
    return flow.credentials


def list_folders(service, parent_id: str = 'root', max_results: int = 100) -> List[Dict]:
    """
    List all folders in user's Drive.
    Returns list of {id, name, modifiedTime}
    """
    try:
        query = f"mimeType='application/vnd.google-apps.folder' and '{_escape_drive_query(parent_id)}' in parents and trashed=false"
        
        results = service.files().list(
            q=query,
            pageSize=max_results,
            fields="files(id, name, modifiedTime)",
            orderBy="name"
        ).execute()
        
        folders = results.get('files', [])
        return folders
    
    except HttpError as error:
        print(f"An error occurred listing folders: {error}")
        return []


def create_folder(service, folder_name: str, parent_id: str = None) -> Optional[Dict]:
    """
    Create a new folder in Drive.
    Returns {id, name} or None on error.
    """
    try:
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        
        if parent_id:
            file_metadata['parents'] = [parent_id]
        
        folder = service.files().create(
            body=file_metadata,
            fields='id, name'
        ).execute()
        
        return folder
    
    except HttpError as error:
        print(f"An error occurred creating folder: {error}")
        return None


def list_files(service, folder_id: str, mime_type: str = None) -> List[Dict]:
    """
    List files in a specific folder.
    Optionally filter by mime_type (e.g., 'text/csv', 'application/json')
    """
    try:
        query = f"'{_escape_drive_query(folder_id)}' in parents and trashed=false"

        if mime_type:
            query += f" and mimeType='{_escape_drive_query(mime_type)}'"
        
        results = service.files().list(
            q=query,
            pageSize=100,
            fields="files(id, name, mimeType, modifiedTime, size)",
            orderBy="name"
        ).execute()
        
        files = results.get('files', [])
        return files
    
    except HttpError as error:
        print(f"An error occurred listing files: {error}")
        return []


def upload_file(service, filename: str, content: str, folder_id: str, mime_type: str = 'text/plain') -> Optional[str]:
    """
    Upload a file to Drive.
    Returns file_id on success, None on error.
    """
    try:
        # Check if file already exists in folder
        existing_files = service.files().list(
            q=f"name='{_escape_drive_query(filename)}' and '{_escape_drive_query(folder_id)}' in parents and trashed=false",
            fields="files(id)"
        ).execute().get('files', [])
        
        # Convert content to bytes
        file_bytes = BytesIO(content.encode('utf-8'))
        
        media = MediaIoBaseUpload(
            file_bytes,
            mimetype=mime_type,
            resumable=True
        )
        
        if existing_files:
            # Update existing file
            file_id = existing_files[0]['id']
            file = service.files().update(
                fileId=file_id,
                media_body=media
            ).execute()
        else:
            # Create new file
            file_metadata = {
                'name': filename,
                'parents': [folder_id]
            }
            
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
        
        return file.get('id')
    
    except HttpError as error:
        print(f"An error occurred uploading file: {error}")
        return None


def download_file(service, file_id: str, mime_type: str = None) -> Optional[str]:
    """
    Download file content from Drive.
    If it's a Google Doc/Sheet, use export_media.
    Returns content as string, None on error.
    """
    try:
        # If mime_type not provided, fetch it
        if not mime_type:
            file_meta = service.files().get(fileId=file_id, fields='mimeType').execute()
            mime_type = file_meta.get('mimeType')

        # Check if it's a Google Doc/Sheet/etc.
        if mime_type and mime_type.startswith('application/vnd.google-apps.'):
            # For spreadsheets, export as CSV
            if 'spreadsheet' in mime_type:
                request = service.files().export_media(fileId=file_id, mimeType='text/csv')
            else:
                # Other Google formats not explicitly handled yet
                print(f"Skipping non-spreadsheet Google format: {mime_type}")
                return None
        else:
            # Standard binary download
            request = service.files().get_media(fileId=file_id)

        file_bytes = BytesIO()
        downloader = MediaIoBaseDownload(file_bytes, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        # Convert bytes to string
        file_bytes.seek(0)
        content = file_bytes.read().decode('utf-8')
        return content
    
    except HttpError as error:
        print(f"An error occurred downloading file: {error}")
        return None


def delete_file(service, file_id: str) -> bool:
    """
    Delete a file from Drive (move to trash).
    Returns True on success, False on error.
    """
    try:
        service.files().delete(fileId=file_id).execute()
        return True
    
    except HttpError as error:
        print(f"An error occurred deleting file: {error}")
        return False


def sync_session_to_drive(user_id: str = None, auto: bool = False) -> Dict:
    """
    Sync current session data to Google Drive.
    Returns {status, message, synced_files}
    """
    service = get_drive_service(user_id)
    if not service:
        return {'status': 'error', 'message': 'Not authenticated with Google Drive'}
    
    folder_id = get_drive_folder(user_id)
    if not folder_id:
        return {'status': 'error', 'message': 'No Drive folder selected'}
    
    user_data = get_user_data()
    synced_files = []
    errors = []
    
    try:
        # Sync CSV files
        for filename, content in user_data['csv'].items():
            file_id = upload_file(service, filename, content, folder_id, 'text/csv')
            if file_id:
                user_data['drive']['file_mapping'][filename] = file_id
                synced_files.append(filename)
            else:
                errors.append(filename)
        
        # Sync JSON files (kinetics and point)
        for mode in ['kinetics', 'point']:
            for filename, content in user_data['json'][mode].items():
                file_id = upload_file(service, filename, content, folder_id, 'application/json')
                if file_id:
                    user_data['drive']['file_mapping'][filename] = file_id
                    synced_files.append(filename)
                else:
                    errors.append(filename)
        
        # Save mappings to Redis
        from user_data import save_user_data
        save_user_data(user_data, user_id)
        
        # Update last sync time
        set_drive_preference('last_sync', datetime.now().isoformat(), user_id)
        
        if errors:
            return {
                'status': 'partial',
                'message': f'Synced {len(synced_files)} files, {len(errors)} failed',
                'synced_files': synced_files,
                'errors': errors
            }
        else:
            return {
                'status': 'success',
                'message': f'Successfully synced {len(synced_files)} files',
                'synced_files': synced_files
            }
    
    except Exception as e:
        return {'status': 'error', 'message': f'Sync failed: {str(e)}'}


def load_drive_to_session(user_id: str = None) -> Dict:
    """
    Load files from Google Drive to session.
    Returns {status, message, loaded_files}
    """
    service = get_drive_service(user_id)
    if not service:
        return {'status': 'error', 'message': 'Not authenticated with Google Drive'}
    
    folder_id = get_drive_folder(user_id)
    if not folder_id:
        return {'status': 'error', 'message': 'No Drive folder selected'}
    
    user_data = get_user_data()
    loaded_files = []
    errors = []
    
    try:
        # Clear existing session data and mappings before loading from Drive
        user_data['csv'].clear()
        user_data['json']['kinetics'].clear()
        user_data['json']['point'].clear()
        user_data['drive']['file_mapping'].clear()
        
        # Get all files in folder
        all_files = list_files(service, folder_id)
        
        for file_info in all_files:
            filename = file_info['name']
            file_id = file_info['id']
            
            # Download content
            content = download_file(service, file_id, file_info.get('mimeType'))
            if not content:
                errors.append(filename)
                continue
            
            # Store in appropriate location based on extension
            if filename.endswith('.csv'):
                user_data['csv'][filename] = content
                from user_data import update_file_metadata
                update_file_metadata(filename, content)
                loaded_files.append(filename)
            elif filename.endswith('.json'):
                # Determine mode based on content or filename
                try:
                    json_data = json.loads(content)
                    # Check if it's a kinetics or point calibration
                    if 'time' in json_data and 'time-unit' in json_data:
                        user_data['json']['point'][filename] = content
                    else:
                        user_data['json']['kinetics'][filename] = content
                    loaded_files.append(filename)
                except json.JSONDecodeError:
                    errors.append(filename)
            
            # Update file mapping
            user_data['drive']['file_mapping'][filename] = file_id
        
        # Save loaded content to Redis
        from user_data import save_user_data
        save_user_data(user_data, user_id)
        
        if errors:
            return {
                'status': 'partial',
                'message': f'Loaded {len(loaded_files)} files, {len(errors)} failed',
                'loaded_files': loaded_files,
                'errors': errors
            }
        else:
            return {
                'status': 'success',
                'message': f'Successfully loaded {len(loaded_files)} files',
                'loaded_files': loaded_files
            }
    
    except Exception as e:
        return {'status': 'error', 'message': f'Load failed: {str(e)}'}
