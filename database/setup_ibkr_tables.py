#!/usr/bin/env python3
"""
Setup IBKR Position Tracking Tables
Connects to your existing PostgreSQL database and creates the new tables
"""

import sys
import os
import psycopg2
import pandas as pd
import json
from datetime import datetime

# Add config path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'config'))

def load_credentials():
    """Load PostgreSQL credentials from config"""
    credentials_file = os.path.join(os.path.dirname(__file__), '..', 'config', 'credentials.json')

    if not os.path.exists(credentials_file):
        raise FileNotFoundError(f"Credentials file not found: {credentials_file}")

    with open(credentials_file, 'r') as f:
        creds = json.load(f)

    return creds['database']['postgresql']

def create_tables():
    """Execute the SQL file to create tables"""

    # Load credentials
    pg_creds = load_credentials()

    # Read SQL file
    sql_file = os.path.join(os.path.dirname(__file__), 'add_ibkr_tables.sql')
    with open(sql_file, 'r') as f:
        sql_script = f.read()

    try:
        # Connect to database
        conn = psycopg2.connect(
            host=pg_creds['host'],
            port=pg_creds['port'],
            database=pg_creds['database'],
            user=pg_creds['user'],
            password=pg_creds['password']
        )

        cursor = conn.cursor()

        print(f"✅ Connected to PostgreSQL: {pg_creds['host']}")

        # Execute the SQL script
        cursor.execute(sql_script)
        conn.commit()

        print("✅ Successfully created IBKR position tracking tables")

        # Verify tables were created
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('ibkr_positions', 'market_snapshots', 'options_greeks', 'performance_history')
            ORDER BY table_name;
        """)

        tables = cursor.fetchall()
        print(f"\n📊 Created tables: {[t[0] for t in tables]}")

        cursor.close()
        conn.close()

        return True

    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        return False

def insert_joined_df_data(joined_df):
    """Insert data from joined_df into ibkr_positions table"""

    if joined_df.empty:
        print("⚠️ No data to insert - joined_df is empty")
        return

    pg_creds = load_credentials()

    try:
        conn = psycopg2.connect(
            host=pg_creds['host'],
            port=pg_creds['port'],
            database=pg_creds['database'],
            user=pg_creds['user'],
            password=pg_creds['password']
        )

        cursor = conn.cursor()

        # Insert each row from joined_df
        for _, row in joined_df.iterrows():
            insert_sql = """
            INSERT INTO ibkr_positions (
                ibkr_symbol, ibkr_description, ibkr_avg_cost, ibkr_current_price,
                ibkr_unrealized_pnl, ibkr_market_val, ibkr_position,
                db_id, db_ticker, db_strategy_type, db_trigger_price,
                db_strike_sell, db_strike_buy, db_estimated_premium,
                db_options_expiry_date, db_scrape_date, db_strategy_status,
                db_trade_id, premium_difference
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) ON CONFLICT (ibkr_symbol, ibkr_description, db_id)
            DO UPDATE SET
                ibkr_current_price = EXCLUDED.ibkr_current_price,
                ibkr_unrealized_pnl = EXCLUDED.ibkr_unrealized_pnl,
                ibkr_market_val = EXCLUDED.ibkr_market_val,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id;
            """

            cursor.execute(insert_sql, (
                row['ibkr_symbol'],
                row['ibkr_description'],
                row['ibkr_avg_cost'],
                row['ibkr_current_price'],
                row['ibkr_unrealized_pnl'],
                row['ibkr_market_val'],
                row['ibkr_position'],
                row['db_id'],
                row['db_ticker'],
                row['db_strategy_type'],
                row['db_trigger_price'],
                row['db_strike_sell'],
                row['db_strike_buy'],
                row['db_estimated_premium'],
                row['db_options_expiry_date'],
                row['db_scrape_date'],
                row['db_strategy_status'],
                row['db_trade_id'],
                row['premium_difference']
            ))

            position_id = cursor.fetchone()[0]

            # Also insert current price as first market snapshot
            if pd.notnull(row['ibkr_current_price']):
                market_insert_sql = """
                INSERT INTO market_snapshots (position_id, current_price, data_source)
                VALUES (%s, %s, 'IBKR_Initial')
                """
                cursor.execute(market_insert_sql, (position_id, row['ibkr_current_price']))

        conn.commit()
        print(f"✅ Successfully inserted {len(joined_df)} positions into database")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"❌ Error inserting data: {e}")

def test_connection():
    """Test connection to PostgreSQL database"""
    try:
        pg_creds = load_credentials()

        conn = psycopg2.connect(
            host=pg_creds['host'],
            port=pg_creds['port'],
            database=pg_creds['database'],
            user=pg_creds['user'],
            password=pg_creds['password']
        )

        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()

        print(f"✅ Database connection successful")
        print(f"📊 PostgreSQL version: {version[0][:50]}...")

        # Check existing tables
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)

        tables = cursor.fetchall()
        print(f"📋 Existing tables: {[t[0] for t in tables]}")

        cursor.close()
        conn.close()

        return True

    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Setting up IBKR Position Tracking Tables")
    print("=" * 50)

    # Test connection first
    if not test_connection():
        sys.exit(1)

    # Create tables
    if create_tables():
        print("\n✅ Setup completed successfully!")
        print("\nNext steps:")
        print("1. Run your ikbr_get_positions.ipynb notebook to get joined_df")
        print("2. Use insert_joined_df_data(joined_df) to populate the tables")
        print("3. Start adding market data using market_snapshots table")
    else:
        print("\n❌ Setup failed")
        sys.exit(1)