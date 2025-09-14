#!/usr/bin/env python3
"""
Simple Workflow Manager
Check status, stop everything, restart everything
"""
import sys
import os
import time
import subprocess
import logging
import argparse
from datetime import datetime
import glob
import re

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_trading_monitor_progress():
    """Get current trading monitor cycle from logs"""
    try:
        # Look for the most recent task log for step5_trading_monitor
        log_pattern = "/home/chris_s_dodd/optcom-1/airflow_project/logs/dag_id=simple_trading_workflow/run_id=*/task_id=step5_trading_monitor/attempt=*.log"
        log_files = glob.glob(log_pattern)
        
        if not log_files:
            return None
            
        # Get the most recent log file
        latest_log = max(log_files, key=os.path.getmtime)
        
        # Read the last few lines to find cycle information
        with open(latest_log, 'r') as f:
            lines = f.readlines()
            
        # Look for cycle information in the last 50 lines
        cycle_info = None
        for line in reversed(lines[-50:]):
            # Look for patterns like "Cycle 15/120" or "Running cycle 15"
            cycle_match = re.search(r'[Cc]ycle\s+(\d+)', line)
            if cycle_match:
                cycle_num = cycle_match.group(1)
                cycle_info = f"Cycle {cycle_num} running"
                break
                
        return cycle_info
        
    except Exception as e:
        return None

def check_workflow_status():
    """Check which step the workflow is currently on"""
    print("🔍 SIMPLE WORKFLOW STATUS")
    print("=" * 50)
    
    try:
        # Check if Airflow is running
        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        airflow_running = 'airflow' in result.stdout
        
        print(f"Airflow Status: {'🟢 Running' if airflow_running else '🔴 Not Running'}")
        
        if not airflow_running:
            print("\n❌ Airflow is not running. Start it with: airflow standalone")
            return
        
        # Check DAG runs using airflow CLI
        airflow_home = '/home/chris_s_dodd/optcom-1/airflow_project'
        env = os.environ.copy()
        env['AIRFLOW_HOME'] = airflow_home
        
        # Get latest DAG run
        result = subprocess.run([
            'airflow', 'dags', 'list-runs', 'simple_trading_workflow'
        ], capture_output=True, text=True, env=env)
        
        if result.returncode != 0:
            print("❌ Cannot access workflow status")
            print("Try: airflow dags list")
            return
        
        lines = result.stdout.strip().split('\n')
        if len(lines) <= 1:
            print("⚪ No workflow runs found")
            print("To start: airflow dags trigger simple_trading_workflow")
            return
        
        
        # Find the running DAG (not just the first one)
        running_run_id = None
        for i, line in enumerate(lines[1:], 1):  # Skip header, but track index
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 3 and parts[2] == 'running':
                # Found a running DAG, extract run_id from parts[1] and potentially the next line
                run_id = parts[1].strip()
                
                # Check if the next line contains the continuation of the run_id
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    next_parts = [p.strip() for p in next_line.split('|')]
                    # If next line starts with empty DAG name, it's a continuation
                    if len(next_parts) >= 2 and next_parts[0] == '' and next_parts[1] != '':
                        run_id += next_parts[1].strip()
                
                running_run_id = run_id
                break
        
        if not running_run_id:
            print("⚪ No running workflow found")
            return
        
        print(f"Running Workflow: {running_run_id}")
        print(f"State: running")
        
        # Check individual task states for the running workflow
        result = subprocess.run([
            'airflow', 'tasks', 'states-for-dag-run', 'simple_trading_workflow', running_run_id
        ], capture_output=True, text=True, env=env)
        
        if result.returncode == 0:
            print("\nStep Status:")
            task_lines = result.stdout.strip().split('\n')[1:]  # Skip header
            
            step_names = {
                'step1_check_data': 'Step 1: Check Data',
                'step2_run_scraper': 'Step 2: Run Scraper',
                'step2_5_validate_contracts': 'Step 2.5: Validate Contracts',
                'step3_verify_records': 'Step 3: Verify Records',
                'step4_start_gateways': 'Step 4: Start Gateways',
                'step5_trading_monitor': 'Step 5: Trading Monitor'
            }
            
            current_step = "Workflow not started"
            
            for line in task_lines:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 4:
                    task_id = parts[2]
                    task_state = parts[3]
                    
                    if task_id in step_names:
                        status_icon = {
                            'success': '✅',
                            'running': '🟡', 
                            'failed': '❌',
                            'upstream_failed': '⚠️',
                            'skipped': '⏩',
                            'queued': '⏳',
                            'scheduled': '⏳'
                        }.get(task_state, '❓')
                        
                        print(f"  {step_names[task_id]}: {status_icon} {task_state}")
                        
                        if task_state in ['running', 'queued', 'scheduled']:
                            current_step = step_names[task_id]
                            
                            # Show cycle progress for trading monitor
                            if task_id == 'step5_trading_monitor' and task_state == 'running':
                                try:
                                    cycle_info = get_trading_monitor_progress()
                                    if cycle_info:
                                        print(f"    📊 {cycle_info}")
                                except Exception:
                                    pass  # Don't fail status if can't get cycle info
            
            print(f"\n🎯 Current Status: {current_step}")
        else:
            print(f"\n❌ Task states query failed")
            return
        
        # Check gateway status
        print(f"\n🚪 Gateway Status:")
        from ib_gateway_utils import IBGatewayManager
        try:
            manager = IBGatewayManager()
            success, status = manager.check_status()
            print(status)
        except Exception as e:
            print(f"❌ Cannot check gateway status: {e}")
        
    except Exception as e:
        logger.error(f"Status check failed: {e}")

