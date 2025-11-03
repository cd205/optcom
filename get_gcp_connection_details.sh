#!/bin/bash
# Script to get GCP PostgreSQL connection details after instance is created
# Updated for Europe West 4 region (same as VM)

echo "🌍 Getting GCP PostgreSQL connection details (Europe West 4)..."

# Get instance IP
echo "📍 Getting instance IP address..."
INSTANCE_IP=$(gcloud sql instances describe optcom-postgres --format="value(ipAddresses[0].ipAddress)" 2>/dev/null)

if [ -n "$INSTANCE_IP" ]; then
    echo "✅ Instance IP: $INSTANCE_IP"
else
    echo "❌ Could not get instance IP. Make sure 'optcom-postgres' instance exists."
    echo "💡 Check GCP Console: https://console.cloud.google.com/sql"
    exit 1
fi

# Get connection name
CONNECTION_NAME=$(gcloud sql instances describe optcom-postgres --format="value(connectionName)" 2>/dev/null)
echo "🔗 Connection Name: $CONNECTION_NAME"

# Get current VM internal IP (since they're in same region, can use internal IP)
VM_INTERNAL_IP=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/ip)
echo "🖥️  VM Internal IP: $VM_INTERNAL_IP"

# Create .env configuration
echo ""
echo "📝 Creating .env configuration..."

cat > .env << EOF
# Database Configuration for GCP PostgreSQL (Europe West 4)
DB_TYPE=postgresql
DB_HOST=$INSTANCE_IP
DB_PORT=5432
DB_NAME=option_strategies
DB_USER=optcom-user
DB_PASSWORD=YOUR_PASSWORD_HERE

# GCP Connection Details
INSTANCE_CONNECTION_NAME=$CONNECTION_NAME

# Network Configuration
VM_INTERNAL_IP=$VM_INTERNAL_IP
EOF

echo "✅ Created .env file with connection details"
echo ""
echo "🔧 Next steps:"
echo "1. Edit .env and replace 'YOUR_PASSWORD_HERE' with your actual password"
echo "2. Allow your VM's IP for connections:"
echo "   gcloud sql instances patch optcom-postgres --authorized-networks=$VM_INTERNAL_IP/32"
echo "3. Or use Cloud SQL Proxy for secure connection (recommended)"
echo "4. Run the migration: ./deployment/migrate_to_gcp.sh"
echo ""
echo "🌐 Manage via GCP Console: https://console.cloud.google.com/sql/instances/optcom-postgres"
echo "📍 Instance will be in region: europe-west4 (same as your VM)"