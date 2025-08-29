# Trading Workflow Troubleshooting Guide

## Issue: Workflow Starting but Immediately Failing

### Symptoms
- `make start` reports "✅ Workflow started successfully"
- `make status` shows "⚪ No running workflow found" 
- DAG runs show `state: failed` within seconds of starting
- Step 1 (step1_check_data) fails immediately causing all downstream steps to fail with "upstream_failed"

### Root Cause Analysis

1. **Initial Problem**: DAG was paused after first setup
   - **Solution**: Unpaused DAG with `airflow dags unpause simple_trading_workflow`

2. **Status Display Issues**: 
   - Gateway status showed "Not running" even when processes were active
   - Missing step-by-step workflow progress in status output
   - No cycle tracking for trading monitor

3. **Critical Issue**: Scheduler/Worker Process Corruption
   - Airflow scheduler and worker processes got into a bad state
   - Tasks would be queued but fail immediately without proper execution
   - Manual task testing worked fine, but scheduled execution failed

### Step-by-Step Resolution

#### Phase 1: Initial DAG Issues
```bash
# 1. Unpaused the DAG (first time setup issue)
export AIRFLOW_HOME=/home/chris_s_dodd/optcom-1/airflow_project
airflow dags unpause simple_trading_workflow
airflow dags trigger simple_trading_workflow
```

#### Phase 2: Status Display Fixes
```bash
# 2. Fixed gateway PID files (incorrect PIDs)
# Found actual running processes:
pgrep -f "java.*paper.*IbcGateway"  # Result: 12135
pgrep -f "java.*live.*IbcGateway"   # Result: 12623

# Updated PID files:
echo "12135" > /home/chris_s_dodd/optcom-1/ibc-setup/logs/paper-gateway.pid
echo "12623" > /home/chris_s_dodd/optcom-1/ibc-setup/logs/live-gateway.pid
```

#### Phase 3: Workflow Manager Enhancements
Modified `scripts/workflow_manager.py`:
- Fixed DAG run parsing to find running workflows instead of just first entry
- Added cycle progress tracking for trading monitor
- Enhanced status display with step-by-step progress

#### Phase 4: Critical Process Reset
```bash
# 3. Complete Airflow restart (solved the main issue)
make stop                    # Stop everything
pkill -f airflow            # Kill any remaining processes
pkill -f "price_monitor.py" # Kill orphaned trading monitors

# Restart Airflow completely
export AIRFLOW_HOME=/home/chris_s_dodd/optcom-1/airflow_project
nohup airflow standalone > airflow.log 2>&1 &

# Test workflow
make start
make status  # Now shows complete progress
```

### Files Modified

1. **`/home/chris_s_dodd/optcom-1/ibc-setup/logs/paper-gateway.pid`**
   - Updated with correct process ID

2. **`/home/chris_s_dodd/optcom-1/ibc-setup/logs/live-gateway.pid`**
   - Updated with correct process ID

3. **`scripts/workflow_manager.py`**
   - Added imports: `glob`, `re`
   - Added `get_trading_monitor_progress()` function
   - Enhanced status display with cycle tracking
   - Fixed DAG run detection logic

### Key Diagnostic Commands

```bash
# Check if DAG is paused
airflow dags list | grep simple_trading_workflow

# Check recent DAG runs
airflow dags list-runs simple_trading_workflow

# Check task states for a specific run
airflow tasks states-for-dag-run simple_trading_workflow [RUN_ID]

# Test individual task
airflow tasks test simple_trading_workflow step1_check_data 2024-08-26

# Check running processes
ps aux | grep -E "(airflow|trading|monitor)"
ss -tlnp | grep -E ":(4001|4002)"  # Gateway API ports
```

## Recommendations for Robust Startup

### Enhanced `make start` Implementation

The current `make start` should be enhanced to include these reliability checks:

