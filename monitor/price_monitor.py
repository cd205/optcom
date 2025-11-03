import pandas as pd
import numpy as np
from datetime import datetime, date
import time
import logging
import os
import sys
import argparse

# Import the IBKR data provider
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from monitor.ibkr_integration import IBKRDataProvider

# Import the new database configuration
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'database'))
from database_config import get_db_connection

# Set up logging directory
log_dir = os.path.join(os.path.dirname(__file__), '..', 'output', 'logs')
os.makedirs(log_dir, exist_ok=True)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, "price_monitor.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

def get_todays_strategies():
    """
    Query today's option strategies from the database
    Uses the new database configuration system
    
    Returns:
    pandas.DataFrame: DataFrame with today's strategies
    """
    try:
        # Get database connection
        db_conn = get_db_connection()
        
        # Test connection
        if not db_conn.test_connection():
            logger.error("Cannot connect to database. Check your configuration.")
            return pd.DataFrame()
        
        # Get today's date
        today = date.today().isoformat()
        
        # Query for today's entries - use appropriate syntax for database type
        if db_conn.config.is_postgresql():
            query = """
                SELECT * FROM option_strategies 
                WHERE scrape_date::text LIKE %s
                ORDER BY strategy_type, tab_name
            """
            df = db_conn.execute_query_df(query, (f"{today}%",))
        else:
            query = """
                SELECT * FROM option_strategies 
                WHERE scrape_date LIKE ?
                ORDER BY strategy_type, tab_name
            """
            df = db_conn.execute_query_df(query, (f"{today}%",))
        
        # Check if we have data for today
        if len(df) == 0:
            logger.warning(f"No strategy data found for today ({today})")
            return pd.DataFrame()   # comment if block below 
        
        # # Uncomment below to run for data that wasn't scraped today
            # # Fallback to most recent data if no data for today
            # query = """
            #     SELECT * FROM option_strategies 
            #     WHERE scrape_date = (SELECT MAX(scrape_date) FROM option_strategies)
            #     ORDER BY strategy_type, tab_name
            # """
            # df = db_conn.execute_query_df(query)
            
            # if len(df) > 0:
            #     latest_date = df['scrape_date'].iloc[0].split('T')[0]
            #     logger.info(f"Using most recent data from {latest_date} instead")
            # else:
            #     logger.error("No data found in the database")
            #     return pd.DataFrame()
        
        # Add 'triggered' column initialized to None and 'price_when_triggered' column for in-memory tracking
        df['triggered'] = None
        df['price_when_triggered'] = None
        
        logger.info(f"Loaded {len(df)} strategy records")
        
        return df
        
    except Exception as e:
        logger.error(f"Error querying database: {str(e)}")
        return pd.DataFrame()

def clean_price_string(price_str):
    """
    Convert price string to float
    
    Example inputs: "$123.45", "123.45", "$123", etc.
    """
    if pd.isna(price_str) or price_str == 'N/A':
        return None
        
    # Remove $ and any commas
    price_str = str(price_str).replace('$', '').replace(',', '')
    
    try:
        return float(price_str)
    except ValueError:
        logger.warning(f"Could not convert '{price_str}' to float")
        return None