def stop_everything():
    """Stop everything - workflow, airflow, gateways"""
    print("🛑 STOPPING EVERYTHING")
    print("=" * 30)
    
    # Stop Airflow
    print("Stopping Airflow...")
    try:
        subprocess.run(['pkill', '-f', 'airflow standalone'], check=False)
        print("✅ Airflow stopped")
    except Exception as e:
        print(f"⚠️ Error stopping Airflow: {e}")
    
    # Stop gateways
    print("Stopping IB Gateways...")
    try:
        from ib_gateway_utils import IBGatewayManager
        manager = IBGatewayManager()
        success = manager.stop_gateways()
        if success:
            print("✅ Gateways stopped")
        else:
            print("⚠️ Gateway stop may have failed")
    except Exception as e:
        print(f"⚠️ Error stopping gateways: {e}")
    
    # Kill any remaining processes
    print("Cleaning up processes...")
    try:
        subprocess.run(['pkill', '-f', 'java.*IbcGateway'], check=False)
        print("✅ Process cleanup complete")
    except Exception as e:
        print(f"⚠️ Process cleanup error: {e}")
    
    print("🏁 Everything stopped")

def start_workflow():
    """Start the complete workflow"""
    print("🚀 STARTING SIMPLE WORKFLOW")
    print("=" * 35)
    
    # Set environment
    os.environ['AIRFLOW_HOME'] = '/home/chris_s_dodd/optcom-1/airflow_project'
    
    # Start Airflow in background if not running
    result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
    if 'airflow' not in result.stdout:
        print("Starting Airflow...")
        subprocess.Popen(['airflow', 'standalone'], 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE)
        print("⏳ Waiting for Airflow to start...")
        time.sleep(10)
    
    # Trigger the workflow
    print("Triggering workflow...")
    result = subprocess.run([
        'airflow', 'dags', 'trigger', 'simple_trading_workflow'
    ], capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ Workflow started successfully")
        print("Monitor with: python workflow_manager.py status")
    else:
        print(f"❌ Failed to start workflow: {result.stderr}")

def restart_everything():
    """Full restart - stop everything then start workflow"""
    print("🔄 FULL RESTART")
    print("=" * 20)
    
    stop_everything()
    print("\n⏳ Waiting 5 seconds...")
    time.sleep(5)
    start_workflow()

def main():
    parser = argparse.ArgumentParser(description='Simple Workflow Manager')
    parser.add_argument('action', choices=['status', 'stop', 'start', 'restart'], 
                       help='Action to perform')
    
    args = parser.parse_args()
    
    try:
        if args.action == 'status':
            check_workflow_status()
        elif args.action == 'stop':
            stop_everything()
        elif args.action == 'start':
            start_workflow()
        elif args.action == 'restart':
            restart_everything()
            
    except Exception as e:
        logger.error(f"Action {args.action} failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()