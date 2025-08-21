#!/usr/bin/env python3
"""
Test script to verify IB Gateway connection
"""
import socket
import time
import sys

def test_connection(host='127.0.0.1', port=4001, timeout=5):
    """Test connection to IB Gateway API port"""
    try:
        print(f"Testing connection to {host}:{port}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            print("✅ Connection successful - IB Gateway API port is listening")
            return True
        else:
            print("❌ Connection failed - IB Gateway API port is not available")
            return False
            
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

def main():
    print("IB Gateway Connection Test")
    print("=" * 40)
    
    # Test the connection
    if test_connection():
        print("\n🎉 IB Gateway is ready for API connections!")
        print("\nYour Python script should now be able to connect using:")
        print("  - Host: 127.0.0.1 (or localhost)")
        print("  - Port: 4001")
        print("  - Client ID: Any unique integer")
        sys.exit(0)
    else:
        print("\n⚠️  IB Gateway is not ready yet.")
        print("Please make sure the Gateway is started with:")
        print("  ./start-gateway.sh start")
        sys.exit(1)

if __name__ == "__main__":
    main()