def update_triggered_strategy_in_db(strategy_id, price_when_triggered):
    """
    Update a strategy in the database to mark it as triggered,
    but only if the strategy_status, price_when_triggered, and timestamp_of_trigger fields are empty
    Uses the new database configuration system
    
    Parameters:
    strategy_id (int): ID of the strategy to update
    price_when_triggered (float): Current price of the underlying
    
    Returns:
    bool: True if update was successful, False otherwise
    """
    try:
        # Get database connection
        db_conn = get_db_connection()
        
        # For SQLite, check if we need to add columns to the table
        if db_conn.config.is_sqlite():
            table_info = db_conn.get_table_info()
            columns = [column[1] for column in table_info]  # SQLite format
            
            # Add columns if they don't exist (SQLite only)
            if 'timestamp_of_trigger' not in columns:
                logger.info("Adding timestamp_of_trigger column to option_strategies table")
                db_conn.execute_command("ALTER TABLE option_strategies ADD COLUMN timestamp_of_trigger TEXT")
                
            if 'strategy_status' not in columns:
                logger.info("Adding strategy_status column to option_strategies table")
                db_conn.execute_command("ALTER TABLE option_strategies ADD COLUMN strategy_status TEXT")
                
            if 'price_when_triggered' not in columns:
                logger.info("Adding price_when_triggered column to option_strategies table")
                db_conn.execute_command("ALTER TABLE option_strategies ADD COLUMN price_when_triggered REAL")
        
        # First query to check if any of the fields already have values
        if db_conn.config.is_postgresql():
            check_query = """
                SELECT strategy_status, price_when_triggered, timestamp_of_trigger
                FROM option_strategies 
                WHERE id = %s
            """
        else:
            check_query = """
                SELECT strategy_status, price_when_triggered, timestamp_of_trigger
                FROM option_strategies 
                WHERE id = ?
            """
        
        existing_data = db_conn.execute_query(check_query, (strategy_id,))
        
        # Check if any of the fields already have values
        if existing_data:
            status, price, timestamp = existing_data[0]
            
            if status is not None or price is not None or timestamp is not None:
                logger.info(f"Strategy ID {strategy_id} already has trigger data, not updating")
                return False
        
        # If we get here, we can update the record
        current_timestamp = datetime.now().isoformat()
        
        if db_conn.config.is_postgresql():
            update_query = """
                UPDATE option_strategies 
                SET strategy_status = %s, timestamp_of_trigger = %s, price_when_triggered = %s
                WHERE id = %s
            """
        else:
            update_query = """
                UPDATE option_strategies 
                SET strategy_status = ?, timestamp_of_trigger = ?, price_when_triggered = ?
                WHERE id = ?
            """
        
        rows_affected = db_conn.execute_command(
            update_query, 
            ('triggered', current_timestamp, price_when_triggered, strategy_id)
        )
        
        if rows_affected > 0:
            logger.info(f"Updated strategy ID {strategy_id} in database as triggered")
            return True
        else:
            logger.warning(f"No rows updated for strategy ID {strategy_id}")
            return False
        
    except Exception as e:
        logger.error(f"Error updating strategy in database: {str(e)}")
        return False

def get_last_price_from_database(ticker):
    """
    Get the most recent price for a ticker from the database
    Uses the new database configuration system
    
    Parameters:
    ticker (str): Ticker symbol
    
    Returns:
    float: Last known price, or None if not found
    """
    try:
        # Get database connection
        db_conn = get_db_connection()
        
        # Query for the most recent price check for this ticker
        if db_conn.config.is_postgresql():
            query = """
                SELECT last_price_when_checked 
                FROM option_strategies 
                WHERE ticker = %s 
                AND last_price_when_checked IS NOT NULL
                ORDER BY timestamp_of_price_when_last_checked DESC 
                LIMIT 1
            """
        else:
            query = """
                SELECT last_price_when_checked 
                FROM option_strategies 
                WHERE ticker = ? 
                AND last_price_when_checked IS NOT NULL
                ORDER BY timestamp_of_price_when_last_checked DESC 
                LIMIT 1
            """
        
        result = db_conn.execute_query(query, (ticker,))
        
        if result and len(result) > 0:
            price = result[0][0]
            # Check if the price is valid (not None and not NaN)
            if price is not None and not pd.isna(price):
                logger.info(f"Found last known price for {ticker} from database: ${price:.2f}")
                return float(price)
            else:
                logger.warning(f"Invalid price found in database for {ticker}: {price}")
                return None
        else:
            logger.warning(f"No last known price found in database for {ticker}")
            return None
            
    except Exception as e:
        logger.error(f"Error getting last price from database for {ticker}: {str(e)}")
        return None

def update_price_check_info(strategy_id, current_price):
    """
    Update the last_price_when_checked and timestamp_of_price_when_last_checked columns
    Uses the new database configuration system
    
    Parameters:
    strategy_id (int): ID of the strategy to update
    current_price (float): Current price of the underlying
    
    Returns:
    bool: True if update was successful, False otherwise
    """
    try:
        # Skip update if price is None or NaN
        if current_price is None or pd.isna(current_price):
            logger.warning(f"Skipping price update for strategy ID {strategy_id} - invalid price: {current_price}")
            return False
        
        # Get database connection
        db_conn = get_db_connection()
        
        # Set the current timestamp
        current_timestamp = datetime.now().isoformat()
        
        # Update the record using appropriate syntax
        if db_conn.config.is_postgresql():
            update_query = """
                UPDATE option_strategies 
                SET last_price_when_checked = %s, timestamp_of_price_when_last_checked = %s
                WHERE id = %s
            """
        else:
            update_query = """
                UPDATE option_strategies 
                SET last_price_when_checked = ?, timestamp_of_price_when_last_checked = ?
                WHERE id = ?
            """
        
        rows_affected = db_conn.execute_command(
            update_query, 
            (current_price, current_timestamp, strategy_id)
        )
        
        if rows_affected > 0:
            logger.info(f"Updated price check info for strategy ID {strategy_id} in database - Price: {current_price}")
            return True
        else:
            logger.warning(f"No rows updated for price check info for strategy ID {strategy_id}")
            return False
        
    except Exception as e:
        logger.error(f"Error updating price check info in database: {str(e)}")
        return False