```bash
# Proposed enhancements for scripts/workflow_manager.py start_workflow()

def start_workflow():
    """Enhanced startup with reliability checks"""
    print("🚀 STARTING SIMPLE WORKFLOW (ENHANCED)")
    print("=" * 45)
    
    # Set environment
    os.environ['AIRFLOW_HOME'] = '/home/chris_s_dodd/optcom-1/airflow_project'
    
    # 1. CLEANUP PHASE
    print("🧹 Cleanup Phase...")
    cleanup_orphaned_processes()
    
    # 2. AIRFLOW HEALTH CHECK
    print("🏥 Airflow Health Check...")
    if not check_airflow_health():
        print("⚠️  Restarting Airflow...")
        restart_airflow_clean()
    
    # 3. DAG READINESS CHECK  
    print("📋 DAG Readiness Check...")
    ensure_dag_ready()
    
    # 4. TRIGGER WORKFLOW
    print("🎯 Triggering Workflow...")
    result = trigger_workflow_with_retry()
    
    if result:
        print("✅ Workflow started successfully")
        print("Monitor with: make status")
    else:
        print("❌ Failed to start workflow - check logs")

def cleanup_orphaned_processes():
    """Clean up any orphaned processes"""
    subprocess.run(['pkill', '-f', 'price_monitor.py'], check=False)
    # Add other cleanup as needed

def check_airflow_health():
    """Check if Airflow processes are healthy"""
    required_processes = ['scheduler', 'dag-processor', 'api_server']
    result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
    
    for proc in required_processes:
        if f'airflow {proc}' not in result.stdout:
            return False
    return True

def restart_airflow_clean():
    """Clean restart of Airflow"""
    # Stop everything
    subprocess.run(['pkill', '-f', 'airflow'], check=False)
    time.sleep(5)
    
    # Start fresh
    subprocess.Popen(['airflow', 'standalone'], 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE)
    
    # Wait for startup
    for i in range(30):  # 30 second timeout
        if check_airflow_health():
            break
        time.sleep(1)
    else:
        raise Exception("Airflow failed to start")

def ensure_dag_ready():
    """Ensure DAG is unpaused and parseable"""
    # Check if DAG exists and is unpaused
    result = subprocess.run([
        'airflow', 'dags', 'list', '--output', 'json'
    ], capture_output=True, text=True)
    
    # Parse and check simple_trading_workflow
    # Unpause if needed
    subprocess.run([
        'airflow', 'dags', 'unpause', 'simple_trading_workflow'
    ], check=False)

def trigger_workflow_with_retry():
    """Trigger workflow with retry logic"""
    for attempt in range(3):
        result = subprocess.run([
            'airflow', 'dags', 'trigger', 'simple_trading_workflow'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            # Wait and verify it's actually running
            time.sleep(10)
            if verify_workflow_running():
                return True
        
        print(f"Attempt {attempt + 1} failed, retrying...")
        time.sleep(5)
    
    return False

def verify_workflow_running():
    """Verify workflow is actually running"""
    result = subprocess.run([
        'airflow', 'dags', 'list-runs', 'simple_trading_workflow'
    ], capture_output=True, text=True)
    
    return 'running' in result.stdout
```

### Prevention Strategies

1. **Startup Health Checks**
   - Verify all required Airflow processes are running
   - Check DAG parsing status before triggering
   - Validate database connectivity

2. **Process Management**
   - Clean shutdown procedures that kill all related processes
   - Process monitoring and automatic restart
   - Proper PID file management

3. **Graceful Degradation**
   - Retry logic for failed startups
   - Fallback to manual process management if Airflow fails
   - Clear error messages with suggested fixes

4. **Status Monitoring Improvements**
   - Real-time cycle progress for long-running tasks
   - Health status for all components
   - Clear indication of workflow phase and expected duration

### Quick Reference Commands

**For tomorrow's startup:**
```bash
cd /home/chris_s_dodd/optcom-1/airflow_project
make start
make status  # Should show complete workflow progress
```

**If issues persist:**
```bash
make stop
pkill -f airflow
pkill -f "price_monitor.py"
export AIRFLOW_HOME=/home/chris_s_dodd/optcom-1/airflow_project
nohup airflow standalone > airflow.log 2>&1 &
# Wait 30 seconds, then:
make start
```

**Emergency manual trigger:**
```bash
export AIRFLOW_HOME=/home/chris_s_dodd/optcom-1/airflow_project
airflow dags unpause simple_trading_workflow
airflow dags trigger simple_trading_workflow
```

This guide should help prevent and quickly resolve similar issues in the future.