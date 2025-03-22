import os
import sys
import argparse
import datetime
import time
import sqlite3
import yfinance as yf
import pandas as pd
import numpy as np
from optcom.trades import TradeManager

def get_price(symbol):
    """Get current price of a symbol."""
    ticker = yf.Ticker(symbol)
    try:
        price = ticker.history(period='1d')['Close'].iloc[-1]
        return price
    except Exception as e:
        print(f"Error getting price for {symbol}: {e}")
        return None

def get_vix():
    """Get current VIX value."""
    return get_price('^VIX')

def check_strategies(db_path, verbose=False):
    """Check if any strategies should be triggered based on current market conditions."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all active strategies
    cursor.execute('''
        SELECT id, symbol, strategy_type, min_price, max_price, min_vix, max_vix, trade_amount 
        FROM option_strategies 
        WHERE is_active = 1
        AND (completed = 0 OR completed IS NULL)
    ''')
    strategies = cursor.fetchall()
    
    if verbose:
        print(f"Found {len(strategies)} active strategies")
    
    triggered_strategies = []
    
    current_time = datetime.datetime.now()
    
    for strategy in strategies:
        strategy_id, symbol, strategy_type, min_price, max_price, min_vix, max_vix, trade_amount = strategy
        
        # Get current price of symbol
        current_price = get_price(symbol)
        current_timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if current_price is None:
            if verbose:
                print(f"Could not get price for {symbol}, skipping strategy {strategy_id}")
            continue
        
        # Update the last_price_when_checked and timestamp_of_price_when_last_checked columns
        cursor.execute('''
            UPDATE option_strategies
            SET last_price_when_checked = ?,
                timestamp_of_price_when_last_checked = ?
            WHERE id = ?
        ''', (current_price, current_timestamp, strategy_id))
        conn.commit()
            
        # Check if price is within range
        price_trigger = True
        if min_price is not None and current_price < min_price:
            price_trigger = False
        if max_price is not None and current_price > max_price:
            price_trigger = False
            
        # Check if VIX is within range
        vix_trigger = True
        if min_vix is not None or max_vix is not None:
            current_vix = get_vix()
            if current_vix is None:
                if verbose:
                    print(f"Could not get VIX value, skipping VIX check for strategy {strategy_id}")
            else:
                if min_vix is not None and current_vix < min_vix:
                    vix_trigger = False
                if max_vix is not None and current_vix > max_vix:
                    vix_trigger = False
        
        if price_trigger and vix_trigger:
            if verbose:
                print(f"Strategy {strategy_id} triggered! {symbol} at {current_price}, VIX conditions met")
            triggered_strategies.append((strategy_id, symbol, strategy_type, current_price, trade_amount))
    
    conn.close()
    return triggered_strategies

def main():
    parser = argparse.ArgumentParser(description='Monitor prices and execute option strategies')
    parser.add_argument('--db', type=str, default='option_strategies.db', help='Path to the database')
    parser.add_argument('--verbose', '-v', action='store_true', help='Print verbose output')
    parser.add_argument('--interval', '-i', type=int, default=60, help='Check interval in seconds')
    parser.add_argument('--dry-run', '-d', action='store_true', help='Do not execute trades, just print what would happen')
    
    args = parser.parse_args()
    
    db_path = args.db
    if not os.path.exists(db_path):
        print(f"Database {db_path} does not exist")
        sys.exit(1)
        
    tm = TradeManager(db_path=db_path, dry_run=args.dry_run)
    
    while True:
        try:
            if args.verbose:
                print(f"\nChecking strategies at {datetime.datetime.now()}")
                
            triggered = check_strategies(db_path, verbose=args.verbose)
            
            for strategy_id, symbol, strategy_type, current_price, trade_amount in triggered:
                if args.verbose:
                    print(f"Executing strategy {strategy_id}: {strategy_type} on {symbol} at ${current_price:.2f}")
                
                # Execute the trade
                tm.execute_strategy(
                    strategy_id=strategy_id,
                    strategy_type=strategy_type,
                    symbol=symbol,
                    trade_amount=trade_amount,
                    current_price=current_price
                )
                
        except Exception as e:
            print(f"Error: {e}")
            
        time.sleep(args.interval)

if __name__ == "__main__":
    main()