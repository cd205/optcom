# GCP PostgreSQL Setup Instructions

## 1. Create Cloud SQL PostgreSQL Instance

### Using gcloud CLI:
```bash
# Set your project ID
export PROJECT_ID="your-project-id"
gcloud config set project $PROJECT_ID

# Create PostgreSQL instance
gcloud sql instances create optcom-postgres \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro \
    --region=us-central1 \
    --storage-type=SSD \
    --storage-size=10GB \
    --backup-start-time=02:00 \
    --enable-bin-log \
    --maintenance-release-channel=production \
    --maintenance-window-day=SUN \
    --maintenance-window-hour=03

# Create database
gcloud sql databases create option_strategies --instance=optcom-postgres

# Create user
gcloud sql users create optcom-user \
    --instance=optcom-postgres \
    --password=your-secure-password

# Set instance connection name
export INSTANCE_CONNECTION_NAME="$PROJECT_ID:us-central1:optcom-postgres"
```

### Using GCP Console:
1. Go to Cloud SQL in GCP Console
2. Click "Create Instance" > "PostgreSQL"
3. Instance ID: `optcom-postgres`
4. Password: Set a secure password for postgres user
5. Database version: PostgreSQL 15
6. Region: `us-central1`
7. Machine type: `db-f1-micro` (can upgrade later)
8. Storage: 10GB SSD
9. Enable automated backups
10. Click "Create"

## 2. Configure Network Access

### Allow your IP (for development):
```bash
# Get your current IP
MY_IP=$(curl -s ifconfig.me)

# Add authorized network
gcloud sql instances patch optcom-postgres \
    --authorized-networks=$MY_IP/32
```

### For production, use Cloud SQL Proxy or Private IP

## 3. Connection Details

After creation, note these details:
- **Instance Connection Name**: `PROJECT_ID:REGION:INSTANCE_ID`
- **Public IP**: Found in instance details
- **Database Name**: `option_strategies`
- **Username**: `optcom-user`
- **Password**: What you set during creation

## 4. Install Cloud SQL Proxy (Optional but Recommended)

```bash
# Download Cloud SQL Proxy
curl -o cloud_sql_proxy https://dl.google.com/cloudsql/cloud_sql_proxy.linux.amd64
chmod +x cloud_sql_proxy

# Start proxy (replace with your instance connection name)
./cloud_sql_proxy -instances=PROJECT_ID:REGION:INSTANCE_ID=tcp:5432
```

## 5. Test Connection

```bash
# Install PostgreSQL client if needed
sudo apt-get install postgresql-client

# Test connection
psql "host=127.0.0.1 port=5432 dbname=option_strategies user=optcom-user"
```

## Environment Variables

Add these to your environment:
```bash
export DB_HOST="your-instance-public-ip"  # or 127.0.0.1 if using proxy
export DB_PORT="5432"
export DB_NAME="option_strategies" 
export DB_USER="optcom-user"
export DB_PASSWORD="your-password"
export DB_TYPE="postgresql"
```