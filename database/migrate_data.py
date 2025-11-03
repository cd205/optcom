#!/usr/bin/env python3
"""
Data migration script from SQLite to PostgreSQL
Exports data from option_strategies.db and imports to PostgreSQL
"""

import sqlite3
import psycopg2
import pandas as pd
import os
import sys
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_database_config():
    """Get database configuration from environment variables"""
    config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': os.getenv('DB_PORT', '5432'),
        'database': os.getenv('DB_NAME', 'option_strategies'),
        'user': os.getenv('DB_USER', 'optcom-user'),
        'password': os.getenv('DB_PASSWORD')
    }
    
    if not config['password']:
        logger.error("DB_PASSWORD environment variable not set")
        sys.exit(1)
    
    return config

def export_sqlite_data(sqlite_db_path):
    """Export data from SQLite database"""
    try:
        # Connect to SQLite
        conn = sqlite3.connect(sqlite_db_path)
        
        # Get all data
        df = pd.read_sql_query("SELECT * FROM option_strategies", conn)
        
        logger.info(f"Exported {len(df)} records from SQLite")
        
        conn.close()
        return df
        
    except Exception as e:
        logger.error(f"Error exporting SQLite data: {str(e)}")
        return None

def test_postgresql_connection(config):
    """Test PostgreSQL connection"""
    try:
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()
        
        # Test query
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        logger.info(f"Connected to PostgreSQL: {version[0]}")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Error connecting to PostgreSQL: {str(e)}")
        return False

def create_postgresql_schema(config):
    """Create PostgreSQL schema"""
    try:
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()
        
        # Read schema file
        schema_path = os.path.join(os.path.dirname(__file__), 'postgresql_schema.sql')
        with open(schema_path, 'r') as f:
            schema_sql = f.read()
        
        # Execute schema creation
        cursor.execute(schema_sql)
        conn.commit()
        
        logger.info("PostgreSQL schema created successfully")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Error creating PostgreSQL schema: {str(e)}")
        return False

def import_data_to_postgresql(df, config):
    """Import data to PostgreSQL"""
    try:
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()
        
        # Prepare insert statement
        columns = df.columns.tolist()
        # Remove 'id' column as it's auto-increment
        if 'id' in columns:
            columns.remove('id')
            df_insert = df.drop('id', axis=1)
        else:
            df_insert = df
        
        placeholders = ', '.join(['%s'] * len(columns))
        insert_sql = f"""
            INSERT INTO option_strategies ({', '.join(columns)})
            VALUES ({placeholders})
        """
        
        # Convert DataFrame to list of tuples
        data_tuples = [tuple(row) for row in df_insert.values]
        
        # Execute bulk insert
        cursor.executemany(insert_sql, data_tuples)
        conn.commit()
        
        logger.info(f"Imported {len(data_tuples)} records to PostgreSQL")
        
        # Verify import
        cursor.execute("SELECT COUNT(*) FROM option_strategies")
        count = cursor.fetchone()[0]
        logger.info(f"Total records in PostgreSQL: {count}")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Error importing data to PostgreSQL: {str(e)}")
        return False

def backup_sqlite_data(sqlite_db_path):
    """Create a backup of SQLite data as CSV"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"sqlite_backup_{timestamp}.csv"
        
        # Export to CSV
        conn = sqlite3.connect(sqlite_db_path)
        df = pd.read_sql_query("SELECT * FROM option_strategies", conn)
        df.to_csv(backup_path, index=False)
        conn.close()
        
        logger.info(f"SQLite data backed up to {backup_path}")
        return backup_path
        
    except Exception as e:
        logger.error(f"Error backing up SQLite data: {str(e)}")
        return None

def main():
    """Main migration function"""
    logger.info("Starting database migration from SQLite to PostgreSQL")
    
    # Paths
    sqlite_db_path = os.path.join(os.path.dirname(__file__), 'option_strategies.db')
    
    # Check if SQLite database exists
    if not os.path.exists(sqlite_db_path):
        logger.error(f"SQLite database not found at {sqlite_db_path}")
        sys.exit(1)
    
    # Get PostgreSQL configuration
    pg_config = get_database_config()
    
    # Test PostgreSQL connection
    if not test_postgresql_connection(pg_config):
        logger.error("Cannot connect to PostgreSQL. Check configuration.")
        sys.exit(1)
    
    # Create backup
    backup_path = backup_sqlite_data(sqlite_db_path)
    if not backup_path:
        logger.error("Failed to create backup. Aborting migration.")
        sys.exit(1)
    
    # Export SQLite data
    df = export_sqlite_data(sqlite_db_path)
    if df is None or df.empty:
        logger.warning("No data to migrate or export failed")
        return
    
    # Create PostgreSQL schema
    if not create_postgresql_schema(pg_config):
        logger.error("Failed to create PostgreSQL schema")
        sys.exit(1)
    
    # Import data
    if not import_data_to_postgresql(df, pg_config):
        logger.error("Failed to import data to PostgreSQL")
        sys.exit(1)
    
    logger.info("Migration completed successfully!")
    logger.info(f"SQLite backup saved as: {backup_path}")

if __name__ == "__main__":
    main()