def monitor_prices(ibkr_host='127.0.0.1', ibkr_port=4002, check_interval=60, max_runtime=None, output_dir=None):
    """
    Monitor prices for option strategies
    Uses the new database configuration system
    
    Parameters:
    ibkr_host (str): IB Gateway host
    ibkr_port (int): IB Gateway port (4002 for paper trading, 4001 for live)
    check_interval (int): How often to check prices (in seconds)
    max_runtime (int): Maximum runtime in seconds, or None for indefinite
    output_dir (str): Directory to save output files
    """
    try:
        # Set up output directory
        if output_dir is None:
            output_dir = os.path.join(os.path.dirname(__file__), '..', 'output')
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate random client ID to avoid conflicts
        import random
        client_id = random.randint(100, 9999)
        logger.info(f"Using client ID: {client_id}")
        
        # Initialize IBKR connection with retry logic
        ibkr = IBKRDataProvider(host=ibkr_host, port=ibkr_port, client_id=client_id)
        connection_success = ibkr.connect(max_retries=2)  # Try twice, not three times for faster failure
        
        if not connection_success:
            logger.warning("Failed to connect to IB Gateway after retries.")
            logger.info("Will attempt to use last known prices from database as fallback.")
            # Continue anyway - we can try database fallback
        
        # Get option strategies
        strategies_df = get_todays_strategies()
        
        if strategies_df.empty:
            logger.error("No strategies to monitor. Exiting.")
            ibkr.disconnect()
            return
            
        # Clean trigger price values
        strategies_df['trigger_price_value'] = strategies_df['trigger_price'].apply(clean_price_string)
        
        # Track tickers we need to monitor
        tickers = strategies_df['ticker'].unique()
        valid_tickers = [t for t in tickers if t != 'N/A']
        
        if not valid_tickers:
            logger.error("No valid tickers found in strategies. Exiting.")
            ibkr.disconnect()
            return
            
        logger.info(f"Monitoring {len(valid_tickers)} unique tickers: {', '.join(valid_tickers)}")
        
        # Initialize results storage
        last_prices = {}
        
        # Load existing trigger status from database
        db_conn = get_db_connection()
        
        # Check if the needed columns exist
        table_info = db_conn.get_table_info()
        if db_conn.config.is_postgresql():
            # PostgreSQL format: (column_name, data_type, is_nullable, column_default)
            columns = [column[0] for column in table_info]
        else:
            # SQLite format: (cid, name, type, notnull, dflt_value, pk)
            columns = [column[1] for column in table_info]
        
        has_all_columns = ('strategy_status' in columns and 
                          'price_when_triggered' in columns and 
                          'timestamp_of_trigger' in columns)
        
        # If all columns exist, fetch strategy IDs that are already triggered
        already_triggered = set()
        if has_all_columns:
            query = """
                SELECT id FROM option_strategies 
                WHERE strategy_status = 'triggered'
                AND timestamp_of_trigger IS NOT NULL
            """
            results = db_conn.execute_query(query)
            already_triggered = {row[0] for row in results}
            logger.info(f"Found {len(already_triggered)} strategies that are already triggered")
        
        # Track start time if max_runtime is specified
        start_time = time.time()
        
        # Main monitoring loop
        try:
            while True:
                current_time = datetime.now().strftime("%H:%M:%S")
                logger.info(f"===== Price Check at {current_time} =====")
                
                # Check if we've exceeded max runtime
                if max_runtime and (time.time() - start_time > max_runtime):
                    logger.info(f"Reached maximum runtime of {max_runtime} seconds")
                    break
                
                # Get latest prices for all tickers
                for ticker in valid_tickers:
                    try:
                        price = None
                        price_source = "unknown"
                        
                        if connection_success:
                            # Try to get live/current price first
                            price = ibkr.get_latest_price(ticker)
                            if price is not None:
                                price_source = "live"
                        
                        # If no price yet and we have connection, try close price
                        if price is None and connection_success:
                            price = ibkr.get_last_close_price(ticker)
                            if price is not None:
                                price_source = "close"
                        
                        # Final fallback: get last known price from database
                        if price is None:
                            price = get_last_price_from_database(ticker)
                            if price is not None:
                                price_source = "database"
                        
                        if price is not None:
                            last_prices[ticker] = price
                            logger.info(f"{ticker}: ${price:.2f} ({price_source} price)")
                        else:
                            logger.warning(f"Could not get any price for {ticker} from any source")
                    except Exception as e:
                        logger.error(f"Error getting price for {ticker}: {str(e)}")
                
                # Reset triggered column but keep price_when_triggered if not changed
                strategies_df['triggered'] = None
                
                # Compare prices to triggers and record current prices
                for idx, row in strategies_df.iterrows():
                    ticker = row['ticker']
                    strategy_type = row['strategy_type']
                    strategy_id = row['id']
                    
                    if ticker not in last_prices:
                        logger.debug(f"No price available for {ticker}, skipping strategy ID {strategy_id}")
                        continue
                        
                    current_price = last_prices[ticker]
                    
                    # Skip if price is None or NaN
                    if current_price is None or pd.isna(current_price):
                        logger.warning(f"Skipping strategy ID {strategy_id} for {ticker} - invalid price: {current_price}")
                        continue
                    
                    # Update the last_price_when_checked and timestamp columns for every check
                    update_price_check_info(strategy_id, current_price)
                    
                    # Skip checking trigger conditions if this strategy is already triggered
                    if strategy_id in already_triggered:
                        logger.debug(f"Skipping strategy ID {strategy_id} as it's already triggered")
                        continue
                    
                    if pd.isna(row['trigger_price_value']):
                        continue
                        
                    price_when_triggered = current_price
                    trigger_price = row['trigger_price_value']
                    
                    # Record the current price in memory
                    strategies_df.at[idx, 'price_when_triggered'] = price_when_triggered
                    
                    # Apply trigger logic based on strategy type
                    trigger_condition_met = False
                    
                    if strategy_type == 'Bear Call' and price_when_triggered > trigger_price:
                        strategies_df.at[idx, 'triggered'] = 1
                        logger.info(f"TRIGGERED: {ticker} {strategy_type} - Price ${price_when_triggered:.2f} > Trigger ${trigger_price:.2f}")
                        trigger_condition_met = True
                    elif strategy_type == 'Bull Put' and price_when_triggered < trigger_price:
                        strategies_df.at[idx, 'triggered'] = 1
                        logger.info(f"TRIGGERED: {ticker} {strategy_type} - Price ${price_when_triggered:.2f} < Trigger ${trigger_price:.2f}")
                        trigger_condition_met = True
                        
                    # If triggered, update the database and add to our already triggered set
                    if trigger_condition_met:
                        if update_triggered_strategy_in_db(strategy_id, price_when_triggered):
                            already_triggered.add(strategy_id)
                
                # # Save current state to CSV for monitoring purposes
                # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                # csv_path = os.path.join(output_dir, f"strategy_monitor_{timestamp}.csv")
                # strategies_df.to_csv(csv_path, index=False)
                # logger.info(f"Saved monitor state to {csv_path}")
                
                # # Also save the latest snapshot with a fixed filename
                # latest_path = os.path.join(output_dir, "latest_strategy_status.csv")
                # strategies_df.to_csv(latest_path, index=False)
                # logger.info(f"Updated latest status file at {latest_path}")
                
                # Wait for next check
                logger.info(f"Waiting {check_interval} seconds until next check...")
                time.sleep(check_interval)
                
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
        
    except Exception as e:
        logger.error(f"Error in price monitoring: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up
        if 'ibkr' in locals():
            ibkr.disconnect()
        
        logger.info("Price monitoring complete")

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Monitor option strategy prices using IBKR data')
    
    # Database configuration is now handled by environment variables
    # No need for --db argument
    parser.add_argument('--host', type=str, default='127.0.0.1',
                        help='IB Gateway host')
    parser.add_argument('--port', type=int, default=4002,
                        help='IB Gateway port (4002 for paper trading, 4001 for live)')
    parser.add_argument('--interval', type=int, default=60,
                        help='Check interval in seconds')
    parser.add_argument('--runtime', type=int, default=None,
                        help='Maximum runtime in seconds (default: run indefinitely)')
    parser.add_argument('--output', type=str, default=None,
                        help='Output directory for CSV files')
    
    return parser.parse_args()

if __name__ == "__main__":
    # Parse command line arguments
    args = parse_arguments()
    
    # Run the monitor
    monitor_prices(
        ibkr_host=args.host,
        ibkr_port=args.port,
        check_interval=args.interval,
        max_runtime=args.runtime,
        output_dir=args.output
    )

# python monitor/price_monitor.py --port 4002 --interval 60
