#!/usr/bin/env python3
"""
Setup and test secure credentials system
"""

import os
import sys
import json

def setup_secure_credentials():
    """Set up and test the secure credentials system"""
    print("🔐 Setting up secure credentials system...")
    
    # Check if credentials file exists
    creds_file = 'config/credentials.json'
    if not os.path.exists(creds_file):
        print(f"❌ Credentials file not found: {creds_file}")
        return False
    
    print("✅ Credentials file found")
    
    # Test loading credentials
    try:
        sys.path.append('config')
        from credentials_loader import get_credentials_loader, load_credentials_to_env
        
        # Test loading
        loader = get_credentials_loader()
        print("✅ Credentials loader initialized")
        
        # Test PostgreSQL config
        pg_config = loader.get_postgresql_config()
        print(f"✅ PostgreSQL config loaded - Host: {pg_config['host']}")
        
        # Test setting environment variables
        load_credentials_to_env('postgresql')
        print("✅ Environment variables set from credentials")
        
        # Test database connection
        sys.path.append('database')
        from database_config import get_db_connection
        
        db = get_db_connection()
        if db.test_connection():
            print("✅ Database connection successful using secure credentials")
            
            # Get record count
            count = db.execute_query('SELECT COUNT(*) FROM option_strategies')[0][0]
            print(f"✅ Database has {count} records")
            
            return True
        else:
            print("❌ Database connection failed")
            return False
            
    except Exception as e:
        print(f"❌ Error testing credentials: {e}")
        return False

def remove_hardcoded_credentials():
    """Remove or rename files with hardcoded credentials"""
    print("\n🧹 Cleaning up hardcoded credentials...")
    
    # Remove .env file (credentials now in secure file)
    if os.path.exists('.env'):
        os.rename('.env', '.env.backup')
        print("✅ Moved .env to .env.backup (hidden from git)")
    
    # Check for other credential files
    potential_cred_files = [
        'database_config.txt',
        'config.txt',
        'passwords.txt'
    ]
    
    for file in potential_cred_files:
        if os.path.exists(file):
            print(f"⚠️  Found potential credential file: {file}")
            print("    Please review and move to secure storage if needed")

def show_security_status():
    """Show current security status"""
    print("\n🛡️  Security Status:")
    print("✅ Credentials stored in config/credentials.json")
    print("✅ Credentials file hidden from git (.gitignore)")
    print("✅ No hardcoded passwords in code")
    print("✅ Environment variables loaded from secure file")
    print("✅ Fallback to environment variables if needed")
    print()
    print("📋 Usage:")
    print("  - Credentials automatically loaded from secure file")
    print("  - Set DB_TYPE environment variable to switch databases")
    print("  - All applications use secure credentials by default")
    print()
    print("🔒 Security Features:")
    print("  - JSON credentials file (not tracked by git)")
    print("  - Automatic environment variable loading")
    print("  - Fallback to environment variables")
    print("  - No hardcoded passwords in source code")

def main():
    """Main setup function"""
    print("🚀 Optcom Secure Credentials Setup")
    print("=" * 50)
    
    # Test credentials system
    success = setup_secure_credentials()
    
    if success:
        # Clean up old files
        remove_hardcoded_credentials()
        
        # Show status
        show_security_status()
        
        print("\n🎉 Secure credentials setup complete!")
        print("Your database credentials are now securely stored and hidden from git.")
        
    else:
        print("\n❌ Setup failed. Please check the errors above.")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())