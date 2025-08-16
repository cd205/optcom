#!/usr/bin/env python3
"""
Fixed data migration script from SQLite to PostgreSQL
Handles the problematic 'INTEGER' column name issue
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

def export_sqlite_data_fixed(sqlite_db_path):
    """Export data from SQLite database with column name fixes"""
    try:
        # Connect to SQLite
        conn = sqlite3.connect(sqlite_db_path)
        
        # Get data with proper column names, handling the 'INTEGER' column issue
        query = """
        SELECT 
            id, scrape_date, strategy_type, tab_name, ticker, 
            er, [INTEGER] as er_integer,  -- Rename problematic column
            trigger_price, strike_price, strike_buy, strike_sell, estimated_premium, 
            last_price_when_checked, timestamp_of_price_when_last_checked, item_id, 
            options_expiry_date, date_info, timestamp_of_trigger, strategy_status, 
            price_when_triggered, price_when_order_placed, premium_at_order, 
            premium_when_last_checked, timestamp_of_order
        FROM option_strategies
        """
        
        df = pd.read_sql_query(query, conn)
        
        # Drop the problematic er_integer column if it's empty/not needed
        if 'er_integer' in df.columns:
            if df['er_integer'].isna().all() or (df['er_integer'] == 0).all():
                logger.info("Dropping empty 'er_integer' column")
                df = df.drop('er_integer', axis=1)
        
        logger.info(f"Exported {len(df)} records from SQLite")
        logger.info(f"Columns: {list(df.columns)}")
        
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

def create_postgresql_schema_fixed(config):
    """Create PostgreSQL schema without problematic columns"""
    try:
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()
        
        # Updated schema without the 'INTEGER' column issue
        schema_sql = """
        -- Drop table if exists
        DROP TABLE IF EXISTS option_strategies;
        
        -- Create the option_strategies table
        CREATE TABLE option_strategies (
            id SERIAL PRIMARY KEY,
            scrape_date TEXT,
            strategy_type TEXT,
            tab_name TEXT,
            ticker TEXT,
            er TEXT,
            trigger_price TEXT,
            strike_price TEXT,
            strike_buy REAL,
            strike_sell REAL,
            estimated_premium REAL,
            last_price_when_checked REAL,
            timestamp_of_price_when_last_checked TEXT,
            item_id TEXT,
            options_expiry_date TEXT,
            date_info TEXT,
            timestamp_of_trigger TEXT,
            strategy_status TEXT,
            price_when_triggered REAL,
            price_when_order_placed REAL,
            premium_at_order REAL,
            premium_when_last_checked REAL,
            timestamp_of_order TEXT
        );
        
        -- Create indexes for performance
        CREATE INDEX IF NOT EXISTS idx_strategy_type ON option_strategies (strategy_type);
        CREATE INDEX IF NOT EXISTS idx_ticker ON option_strategies (ticker);
        CREATE INDEX IF NOT EXISTS idx_scrape_date ON option_strategies (scrape_date);
        CREATE INDEX IF NOT EXISTS idx_strategy_status ON option_strategies (strategy_status);
        CREATE INDEX IF NOT EXISTS idx_timestamp_trigger ON option_strategies (timestamp_of_trigger);
        """
        
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

def import_data_to_postgresql_fixed(df, config):
    """Import data to PostgreSQL with fixed column handling"""
    try:
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()
        
        # Get the expected columns (excluding id which is auto-increment)
        expected_columns = [
            'scrape_date', 'strategy_type', 'tab_name', 'ticker', 'er',
            'trigger_price', 'strike_price', 'strike_buy', 'strike_sell', 'estimated_premium',
            'last_price_when_checked', 'timestamp_of_price_when_last_checked', 'item_id',
            'options_expiry_date', 'date_info', 'timestamp_of_trigger', 'strategy_status',
            'price_when_triggered', 'price_when_order_placed', 'premium_at_order',
            'premium_when_last_checked', 'timestamp_of_order'
        ]
        
        # Filter dataframe to only include expected columns
        df_insert = df[[col for col in expected_columns if col in df.columns]].copy()
        
        # Handle any missing columns by adding them with NULL values
        for col in expected_columns:
            if col not in df_insert.columns:
                df_insert[col] = None
                logger.info(f"Added missing column '{col}' with NULL values")
        
        # Clean data - replace 'None' strings with actual None values
        numeric_columns = ['strike_buy', 'strike_sell', 'estimated_premium', 
                          'last_price_when_checked', 'price_when_triggered', 
                          'price_when_order_placed', 'premium_at_order', 'premium_when_last_checked']
        
        for col in numeric_columns:
            if col in df_insert.columns:
                # Replace 'None' strings with actual None/NaN
                df_insert[col] = df_insert[col].replace('None', None)
                df_insert[col] = df_insert[col].replace('N/A', None)
                df_insert[col] = df_insert[col].replace('', None)
                
                # Convert to numeric, coercing errors to NaN
                df_insert[col] = pd.to_numeric(df_insert[col], errors='coerce')
        
        # Also clean text columns
        text_columns = ['strategy_type', 'tab_name', 'ticker', 'er', 'trigger_price', 'strike_price', 
                       'item_id', 'options_expiry_date', 'date_info', 'strategy_status']
        
        for col in text_columns:
            if col in df_insert.columns:
                # Replace 'None' with actual None
                df_insert[col] = df_insert[col].replace('None', None)
                df_insert[col] = df_insert[col].replace('N/A', None)
        
        # Reorder columns to match expected order
        df_insert = df_insert[expected_columns]
        
        # Prepare insert statement
        placeholders = ', '.join(['%s'] * len(expected_columns))
        insert_sql = f"""
            INSERT INTO option_strategies ({', '.join(expected_columns)})
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
        backup_path = f"sqlite_backup_fixed_{timestamp}.csv"
        
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
    """Main migration function with fixes"""
    logger.info("Starting FIXED database migration from SQLite to PostgreSQL")
    
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
    
    # Export SQLite data with fixes
    df = export_sqlite_data_fixed(sqlite_db_path)
    if df is None or df.empty:
        logger.warning("No data to migrate or export failed")
        return
    
    # Create PostgreSQL schema
    if not create_postgresql_schema_fixed(pg_config):
        logger.error("Failed to create PostgreSQL schema")
        sys.exit(1)
    
    # Import data
    if not import_data_to_postgresql_fixed(df, pg_config):
        logger.error("Failed to import data to PostgreSQL")
        sys.exit(1)
    
    logger.info("FIXED migration completed successfully!")
    logger.info(f"SQLite backup saved as: {backup_path}")

if __name__ == "__main__":
    main()