# Simple Trading Workflow

**No bells and whistles - just 5 clear steps that work reliably.**

## 🚀 Quick Start

```bash
cd /home/chris_s_dodd/optcom-1/airflow_project

# Start the complete workflow
make start

# Check which step is running
make status

# Stop everything (including gateways)
make stop
```

## 📋 The 5-Step Workflow

1. **Check Data** - Look for today's data in database → skip to step 4 if found
2. **Run Scraper** - Scrape options data (only if step 1 found no data)
3. **Verify Records** - Confirm scraper wrote records to database
4. **Start Gateways** - Start IB gateways, wait up to 15 mins for 2FA
5. **Trading Monitor** - Run trading monitor (leaves running)

## 🔧 Individual Steps (for debugging)

```bash
# Run any step individually
make step1    # Check data
make step2    # Run scraper  
make step3    # Verify records
make step4    # Start gateways
make step5    # Trading monitor (5 min test)
```

## 📊 Check Status

```bash
# See which step is currently running
make status
```

Example output:
```
🔍 SIMPLE WORKFLOW STATUS
==================================================
Airflow Status: 🟢 Running
Latest Run: manual__2025-08-25T20:00:00.000000+00:00
State: running

Step Status:
  Step 1: Check Data: ✅ success
  Step 2: Run Scraper: ✅ success  
  Step 3: Verify Records: ✅ success
  Step 4: Start Gateways: 🟡 running
  Step 5: Trading Monitor: ⚪ Not started

🎯 Current Status: Step 4: Start Gateways

🚪 Gateway Status:
📊 Paper Gateway: Running (PID: 12345)
   ✅ API Port 4002: Listening
💰 Live Gateway: Not started
```

## 🛑 Stop Everything

```bash
# Stop workflow, Airflow, and gateways
make stop

# Or full restart (stop + start)
make restart
```

## 🔍 Gateway Management

```bash
# Check just gateway status
make gateway-status

# Start just gateways
make gateway-start

# Stop just gateways  
make gateway-stop
```

## ⚙️ How It Works

### Data Check Logic (Step 1)
- Queries database for records with `scrape_date = today`
- If found → skips scraper, goes to step 4 
- If not found → runs scraper in step 2

### Gateway Startup (Step 4)
- Starts both paper and live gateways
- Checks status every 15 seconds
- Allows up to 15 minutes for 2FA on live gateway
- Proceeds as soon as both gateways are running

### Trading Monitor (Step 5)
- Runs for 2 hours by default
- Uses paper trading port (4002)
- Handles order placement and monitoring
- Leaves running until manually stopped

## 🐛 Debugging Tips

### Check Individual Steps
```bash
# Test each step separately
make step1
make step2  # Takes 10-15 minutes
make step3
make step4  # Takes up to 15 minutes  
make step5  # 5 minute test run
```

### Check Logs
```bash
# Airflow logs (if workflow running)
export AIRFLOW_HOME=/home/chris_s_dodd/optcom-1/airflow_project
airflow logs simple_trading_workflow step1_check_data $(date +%Y-%m-%d)

# Gateway logs  
tail -f ../ibc-setup/logs/paper-gateway.log
tail -f ../ibc-setup/logs/live-gateway.log
```

### Common Issues

**"Airflow not running"**
```bash
export AIRFLOW_HOME=/home/chris_s_dodd/optcom-1/airflow_project
airflow standalone &
```

**"Gateways won't start"**
```bash
# Check if ports are busy
ss -tlnp | grep -E "4001|4002"

# Manual gateway restart
make -f Makefile.simple gateway-stop
sleep 5
make -f Makefile.simple gateway-start
```

**"Scraper failed"**
```bash
# Test scraper individually
make step2

# Check database after
make step3
```

## 📁 File Structure

```
airflow_project/
├── README.md                 # This file
├── Makefile                  # Simple commands
├── dags/
│   └── simple_trading_workflow.py    # 5-step DAG
└── scripts/
    ├── run_individual_steps.py       # Run steps individually
    ├── workflow_manager.py           # Status/start/stop
    ├── options_scraper.py           # Scraper (existing)
    ├── trading_monitor.py           # Monitor (existing)  
    └── ib_gateway_utils.py          # Gateway utils (existing)
```

## 💡 Key Benefits

- **Simple**: Just 5 clear steps, no complex configuration
- **Reliable**: Each step verifies the previous step worked  
- **Debuggable**: Run any step individually
- **Visible**: Clear status checking
- **Safe**: Easy stop/restart of everything
- **Smart**: Skips scraping if data already exists

---

**Start your trading workflow:**
```bash
make start
```