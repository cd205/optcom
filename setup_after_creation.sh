#!/bin/bash
# Run this script AFTER creating the PostgreSQL instance in GCP Console

echo "🔍 Checking for PostgreSQL instance..."

# Try to get instance details
INSTANCE_IP=$(gcloud sql instances describe optcom-postgres --format="value(ipAddresses[0].ipAddress)" 2>/dev/null)

if [ -z "$INSTANCE_IP" ]; then
    echo "❌ PostgreSQL instance 'optcom-postgres' not found"
    echo "💡 Please create the instance first using GCP Console:"
    echo "   https://console.cloud.google.com/sql/instances?project=crafty-water-453519-d7"
    exit 1
fi

echo "✅ Found PostgreSQL instance!"
echo "📍 Instance IP: $INSTANCE_IP"

# Get connection details
CONNECTION_NAME=$(gcloud sql instances describe optcom-postgres --format="value(connectionName)" 2>/dev/null)
echo "🔗 Connection Name: $CONNECTION_NAME"

# Get current VM IP
VM_EXTERNAL_IP=$(curl -s ifconfig.me)
echo "🖥️  VM External IP: $VM_EXTERNAL_IP"

# Create .env file
echo ""
echo "📝 Creating .env configuration file..."

cat > .env << EOF
# Database Configuration for GCP PostgreSQL (Europe West 4)
DB_TYPE=postgresql
DB_HOST=$INSTANCE_IP
DB_PORT=5432
DB_NAME=option_strategies
DB_USER=optcom-user
DB_PASSWORD=REPLACE_WITH_YOUR_PASSWORD

# GCP Connection Details
INSTANCE_CONNECTION_NAME=$CONNECTION_NAME

# Network Configuration
VM_EXTERNAL_IP=$VM_EXTERNAL_IP
EOF

echo "✅ Created .env file"
echo ""
echo "🔧 IMPORTANT - Complete these steps:"
echo ""
echo "1. ✏️  Edit .env file and replace password:"
echo "   nano .env"
echo ""
echo "2. 🌐 Ensure database and user exist (via GCP Console):"
echo "   - Database: option_strategies"
echo "   - User: optcom-user"
echo "   - Network authorized: $VM_EXTERNAL_IP/32"
echo ""
echo "3. 🧪 Test connection:"
echo "   python test_migration.py"
echo ""
echo "4. 📊 Run migration:"
echo "   ./deployment/migrate_to_gcp.sh"
echo ""
echo "🌐 Manage instance: https://console.cloud.google.com/sql/instances/optcom-postgres"