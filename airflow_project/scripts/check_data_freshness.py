#!/usr/bin/env python3
"""
Standalone Data Freshness Checker
Quick utility to check if fresh trading data exists for a given date
"""
import os
import sys
import argparse
import logging
from datetime import date, datetime

# Add current directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from database_utils import connect_to_database, close_database_connection, check_data_freshness

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Main function for standalone data freshness checking"""
    parser = argparse.ArgumentParser(description='Check Trading Data Freshness')
    parser.add_argument('--date', type=str, help='Date to check (YYYY-MM-DD format). Defaults to today')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Determine target date
    target_date = args.date if args.date else date.today().strftime('%Y-%m-%d')
    
    logger.info(f"Checking data freshness for: {target_date}")
    
    # Connect to database
    conn, cursor = connect_to_database()
    if not conn or not cursor:
        logger.error("Failed to connect to database")
        return 1
    
    try:
        # Check data freshness
        data_is_fresh, details = check_data_freshness(cursor, target_date)
        
        # Display results
        print(f"\n📊 Data Freshness Report for {target_date}")
        print("=" * 50)
        
        if data_is_fresh:
            print("✅ Status: FRESH DATA AVAILABLE")
            print(f"📈 Records Count: {details['same_day_count']}")
            
            if details['strategy_counts']:
                print("\n📋 Breakdown by Strategy:")
                for strategy, count in details['strategy_counts']:
                    print(f"  • {strategy}: {count} records")
            
            print(f"\n🎯 Recommendation: SKIP SCRAPING - data already exists")
            return 0
            
        else:
            print("❌ Status: NO FRESH DATA")
            print(f"📈 Records for {target_date}: {details['same_day_count']}")
            if details['latest_scrape_date']:
                print(f"📅 Latest Data From: {details['latest_scrape_date']}")
            
            print(f"\n🎯 Recommendation: RUN SCRAPING - fresh data needed")
            return 2  # Exit code 2 indicates scraping needed
            
    except Exception as e:
        logger.error(f"Error checking data freshness: {e}")
        return 1
    finally:
        close_database_connection(conn, cursor)

if __name__ == "__main__":
    exit(main())