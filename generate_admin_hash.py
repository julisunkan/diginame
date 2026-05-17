#!/usr/bin/env python3
"""
Utility script to generate secure password hashes for admin authentication.
Use this to create a hashed password for production deployment.
"""

import getpass
from werkzeug.security import generate_password_hash

def main():
    print("=== Admin Password Hash Generator ===")
    print("This script generates a secure hash for your admin password.")
    print("Use the generated hash as the ADMIN_PASSWORD_HASH environment variable in production.\n")
    
    while True:
        # Get password from user (hidden input)
        password = getpass.getpass("Enter admin password: ")
        
        if len(password) < 8:
            print("Password should be at least 8 characters long. Please try again.\n")
            continue
            
        # Confirm password
        confirm_password = getpass.getpass("Confirm password: ")
        
        if password != confirm_password:
            print("Passwords don't match. Please try again.\n")
            continue
            
        break
    
    # Generate secure hash
    password_hash = generate_password_hash(password)
    
    print("\n=== Generated Hash ===")
    print(f"ADMIN_PASSWORD_HASH={password_hash}")
    print("\n=== Instructions ===")
    print("1. Copy the hash above")
    print("2. Set it as an environment variable in your PythonAnywhere web app:")
    print("   - Go to Web tab > Environment variables section")
    print("   - Add: ADMIN_PASSWORD_HASH = <the hash above>")
    print("3. Do NOT set ADMIN_PASSWORD when using ADMIN_PASSWORD_HASH")
    print("4. Keep this hash secure and never commit it to version control")
    
if __name__ == "__main__":
    main()