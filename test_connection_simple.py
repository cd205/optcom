#!/usr/bin/env python3
"""
Simple connection test for IB Gateway with improved timeout handling
"""
import sys
import os
sys.path.append('/home/chris_s_dodd/optcom-1')

from monitor.ibkr_integration import IBKRDataProvider
import time
import random

def main():
    print("Testing IBKR connection with improved timeouts...")
    
    # Use a random client ID to avoid conflicts
    client_id = random.randint(5000, 9999)
    print(f"Using client ID: {client_id}")
    
    try:
        ibkr = IBKRDataProvider(host='127.0.0.1', port=4002, client_id=client_id)
        
        print("Attempting connection...")
        start_time = time.time()
        
        if ibkr.connect():
            connection_time = time.time() - start_time
            print(f"✅ Connection successful! (took {connection_time:.2f} seconds)")
            
            # Test getting a price for a simple stock
            print("Testing price retrieval for AAPL...")
            price_start = time.time()
            price = ibkr.get_latest_price('AAPL')
            price_time = time.time() - price_start
            
            if price:
                print(f"✅ Got price for AAPL: ${price} (took {price_time:.2f} seconds)")
            else:
                print(f"⚠️ Could not get price for AAPL (took {price_time:.2f} seconds)")
            
            # Disconnect
            ibkr.disconnect()
            print("✅ Disconnected successfully")
            
            total_time = time.time() - start_time
            print(f"Total test time: {total_time:.2f} seconds")
            
        else:
            connection_time = time.time() - start_time
            print(f"❌ Connection failed after {connection_time:.2f} seconds")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()