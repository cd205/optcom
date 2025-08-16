"""
Database configuration and connection utilities
Supports both SQLite (for development/fallback) and PostgreSQL (production)
"""

import os
import sqlite3
import psycopg2
import pandas as pd
import logging
import sys
from contextlib import contextmanager
from typing import Optional, Union, Dict, Any

# Add config directory to path for credentials loader
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config'))

try:
    from credentials_loader import get_credentials_loader, load_credentials_to_env
    CREDENTIALS_AVAILABLE = True
except ImportError:
    CREDENTIALS_AVAILABLE = False

logger = logging.getLogger(__name__)

class DatabaseConfig:
    """Database configuration management with secure credentials"""
    
    def __init__(self):
        self.db_type = os.getenv('DB_TYPE', 'sqlite').lower()
        
        # Try to load from credentials file first, then fall back to environment variables
        if CREDENTIALS_AVAILABLE:
            try:
                credentials_loader = get_credentials_loader()
                # Set environment variables from credentials if not already set
                if not os.getenv('DB_PASSWORD'):
                    credentials_loader.set_environment_variables(self.db_type)
                
                if self.db_type == 'postgresql':
                    pg_creds = credentials_loader.get_postgresql_config()
                    self.pg_config = {
                        'host': pg_creds['host'],
                        'port': int(pg_creds['port']),
                        'database': pg_creds['database'],
                        'user': pg_creds['user'],
                        'password': pg_creds['password']
                    }
                else:
                    sqlite_creds = credentials_loader.get_sqlite_config()
                    self.sqlite_path = sqlite_creds['path']
                    
                logger.debug("Using credentials from secure credentials file")
                
            except Exception as e:
                logger.warning(f"Could not load secure credentials: {e}. Falling back to environment variables.")
                self._load_from_env()
        else:
            logger.warning("Credentials loader not available. Using environment variables.")
            self._load_from_env()
    
    def _load_from_env(self):
        """Load configuration from environment variables (fallback)"""
        # PostgreSQL configuration
        self.pg_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', '5432')),
            'database': os.getenv('DB_NAME', 'option_strategies'),
            'user': os.getenv('DB_USER', 'optcom-user'),
            'password': os.getenv('DB_PASSWORD')
        }
        
        # SQLite configuration (fallback)
        self.sqlite_path = os.getenv('SQLITE_DB_PATH', 
                                   os.path.join(os.path.dirname(__file__), 'option_strategies.db'))
    
    def get_connection_string(self) -> str:
        """Get connection string for the configured database"""
        if self.db_type == 'postgresql':
            if not self.pg_config['password']:
                raise ValueError("PostgreSQL password not set in DB_PASSWORD environment variable")
            return f"postgresql://{self.pg_config['user']}:{self.pg_config['password']}@{self.pg_config['host']}:{self.pg_config['port']}/{self.pg_config['database']}"
        else:
            return f"sqlite:///{self.sqlite_path}"
    
    def is_postgresql(self) -> bool:
        """Check if using PostgreSQL"""
        return self.db_type == 'postgresql'
    
    def is_sqlite(self) -> bool:
        """Check if using SQLite"""
        return self.db_type == 'sqlite'

