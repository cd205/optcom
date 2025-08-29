"""
Database utilities for the trading workflow
Extracted from notebook functionality for reusability
"""
import os
import json
import psycopg2
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

def load_database_credentials(config_path: str = None) -> dict:
    """
    Load PostgreSQL database credentials from JSON file
    
    Args:
        config_path: Path to credentials.json file
        
    Returns:
        dict: PostgreSQL credentials
        
    Raises:
        FileNotFoundError: If credentials file doesn't exist
        KeyError: If database credentials are missing
    """
    if config_path is None:
        # Try to find the credentials file
        possible_paths = [
            '../config/credentials.json',
            '../../config/credentials.json',
            '/home/chris_s_dodd/optcom-1/config/credentials.json'
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                config_path = path
                break
        
        if config_path is None:
            raise FileNotFoundError("Could not find credentials.json file")
    
    try:
        with open(config_path, 'r') as f:
            creds = json.load(f)
        
        pg_creds = creds['database']['postgresql']
        logger.info("✅ Database credentials loaded successfully")
        return pg_creds
        
    except FileNotFoundError:
        logger.error(f"Credentials file not found: {config_path}")
        raise
    except KeyError as e:
        logger.error(f"Database credentials missing in config: {e}")
        raise

def connect_to_database(pg_creds: Optional[dict] = None) -> Tuple[Optional[psycopg2.extensions.connection], Optional[psycopg2.extensions.cursor]]:
    """
    Connect to the PostgreSQL database
    
    Args:
        pg_creds: PostgreSQL credentials dict. If None, loads from default config
        
    Returns:
        tuple: (connection, cursor) or (None, None) on failure
    """
    if pg_creds is None:
        try:
            pg_creds = load_database_credentials()
        except Exception as e:
            logger.error(f"Failed to load database credentials: {e}")
            return None, None
    
    try:
        conn = psycopg2.connect(
            host=pg_creds['host'],
            port=pg_creds['port'],
            database=pg_creds['database'],
            user=pg_creds['user'],
            password=pg_creds['password']
        )
        cursor = conn.cursor()
        
        # Verify the database has the required table
        cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'option_strategies')")
        if not cursor.fetchone()[0]:
            logger.error("PostgreSQL database does not contain the option_strategies table")
            conn.close()
            return None, None
            
        logger.info(f"✅ Connected to PostgreSQL: {pg_creds['host']}")
        return conn, cursor
        
    except Exception as e:
        logger.error(f"Error connecting to PostgreSQL database: {e}")
        return None, None

def verify_scraped_data(cursor: psycopg2.extensions.cursor, hours_back: int = 1) -> int:
    """
    Verify that scraped data exists in the database within the specified time window
    
    Args:
        cursor: Database cursor
        hours_back: How many hours back to check for data
        
    Returns:
        int: Number of records found in the time window
    """
    try:
        cursor.execute("""
            SELECT COUNT(*) 
            FROM option_strategies 
            WHERE scrape_date::timestamp >= NOW() - INTERVAL '%s hour'
        """, (hours_back,))
        
        count = cursor.fetchone()[0]
        logger.info(f"Found {count} records in the last {hours_back} hour(s)")
        return count
        
    except Exception as e:
        logger.error(f"Error verifying scraped data: {e}")
        return 0

def check_data_freshness(cursor: psycopg2.extensions.cursor, target_date: str = None) -> Tuple[bool, dict]:
    """
    Check if fresh scraper data exists for a specific date
    
    Args:
        cursor: Database cursor
        target_date: Date to check (YYYY-MM-DD format). If None, uses today
        
    Returns:
        tuple: (data_is_fresh, details_dict)
            - data_is_fresh: True if fresh data exists for target date
            - details_dict: Contains counts, latest_scrape, target_date info
    """
    try:
        if target_date is None:
            from datetime import date
            target_date = date.today().strftime('%Y-%m-%d')
        
        # Check for records on the target date
        cursor.execute("""
            SELECT COUNT(*) 
            FROM option_strategies 
            WHERE scrape_date::date = %s
        """, (target_date,))
        
        same_day_count = cursor.fetchone()[0]
        
        # Get latest scrape date
        cursor.execute("SELECT MAX(scrape_date::date) FROM option_strategies")
        latest_scrape_date = cursor.fetchone()[0]
        
        # Get count by strategy for target date
        cursor.execute("""
            SELECT strategy_type, COUNT(*) as count 
            FROM option_strategies 
            WHERE scrape_date::date = %s
            GROUP BY strategy_type
        """, (target_date,))
        
        strategy_counts = cursor.fetchall()
        
        # Data is fresh if we have records from the target date
        data_is_fresh = same_day_count > 0
        
        details = {
            'target_date': target_date,
            'same_day_count': same_day_count,
            'latest_scrape_date': str(latest_scrape_date) if latest_scrape_date else None,
            'strategy_counts': strategy_counts,
            'data_is_fresh': data_is_fresh
        }
        
        logger.info(f"Data freshness check for {target_date}: {same_day_count} records found")
        if data_is_fresh:
            logger.info(f"✅ Fresh data exists for {target_date}")
        else:
            logger.info(f"❌ No fresh data for {target_date}, latest data from {latest_scrape_date}")
        
        return data_is_fresh, details
        
    except Exception as e:
        logger.error(f"Error checking data freshness: {e}")
        return False, {'error': str(e)}

def get_database_summary(cursor: psycopg2.extensions.cursor) -> dict:
    """
    Get summary statistics about the database
    
    Args:
        cursor: Database cursor
        
    Returns:
        dict: Summary statistics
    """
    try:
        # Total records
        cursor.execute("SELECT COUNT(*) FROM option_strategies")
        total_records = cursor.fetchone()[0]
        
        # Records by strategy type (last 24 hours)
        cursor.execute("""
            SELECT strategy_type, tab_name, COUNT(*) as count 
            FROM option_strategies 
            WHERE scrape_date::timestamp >= NOW() - INTERVAL '24 hour' 
            GROUP BY strategy_type, tab_name
        """)
        recent_by_strategy = cursor.fetchall()
        
        # Latest scrape time
        cursor.execute("SELECT MAX(scrape_date::timestamp) FROM option_strategies")
        latest_scrape = cursor.fetchone()[0]
        
        summary = {
            'total_records': total_records,
            'recent_by_strategy': recent_by_strategy,
            'latest_scrape': latest_scrape
        }
        
        logger.info(f"Database summary: {total_records} total records, latest scrape: {latest_scrape}")
        return summary
        
    except Exception as e:
        logger.error(f"Error getting database summary: {e}")
        return {}

def close_database_connection(conn: psycopg2.extensions.connection, cursor: psycopg2.extensions.cursor):
    """
    Safely close database connection and cursor
    
    Args:
        conn: Database connection
        cursor: Database cursor
    """
    try:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        logger.info("Database connection closed")
    except Exception as e:
        logger.error(f"Error closing database connection: {e}")