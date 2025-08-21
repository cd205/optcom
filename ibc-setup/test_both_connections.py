#!/usr/bin/env python3
"""
Test script to verify both Paper and Live IB Gateway connections
"""
import socket
import time
import sys

def test_connection(host='127.0.0.1', port=4001, timeout=5, account_type="Paper"):
    """Test connection to IB Gateway API port"""
    try:
        print(f"Testing {account_type} connection to {host}:{port}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            print(f"✅ {account_type} Connection successful - API port {port} is listening")
            return True
        else:
            print(f"❌ {account_type} Connection failed - API port {port} is not available")
            return False
            
    except Exception as e:
        print(f"❌ {account_type} Connection error: {e}")
        return False

def main():
    print("IB Gateway Dual Account Connection Test")
    print("=" * 50)
    
    # Test both connections
    paper_ok = test_connection(port=4001, account_type="Paper")
    live_ok = test_connection(port=4002, account_type="Live")
    
    print("\n" + "=" * 50)
    
    if paper_ok and live_ok:
        print("🎉 Both Gateways are ready for API connections!")
        print("\nConnection Details:")
        print("  📊 Paper Trading: localhost:4001") 
        print("  💰 Live Trading:  localhost:4002")
        print("\nExample Python connection:")
        print("  # Paper account")
        print("  app.connect('127.0.0.1', 4001, clientId=1)")
        print("  # Live account") 
        print("  app.connect('127.0.0.1', 4002, clientId=2)")
        sys.exit(0)
    elif paper_ok:
        print("⚠️ Only Paper Gateway is ready")
        print("📊 Paper Trading: localhost:4001 ✅")
        print("💰 Live Trading:  localhost:4002 ❌")
        sys.exit(1)
    elif live_ok:
        print("⚠️ Only Live Gateway is ready") 
        print("📊 Paper Trading: localhost:4001 ❌")
        print("💰 Live Trading:  localhost:4002 ✅")
        sys.exit(1)
    else:
        print("⚠️ Neither Gateway is ready")
        print("Please start the Gateways with:")
        print("  ./start-dual-gateway.sh start")
        sys.exit(1)

if __name__ == "__main__":
    main()