class DatabaseConnection:
    """Database connection manager with support for both SQLite and PostgreSQL"""
    
    def __init__(self, config: Optional[DatabaseConfig] = None):
        self.config = config or DatabaseConfig()
        
    @contextmanager
    def get_connection(self):
        """Get database connection with automatic cleanup"""
        conn = None
        try:
            if self.config.is_postgresql():
                conn = psycopg2.connect(**self.config.pg_config)
            else:
                conn = sqlite3.connect(self.config.sqlite_path)
            
            yield conn
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database connection error: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()
    
    def get_cursor(self, conn):
        """Get database cursor"""
        return conn.cursor()
    
    def execute_query(self, query: str, params: tuple = None) -> list:
        """Execute a SELECT query and return results"""
        with self.get_connection() as conn:
            cursor = self.get_cursor(conn)
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            return cursor.fetchall()
    
    def execute_query_df(self, query: str, params: tuple = None) -> pd.DataFrame:
        """Execute a SELECT query and return results as DataFrame"""
        with self.get_connection() as conn:
            if params:
                return pd.read_sql_query(query, conn, params=params)
            else:
                return pd.read_sql_query(query, conn)
    
    def execute_command(self, command: str, params: tuple = None) -> int:
        """Execute INSERT/UPDATE/DELETE command and return affected rows"""
        with self.get_connection() as conn:
            cursor = self.get_cursor(conn)
            
            if params:
                cursor.execute(command, params)
            else:
                cursor.execute(command)
            
            conn.commit()
            return cursor.rowcount
    
    def execute_many(self, command: str, params_list: list) -> int:
        """Execute command with multiple parameter sets"""
        with self.get_connection() as conn:
            cursor = self.get_cursor(conn)
            cursor.executemany(command, params_list)
            conn.commit()
            return cursor.rowcount
    
    def test_connection(self) -> bool:
        """Test database connection"""
        try:
            with self.get_connection() as conn:
                cursor = self.get_cursor(conn)
                
                if self.config.is_postgresql():
                    cursor.execute("SELECT version();")
                else:
                    cursor.execute("SELECT sqlite_version();")
                
                version = cursor.fetchone()
                logger.info(f"Database connection successful: {version[0]}")
                return True
                
        except Exception as e:
            logger.error(f"Database connection failed: {str(e)}")
            return False
    
    def get_table_info(self, table_name: str = 'option_strategies') -> list:
        """Get table structure information"""
        if self.config.is_postgresql():
            query = """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = %s
                ORDER BY ordinal_position
            """
            return self.execute_query(query, (table_name,))
        else:
            query = f"PRAGMA table_info({table_name})"
            return self.execute_query(query)
    
    def table_exists(self, table_name: str = 'option_strategies') -> bool:
        """Check if table exists"""
        try:
            if self.config.is_postgresql():
                query = """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = %s
                    )
                """
                result = self.execute_query(query, (table_name,))
                return result[0][0] if result else False
            else:
                query = """
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name = ?
                """
                result = self.execute_query(query, (table_name,))
                return len(result) > 0
                
        except Exception as e:
            logger.error(f"Error checking table existence: {str(e)}")
            return False

# Global database connection instance
db_connection = DatabaseConnection()

def get_db_connection():
    """Get the global database connection instance"""
    return db_connection

def setup_database(db_path: Optional[str] = None) -> bool:
    """
    Create database and tables if they don't exist
    Compatible with both SQLite and PostgreSQL
    """
    try:
        # For backwards compatibility, if db_path is provided, use SQLite
        if db_path:
            config = DatabaseConfig()
            config.db_type = 'sqlite'
            config.sqlite_path = db_path
            conn_manager = DatabaseConnection(config)
        else:
            conn_manager = get_db_connection()
        
        # Test connection first
        if not conn_manager.test_connection():
            logger.error("Cannot connect to database")
            return False
        
        # Check if table exists
        if conn_manager.table_exists():
            logger.info("Database table already exists")
            return True
        
        # Create table based on database type
        if conn_manager.config.is_postgresql():
            # Use the schema file for PostgreSQL
            schema_path = os.path.join(os.path.dirname(__file__), 'postgresql_schema.sql')
            if os.path.exists(schema_path):
                with open(schema_path, 'r') as f:
                    schema_sql = f.read()
                
                with conn_manager.get_connection() as conn:
                    cursor = conn_manager.get_cursor(conn)
                    cursor.execute(schema_sql)
                    conn.commit()
                    
                logger.info("PostgreSQL database schema created")
            else:
                logger.error(f"Schema file not found: {schema_path}")
                return False
        else:
            # SQLite table creation (existing logic)
            create_table_sql = '''
            CREATE TABLE IF NOT EXISTS option_strategies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scrape_date DATETIME,
                strategy_type TEXT,
                tab_name TEXT,
                ticker TEXT,
                er INTEGER,
                trigger_price TEXT,
                strike_price TEXT,
                strike_buy FLOAT,
                strike_sell FLOAT,
                estimated_premium FLOAT,
                last_price_when_checked FLOAT,
                timestamp_of_price_when_last_checked FLOAT,
                item_id TEXT,
                options_expiry_date TEXT,
                date_info TEXT,
                timestamp_of_trigger DATETIME, 
                strategy_status TEXT,    
                price_when_triggered FLOAT,
                price_when_order_placed FLOAT,
                premium_at_order FLOAT,   
                premium_when_last_checked FLOAT,
                timestamp_of_order DATETIME
            )
            '''
            
            index_queries = [
                'CREATE INDEX IF NOT EXISTS idx_strategy_type ON option_strategies (strategy_type)',
                'CREATE INDEX IF NOT EXISTS idx_ticker ON option_strategies (ticker)',
                'CREATE INDEX IF NOT EXISTS idx_scrape_date ON option_strategies (scrape_date)'
            ]
            
            with conn_manager.get_connection() as conn:
                cursor = conn_manager.get_cursor(conn)
                cursor.execute(create_table_sql)
                
                for index_query in index_queries:
                    cursor.execute(index_query)
                
                conn.commit()
                
            logger.info("SQLite database created")
        
        return True
        
    except Exception as e:
        logger.error(f"Error setting up database: {str(e)}")
        return False