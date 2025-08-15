# Database Migration: SQLite to PostgreSQL in GCP

This guide covers the complete migration from SQLite to PostgreSQL hosted in Google Cloud Platform.

## 🏗️ Migration Overview

The migration includes:
- ✅ New database abstraction layer supporting both SQLite and PostgreSQL
- ✅ GCP PostgreSQL setup instructions
- ✅ Data migration scripts
- ✅ Updated application code
- ✅ Docker deployment configuration
- ✅ Environment-based configuration

## 📋 Prerequisites

1. **GCP Account** with Cloud SQL enabled
2. **Python packages**: `psycopg2-binary`, `pandas`, `sqlalchemy`, `python-dotenv`
3. **Existing SQLite database**: `database/option_strategies.db`

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set Up GCP PostgreSQL
Follow the instructions in `database/gcp_setup_instructions.md` to:
- Create Cloud SQL PostgreSQL instance
- Configure networking and users
- Get connection details

### 3. Configure Environment
```bash
cp .env.example .env
# Edit .env with your PostgreSQL credentials
```

### 4. Run Migration
```bash
# Set your database credentials
export DB_PASSWORD="your-secure-password"
export DB_HOST="your-gcp-instance-ip"

# Run migration script
./deployment/migrate_to_gcp.sh
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_TYPE` | Database type (`postgresql` or `sqlite`) | `sqlite` |
| `DB_HOST` | PostgreSQL host | `localhost` |
| `DB_PORT` | PostgreSQL port | `5432` |
| `DB_NAME` | Database name | `option_strategies` |
| `DB_USER` | PostgreSQL user | `optcom-user` |
| `DB_PASSWORD` | PostgreSQL password | *(required)* |
| `SQLITE_DB_PATH` | SQLite file path (fallback) | `./database/option_strategies.db` |

### Database Selection

The system automatically uses PostgreSQL when `DB_TYPE=postgresql` and falls back to SQLite otherwise.

## 📁 Updated Files

### Core Database Files
- `database/database_config.py` - New database abstraction layer
- `database/postgresql_schema.sql` - PostgreSQL schema
- `database/migrate_data.py` - Data migration script
- `requirements.txt` - Added PostgreSQL dependencies

### Updated Applications
- `database/create_database.ipynb` - Uses new config system
- `database/database_query.ipynb` - Updated for both databases
- `monitor/price_monitor.py` - Removed SQLite-specific code

### Deployment
- `Dockerfile` - Container configuration
- `deployment/docker-compose.yml` - PostgreSQL + application
- `deployment/migrate_to_gcp.sh` - Migration automation

## 🧪 Testing

Run the test suite to verify everything works:
```bash
python test_migration.py
```

This tests:
- ✅ SQLite connection and queries
- ✅ Database abstraction functions
- ✅ PostgreSQL configuration
- ✅ Schema compatibility

## 🔄 Usage Examples

### Using with PostgreSQL
```bash
export DB_TYPE=postgresql
export DB_HOST=your-gcp-ip
export DB_PASSWORD=your-password

python monitor/price_monitor.py
```

### Using with SQLite (fallback)
```bash
export DB_TYPE=sqlite
# or just unset DB_TYPE

python monitor/price_monitor.py
```

### Using Jupyter Notebooks
The notebooks automatically detect and use the configured database:
```python
# In database/create_database.ipynb
setup_option_strategies_database()

# In database/database_query.ipynb
query_database()
```

## 🐳 Docker Deployment

### Local PostgreSQL (for testing)
```bash
cd deployment
docker-compose up -d postgres

# Wait for PostgreSQL to start, then migrate
export DB_HOST=localhost
export DB_PASSWORD=your-secure-password
./migrate_to_gcp.sh
```

### Full Application Stack
```bash
cd deployment
export DB_PASSWORD=your-secure-password
docker-compose up -d
```

## 🔍 Monitoring

The migration preserves all existing functionality:
- Price monitoring continues to work
- All database queries are compatible
- Data integrity is maintained
- Performance is improved with PostgreSQL indexes

## 🚨 Troubleshooting

### Connection Issues
```bash
# Test PostgreSQL connection
python -c "
import sys; sys.path.append('database')
from database_config import get_db_connection
print('Connected:', get_db_connection().test_connection())
"
```

### Migration Issues
```bash
# Check SQLite data before migration
python -c "
import sqlite3
conn = sqlite3.connect('database/option_strategies.db')
print('SQLite records:', conn.execute('SELECT COUNT(*) FROM option_strategies').fetchone()[0])
"

# Check PostgreSQL after migration
export DB_TYPE=postgresql
python -c "
import sys; sys.path.append('database')
from database_config import get_db_connection
db = get_db_connection()
count = db.execute_query('SELECT COUNT(*) FROM option_strategies')[0][0]
print('PostgreSQL records:', count)
"
```

### Fallback to SQLite
If there are issues with PostgreSQL, simply set:
```bash
export DB_TYPE=sqlite
```

All applications will automatically fall back to SQLite.

## 📈 Performance Benefits

PostgreSQL provides:
- **Concurrent access** - Multiple processes can read/write simultaneously
- **Better indexing** - Improved query performance
- **ACID compliance** - Better data integrity
- **Scalability** - Can handle larger datasets
- **Cloud integration** - Native GCP features (backups, monitoring, etc.)

## 🔐 Security

- Database credentials are environment-based
- No hardcoded passwords in code
- GCP Cloud SQL provides encryption at rest and in transit
- Network access can be restricted to specific IPs

## 📚 File Reference

```
optcom-1/
├── database/
│   ├── database_config.py          # New database abstraction
│   ├── postgresql_schema.sql       # PostgreSQL schema
│   ├── migrate_data.py             # Migration script
│   ├── gcp_setup_instructions.md   # GCP setup guide
│   ├── create_database.ipynb       # Updated notebook
│   └── database_query.ipynb        # Updated notebook
├── deployment/
│   ├── docker-compose.yml          # Docker deployment
│   └── migrate_to_gcp.sh           # Migration automation
├── monitor/
│   └── price_monitor.py            # Updated monitoring
├── .env.example                    # Environment template
├── Dockerfile                      # Container config
├── requirements.txt                # Dependencies
├── test_migration.py               # Test suite
└── README_MIGRATION.md             # This guide
```