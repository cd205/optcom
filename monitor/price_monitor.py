import sqlite3
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

def get_todays_strategies(db_path):
    """
    Query today's option strategies from the database
    
    Parameters:
    db_path (str): Path to the SQLite database file
    
    Returns:
    pandas.DataFrame: DataFrame with today's strategies
    """
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        
        # Get today's date
        today = date.today().isoformat()
        
        # Query for today's entries
        query = f"""
            SELECT * FROM option_strategies 
            WHERE scrape_date LIKE '{today}%'
            ORDER BY strategy_type, tab_name
        """
        
        # Execute query and load into DataFrame
        df = pd.read_sql_query(query, conn)
        
        # Close connection
        conn.close()
        
        # Check if we have data for today
        if len(df) == 0:
            logger.warning(f"No strategy data found for today ({today})")
            return pd.DataFrame()   # comment if bock below 
        
        # # Uncomment below to run for data that wasn;t scraped today
            # # Fallback to most recent data if no data for today
            # conn = sqlite3.connect(db_path)
            # query = """
            #     SELECT * FROM option_strategies 
            #     WHERE scrape_date = (SELECT MAX(scrape_date) FROM option_strategies)
            #     ORDER BY strategy_type, tab_name
            # """
            # df = pd.read_sql_query(query, conn)
            # conn.close()
            
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

