# encrypt_credentials.py (run this locally once)
from cryptography.fernet import Fernet
import json
import os

# Load original credentials
with open('credentials.json', 'r') as f:
    credentials_data = json.load(f)

# Generate a key (save this securely as env var GOOGLE_ENCRYPTION_KEY)
key = Fernet.generate_key()
print("Generated encryption key (set as GOOGLE_ENCRYPTION_KEY in env):", key.decode())

# Encrypt
fernet = Fernet(key)
encrypted_data = fernet.encrypt(json.dumps(credentials_data).encode())

# Save encrypted file
with open('credentials.enc', 'wb') as f:
    f.write(encrypted_data)

print("Encrypted file saved as credentials.enc")