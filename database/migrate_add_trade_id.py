#!/usr/bin/env python3
"""
Migration script to add trade_id column and populate existing records
"""

import hashlib
import coolname
import random
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

def generate_trade_id(scrape_date, strategy_type, tab_name, ticker, trigger_price, strike_price):
    """
    Generate a human-readable 3-word trade_id using coolname library.
    
    Args:
        scrape_date: Date when data was scraped
        strategy_type: Type of strategy (Bear Call, Bull Put, etc.)
        tab_name: Risk level and expiry category
        ticker: Stock ticker symbol
        trigger_price: Price that triggers the strategy
        strike_price: Strike prices for the option spread
    
    Returns:
        str: Human-readable trade ID like 'certain-magpie-dancing'
    """
    # Convert all inputs to strings and handle None values
    components = [
        str(scrape_date) if scrape_date is not None else '',
        str(strategy_type) if strategy_type is not None else '',
        str(tab_name) if tab_name is not None else '',
        str(ticker) if ticker is not None else '',
        str(trigger_price) if trigger_price is not None else '',
        str(strike_price) if strike_price is not None else ''
    ]
    
    # Join components with delimiter
    combined_string = '|'.join(components)
    
    # Generate hash and use as seed for reproducible results
    hash_value = hashlib.sha256(combined_string.encode('utf-8')).hexdigest()
    hash_seed = int(hash_value[:8], 16)
    
    # Set random seed for deterministic results
    random.seed(hash_seed)
    
    # Generate 3-word coolname
    trade_id = '-'.join(coolname.generate(3))
    
    return trade_id

def add_trade_id_column():
    """Add trade_id column to existing table"""
    db_conn = get_db_connection()
    
    try:
        # Check if column already exists
        if db_conn.config.is_postgresql():
            check_query = """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'option_strategies' 
                    AND column_name = 'trade_id'
                )
            """
        else:
            check_query = "PRAGMA table_info(option_strategies)"
        
        result = db_conn.execute_query(check_query)
        
        if db_conn.config.is_postgresql():
            column_exists = result[0][0] if result else False
        else:
            column_exists = any('trade_id' in str(row) for row in result)
        
        if column_exists:
            logger.info("trade_id column already exists")
            return True
        
        # Add the column
        logger.info("Adding trade_id column...")
        if db_conn.config.is_postgresql():
            alter_query = "ALTER TABLE option_strategies ADD COLUMN trade_id TEXT"
        else:
            alter_query = "ALTER TABLE option_strategies ADD COLUMN trade_id TEXT"
        
        db_conn.execute_command(alter_query)
        
        # Add unique constraint (PostgreSQL)
        if db_conn.config.is_postgresql():
            unique_query = "ALTER TABLE option_strategies ADD CONSTRAINT unique_trade_id UNIQUE (trade_id)"
            try:
                db_conn.execute_command(unique_query)
                logger.info("Added unique constraint to trade_id")
            except Exception as e:
                logger.warning(f"Could not add unique constraint: {e}")
        
        # Add index
        if db_conn.config.is_postgresql():
            index_query = "CREATE INDEX IF NOT EXISTS idx_trade_id ON option_strategies (trade_id)"
        else:
            index_query = "CREATE INDEX IF NOT EXISTS idx_trade_id ON option_strategies (trade_id)"
        
        db_conn.execute_command(index_query)
        logger.info("Added index on trade_id column")
        
        return True
        
    except Exception as e:
        logger.error(f"Error adding trade_id column: {e}")
        return False

def populate_existing_trade_ids():
    """Populate trade_id for existing records"""
    db_conn = get_db_connection()
    
    try:
        # Get all records that don't have trade_id
        logger.info("Fetching records without trade_id...")
        select_query = """
            SELECT id, scrape_date, strategy_type, tab_name, ticker, trigger_price, strike_price
            FROM option_strategies 
            WHERE trade_id IS NULL
        """
        
        records = db_conn.execute_query(select_query)
        logger.info(f"Found {len(records)} records to update")
        
        if not records:
            logger.info("No records need trade_id updates")
            return True
        
        # Generate trade_ids for each record
        updates = []
        trade_ids_seen = set()
        duplicates = 0
        
        for record in records:
            record_id, scrape_date, strategy_type, tab_name, ticker, trigger_price, strike_price = record
            
            # Generate trade_id
            trade_id = generate_trade_id(
                scrape_date, strategy_type, tab_name, 
                ticker, trigger_price, strike_price
            )
            
            # Check for duplicates (should be very rare with 3-word combinations)
            if trade_id in trade_ids_seen:
                duplicates += 1
                logger.warning(f"Duplicate trade_id detected: {trade_id} for record {record_id}")
                # Add record ID to make it unique
                trade_id = f"{trade_id}-{record_id}"
            
            trade_ids_seen.add(trade_id)
            updates.append((trade_id, record_id))
        
        logger.info(f"Generated {len(updates)} trade_ids ({duplicates} duplicates resolved)")
        
        # Update records in batches
        batch_size = 100
        total_updated = 0
        
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i + batch_size]
            
            # Prepare batch update
            update_query = "UPDATE option_strategies SET trade_id = %s WHERE id = %s"
            if db_conn.config.is_sqlite():
                update_query = "UPDATE option_strategies SET trade_id = ? WHERE id = ?"
            
            updated_count = db_conn.execute_many(update_query, batch)
            total_updated += updated_count
            
            logger.info(f"Updated batch {i//batch_size + 1}: {updated_count} records")
        
        logger.info(f"Successfully updated {total_updated} records with trade_ids")
        
        # Verify the updates
        verify_query = "SELECT COUNT(*) FROM option_strategies WHERE trade_id IS NOT NULL"
        result = db_conn.execute_query(verify_query)
        count_with_trade_id = result[0][0] if result else 0
        
        total_query = "SELECT COUNT(*) FROM option_strategies"
        result = db_conn.execute_query(total_query)
        total_count = result[0][0] if result else 0
        
        logger.info(f"Verification: {count_with_trade_id}/{total_count} records have trade_ids")
        
        return True
        
    except Exception as e:
        logger.error(f"Error populating trade_ids: {e}")
        return False

def run_migration():
    """Run the complete migration"""
    logger.info("Starting trade_id migration...")
    
    # Test database connection
    db_conn = get_db_connection()
    if not db_conn.test_connection():
        logger.error("Cannot connect to database")
        return False
    
    logger.info(f"Connected to {db_conn.config.db_type.upper()} database")
    
    # Step 1: Add column
    if not add_trade_id_column():
        logger.error("Failed to add trade_id column")
        return False
    
    # Step 2: Populate existing records
    if not populate_existing_trade_ids():
        logger.error("Failed to populate existing trade_ids")
        return False
    
    logger.info("Migration completed successfully!")
    return True

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)