def update_triggered_strategy_in_db(db_path, strategy_id, price_when_triggered):
    """
    Update a strategy in the database to mark it as triggered,
    but only if the strategy_status, price_when_triggered, and timestamp_of_trigger fields are empty
    
    Parameters:
    db_path (str): Path to the SQLite database
    strategy_id (int): ID of the strategy to update
    price_when_triggered (float): Current price of the underlying
    
    Returns:
    bool: True if update was successful, False otherwise
    """
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # First check if we need to add the columns to the table
        cursor.execute("PRAGMA table_info(option_strategies)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # Add timestamp_of_trigger column if it doesn't exist
        if 'timestamp_of_trigger' not in columns:
            logger.info("Adding timestamp_of_trigger column to option_strategies table")
            cursor.execute("ALTER TABLE option_strategies ADD COLUMN timestamp_of_trigger TEXT")
            
        # Add strategy_status column if it doesn't exist
        if 'strategy_status' not in columns:
            logger.info("Adding strategy_status column to option_strategies table")
            cursor.execute("ALTER TABLE option_strategies ADD COLUMN strategy_status TEXT")
            
        # Add price_when_triggered column if it doesn't exist    
        if 'price_when_triggered' not in columns:
            logger.info("Adding price_when_triggered column to option_strategies table")
            cursor.execute("ALTER TABLE option_strategies ADD COLUMN price_when_triggered REAL")
        
        # First query to check if any of the fields already have values
        cursor.execute(
            """
            SELECT strategy_status, price_when_triggered, timestamp_of_trigger
            FROM option_strategies 
            WHERE id = ?
            """, 
            (strategy_id,)
        )
        
        existing_data = cursor.fetchone()
        
        # Check if any of the fields already have values
        if existing_data:
            status, price, timestamp = existing_data
            
            if status is not None or price is not None or timestamp is not None:
                logger.info(f"Strategy ID {strategy_id} already has trigger data, not updating")
                conn.close()
                return False
        
        # If we get here, we can update the record
        current_timestamp = datetime.now().isoformat()
        cursor.execute(
            """
            UPDATE option_strategies 
            SET strategy_status = ?, timestamp_of_trigger = ?, price_when_triggered = ?
            WHERE id = ?
            """, 
            ('triggered', current_timestamp, price_when_triggered, strategy_id)
        )
        
        # Commit changes
        conn.commit()
        
        # Get number of rows affected
        rows_affected = cursor.rowcount
        
        # Close connection
        conn.close()
        
        if rows_affected > 0:
            logger.info(f"Updated strategy ID {strategy_id} in database as triggered")
            return True
        else:
            logger.warning(f"No rows updated for strategy ID {strategy_id}")
            return False
        
    except Exception as e:
        logger.error(f"Error updating strategy in database: {str(e)}")
        return False

def monitor_prices(db_path, ibkr_host='127.0.0.1', ibkr_port=7497, check_interval=60, max_runtime=None, output_dir=None):
    """
    Monitor prices for option strategies
    
    Parameters:
    db_path (str): Path to the SQLite database
    ibkr_host (str): IBKR TWS/Gateway host
    ibkr_port (int): IBKR TWS/Gateway port
    check_interval (int): How often to check prices (in seconds)
    max_runtime (int): Maximum runtime in seconds, or None for indefinite
    output_dir (str): Directory to save output files
    """
    try:
        # Set up output directory
        if output_dir is None:
            output_dir = os.path.join(os.path.dirname(__file__), '..', 'output')
        os.makedirs(output_dir, exist_ok=True)
        
        # Initialize IBKR connection
        ibkr = IBKRDataProvider(host=ibkr_host, port=ibkr_port)
        connection_success = ibkr.connect()
        
        if not connection_success:
            logger.error("Failed to connect to IBKR. Exiting.")
            return
        
        # Get option strategies
        strategies_df = get_todays_strategies(db_path)
        
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
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if the needed columns exist
        cursor.execute("PRAGMA table_info(option_strategies)")
        columns = [column[1] for column in cursor.fetchall()]
        has_all_columns = ('strategy_status' in columns and 
                          'price_when_triggered' in columns and 
                          'timestamp_of_trigger' in columns)
        
        # If all columns exist, fetch strategy IDs that are already triggered
        already_triggered = set()
        if has_all_columns:
            cursor.execute(
                """
                SELECT id FROM option_strategies 
                WHERE strategy_status IS NOT NULL 
                OR price_when_triggered IS NOT NULL 
                OR timestamp_of_trigger IS NOT NULL
                """
            )
            already_triggered = {row[0] for row in cursor.fetchall()}
            logger.info(f"Found {len(already_triggered)} strategies that are already triggered")
        
        conn.close()
        
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
                        price = ibkr.get_latest_price(ticker)
                        
                        if price is not None:
                            last_prices[ticker] = price
                            logger.info(f"{ticker}: ${price:.2f}")
                        else:
                            logger.warning(f"Could not get price for {ticker}")
                    except Exception as e:
                        logger.error(f"Error getting price for {ticker}: {str(e)}")
                
                # Reset triggered column but keep price_when_triggered if not changed
                strategies_df['triggered'] = None
                
                # Compare prices to triggers and record current prices
                for idx, row in strategies_df.iterrows():
                    ticker = row['ticker']
                    strategy_type = row['strategy_type']
                    strategy_id = row['id']
                    
                    # Skip if this strategy is already triggered in the database
                    if strategy_id in already_triggered:
                        logger.debug(f"Skipping strategy ID {strategy_id} as it's already triggered")
                        continue
                    
                    if ticker not in last_prices or pd.isna(row['trigger_price_value']):
                        continue
                        
                    price_when_triggered = last_prices[ticker]
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
                        if update_triggered_strategy_in_db(db_path, strategy_id, price_when_triggered):
                            already_triggered.add(strategy_id)
                
                # Save current state to CSV for monitoring purposes
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                csv_path = os.path.join(output_dir, f"strategy_monitor_{timestamp}.csv")
                strategies_df.to_csv(csv_path, index=False)
                logger.info(f"Saved monitor state to {csv_path}")
                
                # Also save the latest snapshot with a fixed filename
                latest_path = os.path.join(output_dir, "latest_strategy_status.csv")
                strategies_df.to_csv(latest_path, index=False)
                logger.info(f"Updated latest status file at {latest_path}")
                
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
    
    parser.add_argument('--db', type=str, default='../database/option_strategies.db',
                        help='Path to SQLite database')
    parser.add_argument('--host', type=str, default='127.0.0.1',
                        help='IBKR TWS/Gateway host')
    parser.add_argument('--port', type=int, default=7497,
                        help='IBKR TWS/Gateway port (7497 for paper, 7496 for live)')
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
        db_path=args.db,
        ibkr_host=args.host,
        ibkr_port=args.port,
        check_interval=args.interval,
        max_runtime=args.runtime,
        output_dir=args.output
    )

#python monitor/price_monitor.py --db database/option_strategies.db --interval 60