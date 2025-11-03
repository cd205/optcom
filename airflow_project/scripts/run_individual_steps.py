#!/usr/bin/env python3
"""
Individual Step Runner for Debugging
Run any step of the trading workflow independently
"""
import sys
import os
import logging
import argparse
from datetime import date

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import our functions
from options_scraper import run_options_scraper
from trading_monitor import run_trading_monitor
from ib_gateway_utils import IBGatewayManager
from database_utils import connect_to_database, close_database_connection, check_data_freshness

def step1_check_data():
    """Step 1: Check if we have data for today"""
    print("🔍 STEP 1: Checking for today's data...")
    
    conn, cursor = connect_to_database()
    if not conn:
        raise Exception("Failed to connect to database")
    
    try:
        today = date.today().strftime('%Y-%m-%d')
        data_is_fresh, details = check_data_freshness(cursor, today)
        
        if data_is_fresh:
            print(f"✅ Found {details['same_day_count']} records for {today}")
            print("⏩ Data exists - scraping not needed")
            return True, details['same_day_count']
        else:
            print(f"❌ No data found for {today}")
            print("➡️ Scraping is needed")
            return False, 0
            
    finally:
        close_database_connection(conn, cursor)

def step2_run_scraper():
    """Step 2: Run options scraper"""
    print("🚀 STEP 2: Running options scraper...")
    
    print("Starting scraper (this may take 10-15 minutes)...")
    records_scraped = run_options_scraper(test_mode=False, headless=True)
    
    print(f"✅ Scraper completed: {records_scraped} records")
    return records_scraped

def step3_verify_records():
    """Step 3: Verify scraper wrote records"""
    print("✅ STEP 3: Verifying records were written...")
    
    conn, cursor = connect_to_database()
    if not conn:
        raise Exception("Failed to connect to database for verification")
    
    try:
        today = date.today().strftime('%Y-%m-%d')
        data_is_fresh, details = check_data_freshness(cursor, today)
        
        if data_is_fresh and details['same_day_count'] > 0:
            print(f"✅ Verification successful: {details['same_day_count']} records found")
            return details['same_day_count']
        else:
            print("❌ No records found - scraper may have failed")
            return 0
            
    finally:
        close_database_connection(conn, cursor)

def step4_start_gateways():
    """Step 4: Start IB gateways"""
    print("🚪 STEP 4: Starting IB gateways...")
    
    manager = IBGatewayManager()
    
    print("Starting gateways (this may take up to 15 minutes for 2FA)...")
    success = manager.start_gateways()
    
    if success:
        print("✅ Gateways started successfully")
        
        # Show final status
        print("\nFinal gateway status:")
        success, status = manager.check_status()
        print(status)
        return True
    else:
        print("❌ Failed to start gateways")
        return False

def step5_trading_monitor(runtime=300):
    """Step 5: Run trading monitor"""
    print(f"📊 STEP 5: Running trading monitor for {runtime} seconds...")
    
    cycles_completed = run_trading_monitor(
        runtime=runtime,
        cycles=1000,
        port=4002,     # Paper trading port
        allow_market_closed=True,
        interval=60    # 1 minute intervals
    )
    
    print(f"✅ Trading monitor completed: {cycles_completed} cycles")
    return cycles_completed

def main():
    parser = argparse.ArgumentParser(description='Run individual workflow steps')
    parser.add_argument('step', choices=['1', '2', '3', '4', '5'], 
                       help='Step number to run')
    parser.add_argument('--runtime', type=int, default=300,
                       help='Runtime for step 5 (trading monitor) in seconds')
    
    args = parser.parse_args()
    
    try:
        if args.step == '1':
            data_exists, count = step1_check_data()
            print(f"\nResult: {'Data exists' if data_exists else 'No data'} ({count} records)")
            
        elif args.step == '2':
            records = step2_run_scraper()
            print(f"\nResult: {records} records scraped")
            
        elif args.step == '3':
            count = step3_verify_records()
            print(f"\nResult: {count} records verified")
            
        elif args.step == '4':
            success = step4_start_gateways()
            print(f"\nResult: {'Success' if success else 'Failed'}")
            
        elif args.step == '5':
            cycles = step5_trading_monitor(args.runtime)
            print(f"\nResult: {cycles} cycles completed")
            
    except Exception as e:
        logger.error(f"Step {args.step} failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()