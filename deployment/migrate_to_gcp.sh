#!/bin/bash
# Migration script for moving from SQLite to GCP PostgreSQL

set -e

echo "🚀 Starting migration to GCP PostgreSQL..."

# Check if required environment variables are set
if [ -z "$DB_PASSWORD" ]; then
    echo "❌ Error: DB_PASSWORD environment variable not set"
    exit 1
fi

if [ -z "$DB_HOST" ]; then
    echo "❌ Error: DB_HOST environment variable not set"
    exit 1
fi

# Set database type to PostgreSQL
export DB_TYPE=postgresql
export DB_NAME=option_strategies
export DB_USER=optcom-user
export DB_PORT=5432

echo "📋 Configuration:"
echo "  Database Type: $DB_TYPE"
echo "  Host: $DB_HOST"
echo "  Port: $DB_PORT"
echo "  Database: $DB_NAME"
echo "  User: $DB_USER"

# Install required packages if not already installed
echo "📦 Installing required packages..."
pip install -r requirements.txt

# Test PostgreSQL connection
echo "🔍 Testing PostgreSQL connection..."
python -c "
import sys
sys.path.append('database')
from database_config import get_db_connection
db = get_db_connection()
if not db.test_connection():
    print('❌ Cannot connect to PostgreSQL')
    sys.exit(1)
print('✅ PostgreSQL connection successful')
"

# Create PostgreSQL schema
echo "🏗️  Creating PostgreSQL schema..."
python -c "
import sys
sys.path.append('database')
from database_config import setup_database
if not setup_database():
    print('❌ Schema creation failed')
    sys.exit(1)
print('✅ Schema created successfully')
"

# Run data migration
echo "📊 Migrating data from SQLite to PostgreSQL..."
python database/migrate_data.py

# Verify migration
echo "🔎 Verifying migration..."
python -c "
import sys
sys.path.append('database')
from database_config import get_db_connection
db = get_db_connection()
count_result = db.execute_query('SELECT COUNT(*) FROM option_strategies')
count = count_result[0][0] if count_result else 0
print(f'✅ PostgreSQL database has {count} records')
"

# Test updated applications
echo "🧪 Testing updated applications..."
python test_migration.py

echo "🎉 Migration completed successfully!"
echo ""
echo "📝 Next steps:"
echo "  1. Update any remaining scripts to use new database configuration"
echo "  2. Set DB_TYPE=postgresql in your environment"
echo "  3. Update any deployment scripts or containers"
echo ""
echo "💡 To use SQLite as fallback, set DB_TYPE=sqlite"