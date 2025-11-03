# 🚀 GCP PostgreSQL Setup Steps

## Step 1: Create PostgreSQL Instance in GCP Console

### 📍 **Direct Links:**
- **GCP Console**: https://console.cloud.google.com/
- **Cloud SQL Page**: https://console.cloud.google.com/sql/instances?project=crafty-water-453519-d7
- **Create Instance**: https://console.cloud.google.com/sql/choose-instance-engine?project=crafty-water-453519-d7

### 🛠️ **Configuration Settings:**

1. **Click "Create Instance"**
2. **Choose "PostgreSQL"**
3. **Configure Instance:**

| Setting | Value |
|---------|-------|
| **Instance ID** | `optcom-postgres` |
| **Password** | Choose a secure password (save it!) |
| **Database version** | `PostgreSQL 15` |
| **Cloud SQL edition** | `Enterprise` |
| **Preset** | `Development` (cheapest) |
| **Region** | `europe-west4` (Netherlands) |
| **Zonal availability** | `Single zone` |
| **Machine type** | `db-f1-micro` (1 vCPU, 0.6 GB) |
| **Storage type** | `SSD` |
| **Storage capacity** | `10 GB` |
| **Enable automatic storage increases** | `✓ Yes` |

4. **Advanced Configuration:**
   - **Automated backups**: `✓ Enabled`
   - **Backup time**: `02:00` (2 AM)
   - **Maintenance window**: `Sunday 03:00`
   - **Delete protection**: `✓ Enabled` (recommended)

5. **Click "CREATE INSTANCE"**

## Step 2: Wait for Creation
- **Estimated time**: 3-5 minutes
- **Status**: Wait for green checkmark ✅

## Step 3: Configure Database and User

After the instance is created:

1. **Click on your instance** (`optcom-postgres`)
2. **Go to "Databases" tab**
   - Click **"Create Database"**
   - Database name: `option_strategies`
   - Click **"Create"**

3. **Go to "Users" tab**
   - Click **"Add User Account"**
   - Username: `optcom-user`
   - Password: Choose a secure password (same or different from root)
   - Click **"Add"**

## Step 4: Configure Network Access

1. **Go to "Connections" tab**
2. **Add Authorized Networks:**
   - Click **"Add Network"**
   - Name: `VM Access`
   - Network: Get your VM's external IP:

```bash
# Run this on your VM to get external IP
curl -s ifconfig.me
```

3. **Add the IP with /32** (e.g., `34.123.45.67/32`)
4. **Click "Save"**

## Step 5: Get Connection Details

After everything is configured, the connection details will be:

- **Host**: Found in instance overview (public IP)
- **Port**: `5432`
- **Database**: `option_strategies`
- **Username**: `optcom-user`
- **Password**: What you set

## 🔧 Estimated Costs

- **db-f1-micro**: ~$7-10/month
- **10GB storage**: ~$2/month
- **Total**: ~$9-12/month

## 📱 Quick Status Check

You can monitor progress at:
https://console.cloud.google.com/sql/instances/optcom-postgres?project=crafty-water-453519-d7