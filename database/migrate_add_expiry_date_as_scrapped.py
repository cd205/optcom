#!/usr/bin/env python3
"""
Migration script to add options_expiry_date_as_scrapped column to option_strategies table
"""

import sys
import os
import logging
from datetime import datetime

# Add the current directory to the path to import database config
sys.path.append(os.path.dirname(__file__))

from database_config import get_db_connection

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def add_options_expiry_date_as_scrapped_column():
    """Add options_expiry_date_as_scrapped column to existing table"""
    db_conn = get_db_connection()
    
    try:
        # Check if column already exists
        if db_conn.config.is_postgresql():
            check_query = """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'option_strategies' 
                    AND column_name = 'options_expiry_date_as_scrapped'
                )
            """
        else:
            check_query = "PRAGMA table_info(option_strategies)"
        
        result = db_conn.execute_query(check_query)
        
        if db_conn.config.is_postgresql():
            column_exists = result[0][0] if result else False
        else:
            column_exists = any('options_expiry_date_as_scrapped' in str(row) for row in result)
        
        if column_exists:
            logger.info("options_expiry_date_as_scrapped column already exists")
            return True
        
        # Add the column
        logger.info("Adding options_expiry_date_as_scrapped column...")
        if db_conn.config.is_postgresql():
            alter_query = "ALTER TABLE option_strategies ADD COLUMN options_expiry_date_as_scrapped TEXT"
        else:
            alter_query = "ALTER TABLE option_strategies ADD COLUMN options_expiry_date_as_scrapped TEXT"
        
        db_conn.execute_command(alter_query)
        logger.info("Successfully added options_expiry_date_as_scrapped column")
        
        # Add index for performance (optional but recommended)
        if db_conn.config.is_postgresql():
            index_query = "CREATE INDEX IF NOT EXISTS idx_options_expiry_date_as_scrapped ON option_strategies (options_expiry_date_as_scrapped)"
        else:
            index_query = "CREATE INDEX IF NOT EXISTS idx_options_expiry_date_as_scrapped ON option_strategies (options_expiry_date_as_scrapped)"
        
        db_conn.execute_command(index_query)
        logger.info("Added index on options_expiry_date_as_scrapped column")
        
        # Add comment for documentation (PostgreSQL only)
        if db_conn.config.is_postgresql():
            comment_query = "COMMENT ON COLUMN option_strategies.options_expiry_date_as_scrapped IS 'Original expiry date format as scraped from source'"
            db_conn.execute_command(comment_query)
            logger.info("Added column comment")
        
        return True
        
    except Exception as e:
        logger.error(f"Error adding options_expiry_date_as_scrapped column: {e}")
        return False

def run_migration():
    """Run the complete migration"""
    logger.info("Starting options_expiry_date_as_scrapped column migration...")
    
    # Test database connection
    db_conn = get_db_connection()
    if not db_conn.test_connection():
        logger.error("Cannot connect to database")
        return False
    
    logger.info(f"Connected to {db_conn.config.db_type.upper()} database")
    
    # Add column
    if not add_options_expiry_date_as_scrapped_column():
        logger.error("Failed to add options_expiry_date_as_scrapped column")
        return False
    
    logger.info("Migration completed successfully!")
    return True

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)