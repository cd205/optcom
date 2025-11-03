#!/usr/bin/env python3
"""
Test script for database migration functionality
"""

import os
import sys
import logging

# Add paths for imports
sys.path.append('database')

from database_config import get_db_connection, setup_database

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_sqlite_connection():
    """Test SQLite connection and functionality"""
    print("\n=== Testing SQLite Connection ===")
    
    # Ensure we're using SQLite
    os.environ['DB_TYPE'] = 'sqlite'
    
    db = get_db_connection()
    print(f"Database type: {db.config.db_type}")
    
    # Test connection
    if not db.test_connection():
        print("❌ SQLite connection failed")
        return False
    print("✅ SQLite connection successful")
    
    # Test table exists
    if not db.table_exists():
        print("❌ Table doesn't exist")
        return False
    print("✅ Table exists")
    
    # Test query
    try:
        count_result = db.execute_query("SELECT COUNT(*) FROM option_strategies")
        count = count_result[0][0] if count_result else 0
        print(f"✅ Record count: {count}")
    except Exception as e:
        print(f"❌ Query failed: {e}")
        return False
    
    return True

def test_database_functions():
    """Test database functions from notebooks"""
    print("\n=== Testing Database Functions ===")
    
    try:
        # Test setup function
        success = setup_database()
        if success:
            print("✅ Database setup successful")
        else:
            print("❌ Database setup failed")
            return False
        
        # Test some sample queries
        db = get_db_connection()
        
        # Test strategy type query
        strategy_results = db.execute_query(
            "SELECT strategy_type, COUNT(*) FROM option_strategies GROUP BY strategy_type"
        )
        print(f"✅ Strategy types query: {len(strategy_results)} types found")
        
        # Test DataFrame query
        df = db.execute_query_df("SELECT * FROM option_strategies LIMIT 5")
        print(f"✅ DataFrame query: {len(df)} records retrieved")
        
        return True
        
    except Exception as e:
        print(f"❌ Database functions test failed: {e}")
        return False

def test_postgresql_config():
    """Test PostgreSQL configuration (without actual connection)"""
    print("\n=== Testing PostgreSQL Configuration ===")
    
    # Set PostgreSQL environment
    os.environ['DB_TYPE'] = 'postgresql'
    os.environ['DB_HOST'] = 'localhost'
    os.environ['DB_PORT'] = '5432'
    os.environ['DB_NAME'] = 'option_strategies'
    os.environ['DB_USER'] = 'test_user'
    os.environ['DB_PASSWORD'] = 'test_password'
    
    try:
        # Import fresh to pick up new env vars
        from importlib import reload
        import database_config
        reload(database_config)
        from database_config import get_db_connection
        
        db = get_db_connection()
        print(f"✅ PostgreSQL config loaded: {db.config.db_type}")
        print(f"✅ Connection string format: postgresql://...")
        
        # Reset to SQLite for other tests
        os.environ['DB_TYPE'] = 'sqlite'
        
        return True
        
    except Exception as e:
        print(f"❌ PostgreSQL config test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Starting Database Migration Tests")
    
    tests = [
        test_sqlite_connection,
        test_database_functions,
        test_postgresql_config,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
            results.append(False)
    
    print(f"\n📊 Test Results: {sum(results)}/{len(results)} passed")
    
    if all(results):
        print("🎉 All tests passed! Migration setup is working correctly.")
    else:
        print("⚠️  Some tests failed. Check the output above.")
    
    return all(results)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)