"""
Secure credentials loader for optcom project
Loads credentials from hidden JSON file, never hardcoded
"""

import json
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class CredentialsLoader:
    """Secure credentials management"""
    
    def __init__(self, credentials_file: str = None):
        """
        Initialize credentials loader
        
        Args:
            credentials_file: Path to credentials JSON file
        """
        if credentials_file is None:
            # Default to config/credentials.json relative to project root
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            credentials_file = os.path.join(project_root, 'config', 'credentials.json')
        
        self.credentials_file = credentials_file
        self._credentials = None
        self._load_credentials()
    
    def _load_credentials(self):
        """Load credentials from JSON file"""
        try:
            if not os.path.exists(self.credentials_file):
                raise FileNotFoundError(f"Credentials file not found: {self.credentials_file}")
            
            with open(self.credentials_file, 'r') as f:
                self._credentials = json.load(f)
            
            logger.debug("Credentials loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load credentials: {e}")
            raise
    
    def get_database_config(self, db_type: str = None) -> Dict[str, Any]:
        """
        Get database configuration
        
        Args:
            db_type: 'postgresql' or 'sqlite'. If None, uses DB_TYPE env var or defaults to 'sqlite'
        
        Returns:
            Database configuration dictionary
        """
        if db_type is None:
            db_type = os.getenv('DB_TYPE', 'postgresql').lower()
        
        if db_type not in ['postgresql', 'sqlite']:
            raise ValueError(f"Unsupported database type: {db_type}")
        
        db_config = self._credentials.get('database', {}).get(db_type, {})
        
        if not db_config:
            raise ValueError(f"No configuration found for database type: {db_type}")
        
        return db_config
    
    def get_postgresql_config(self) -> Dict[str, Any]:
        """Get PostgreSQL configuration"""
        return self.get_database_config('postgresql')
    
    def get_sqlite_config(self) -> Dict[str, Any]:
        """Get SQLite configuration"""
        return self.get_database_config('sqlite')
    
    def get_gcp_config(self) -> Dict[str, Any]:
        """Get GCP configuration"""
        return self._credentials.get('gcp', {})
    
    def get_network_config(self) -> Dict[str, Any]:
        """Get network configuration"""
        return self._credentials.get('network', {})
    
    def get_credential(self, path: str) -> Any:
        """
        Get a specific credential by dot notation path
        
        Args:
            path: Dot notation path like 'database.postgresql.host'
        
        Returns:
            The credential value
        """
        keys = path.split('.')
        value = self._credentials
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                raise KeyError(f"Credential not found: {path}")
        
        return value
    
    def set_environment_variables(self, db_type: str = None):
        """
        Set environment variables from credentials
        
        Args:
            db_type: Database type to configure ('postgresql' or 'sqlite')
        """
        if db_type is None:
            db_type = os.getenv('DB_TYPE', 'postgresql').lower()
        
        # Set database type
        os.environ['DB_TYPE'] = db_type
        
        if db_type == 'postgresql':
            pg_config = self.get_postgresql_config()
            os.environ['DB_HOST'] = str(pg_config['host'])
            os.environ['DB_PORT'] = str(pg_config['port'])
            os.environ['DB_NAME'] = pg_config['database']
            os.environ['DB_USER'] = pg_config['user']
            os.environ['DB_PASSWORD'] = pg_config['password']
        elif db_type == 'sqlite':
            sqlite_config = self.get_sqlite_config()
            os.environ['SQLITE_DB_PATH'] = sqlite_config['path']
        
        # Set GCP variables
        gcp_config = self.get_gcp_config()
        if gcp_config:
            os.environ['GCP_PROJECT_ID'] = gcp_config.get('project_id', '')
            os.environ['INSTANCE_CONNECTION_NAME'] = gcp_config.get('instance_connection_name', '')
        
        logger.debug(f"Environment variables set for {db_type}")

# Global instance for easy access
_credentials_loader = None

def get_credentials_loader() -> CredentialsLoader:
    """Get the global credentials loader instance"""
    global _credentials_loader
    if _credentials_loader is None:
        _credentials_loader = CredentialsLoader()
    return _credentials_loader

def load_credentials_to_env(db_type: str = None):
    """Load credentials and set environment variables"""
    loader = get_credentials_loader()
    loader.set_environment_variables(db_type)

def get_db_credentials(db_type: str = None) -> Dict[str, Any]:
    """Get database credentials"""
    loader = get_credentials_loader()
    return loader.get_database_config(db_type)

# Backwards compatibility functions
def get_postgresql_credentials() -> Dict[str, Any]:
    """Get PostgreSQL credentials"""
    return get_db_credentials('postgresql')

def get_sqlite_credentials() -> Dict[str, Any]:
    """Get SQLite credentials"""
    return get_db_credentials('sqlite')