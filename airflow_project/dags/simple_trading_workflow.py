"""
Simple Trading Workflow DAG
5 clear steps with no bells and whistles
"""
import sys
import os
import time
import logging
from datetime import datetime, timedelta

# Add scripts directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.standard.operators.bash import BashOperator

# Import our functions
from options_scraper import run_options_scraper
from trading_monitor import run_trading_monitor
from ib_gateway_utils import IBGatewayManager
from database_utils import connect_to_database, close_database_connection, check_data_freshness

# Simple DAG configuration
default_args = {
    'owner': 'trading',
    'depends_on_past': False,
    'start_date': datetime(2024, 8, 24),
    'retries': 0,  # No retries - fail fast
    'max_active_runs': 1,
}

dag = DAG(
    'simple_trading_workflow',
    default_args=default_args,
    description='Simple 5-Step Trading Workflow',
    schedule=None,  # Manual trigger only
    catchup=False,
    max_active_runs=1,
    tags=['trading', 'simple']
)

# ============================================================================
# STEP 1: Check for today's data
# ============================================================================
def step1_check_data(**context):
    """Step 1: Check if we have data for today"""
    print("🔍 STEP 1: Checking for today's data...")
    
    conn, cursor = connect_to_database()
    if not conn:
        raise Exception("Failed to connect to database")
    
    try:
        from datetime import date
        today = date.today().strftime('%Y-%m-%d')
        data_is_fresh, details = check_data_freshness(cursor, today)
        
        # Store result for next steps
        context['task_instance'].xcom_push(key='data_exists', value=data_is_fresh)
        context['task_instance'].xcom_push(key='record_count', value=details.get('same_day_count', 0))
        
        if data_is_fresh:
            print(f"✅ Found {details['same_day_count']} records for {today}")
            print("⏩ Will skip scraping and go to step 4")
            return f"SKIP_TO_STEP4: {details['same_day_count']} records found"
        else:
            print(f"❌ No data found for {today}")
            print("➡️ Will proceed to step 2 (scraping)")
            return "PROCEED_TO_STEP2: No data found"
            
    finally:
        close_database_connection(conn, cursor)

step1 = PythonOperator(
    task_id='step1_check_data',
    python_callable=step1_check_data,
    dag=dag
)

# ============================================================================
# STEP 2: Run scraper (conditional)
# ============================================================================
def step2_run_scraper(**context):
    """Step 2: Run options scraper"""
    print("🚀 STEP 2: Running options scraper...")
    
    # Check if we should skip this step
    data_exists = context['task_instance'].xcom_pull(key='data_exists', task_ids='step1_check_data')
    if data_exists:
        print("⏩ Skipping scraper - data already exists")
        return "SKIPPED: Data already exists"
    
    print("Starting scraper...")
    records_scraped = run_options_scraper(test_mode=False, headless=True)
    
    print(f"✅ Scraper completed: {records_scraped} records")
    return f"COMPLETED: {records_scraped} records scraped"

step2 = PythonOperator(
    task_id='step2_run_scraper',
    python_callable=step2_run_scraper,
    execution_timeout=timedelta(minutes=30),
    dag=dag
)

# ============================================================================
# STEP 3: Verify scraper wrote records
# ============================================================================
def step3_verify_records(**context):
    """Step 3: Verify scraper actually wrote records"""
    print("✅ STEP 3: Verifying records were written...")
    
    # Check if scraper was skipped
    data_exists = context['task_instance'].xcom_pull(key='data_exists', task_ids='step1_check_data')
    if data_exists:
        record_count = context['task_instance'].xcom_pull(key='record_count', task_ids='step1_check_data')
        print(f"⏩ Using existing {record_count} records")
        return f"EXISTING: {record_count} records verified"
    
    # Verify new records were written
    conn, cursor = connect_to_database()
    if not conn:
        raise Exception("Failed to connect to database for verification")
    
    try:
        from datetime import date
        today = date.today().strftime('%Y-%m-%d')
        data_is_fresh, details = check_data_freshness(cursor, today)
        
        if data_is_fresh and details['same_day_count'] > 0:
            print(f"✅ Verification successful: {details['same_day_count']} records found")
            return f"VERIFIED: {details['same_day_count']} records"
        else:
            raise Exception("Scraper failed to write records to database")
            
    finally:
        close_database_connection(conn, cursor)

step3 = PythonOperator(
    task_id='step3_verify_records',
    python_callable=step3_verify_records,
    dag=dag
)

# ============================================================================
# STEP 4: Start gateways with smart polling
# ============================================================================
def step4_start_gateways(**context):
    """Step 4: Start IB gateways and wait for them to be ready"""
    print("🚪 STEP 4: Starting IB gateways...")
    
    manager = IBGatewayManager()
    
    # Start gateways
    print("Starting gateways...")
    success = manager.start_gateways()
    
    if not success:
        raise Exception("Failed to start gateways")
    
    print("✅ Gateways started successfully")
    return "COMPLETED: Both gateways running"

step4 = PythonOperator(
    task_id='step4_start_gateways',
    python_callable=step4_start_gateways,
    execution_timeout=timedelta(minutes=15),  # 15 minutes for 2FA
    dag=dag
)

# ============================================================================
# STEP 5: Run trading monitor
# ============================================================================
def step5_trading_monitor(**context):
    """Step 5: Run trading monitor (leave running)"""
    print("📊 STEP 5: Running trading monitor...")
    
    # Run for specified number of cycles
    cycles_completed = run_trading_monitor(
        cycles=1000,
        port=4002,     # Paper trading port
        allow_market_closed=True,
        interval=120    # 2 minute intervals
    )
    
    print(f"✅ Trading monitor completed: {cycles_completed} cycles")
    return f"COMPLETED: {cycles_completed} cycles"

step5 = PythonOperator(
    task_id='step5_trading_monitor',
    python_callable=step5_trading_monitor,
    dag=dag
)

# ============================================================================
# Define simple linear dependencies
# ============================================================================
step1 >> step2 >> step3 >> step4 >> step5

# ============================================================================
# Add status checking DAG for debugging
# ============================================================================
status_dag = DAG(
    'workflow_status_checker',
    default_args={**default_args, 'schedule': None},
    description='Check workflow status and individual steps',
    catchup=False,
    tags=['status', 'debug']
)

def check_workflow_status(**context):
    """Check which step the workflow is currently on"""
    from airflow.models import DagRun, TaskInstance
    from airflow import settings
    
    print("🔍 WORKFLOW STATUS CHECK")
    print("=" * 50)
    
    # Get the latest DAG run
    session = settings.Session()
    try:
        latest_run = session.query(DagRun).filter(
            DagRun.dag_id == 'simple_trading_workflow'
        ).order_by(DagRun.execution_date.desc()).first()
        
        if not latest_run:
            print("❌ No workflow runs found")
            return "NO_RUNS"
        
        print(f"Latest run: {latest_run.run_id}")
        print(f"State: {latest_run.state}")
        print(f"Started: {latest_run.start_date}")
        
        # Check each step status
        steps = ['step1_check_data', 'step2_run_scraper', 'step3_verify_records', 
                'step4_start_gateways', 'step5_trading_monitor']
        
        current_step = "Not started"
        for i, step in enumerate(steps, 1):
            task_instance = session.query(TaskInstance).filter(
                TaskInstance.dag_id == 'simple_trading_workflow',
                TaskInstance.run_id == latest_run.run_id,
                TaskInstance.task_id == step
            ).first()
            
            if task_instance:
                status_icon = {
                    'success': '✅',
                    'running': '🟡',
                    'failed': '❌',
                    'upstream_failed': '⚠️',
                    'skipped': '⏩',
                    'queued': '⏳'
                }.get(task_instance.state, '❓')
                
                print(f"Step {i}: {step} - {status_icon} {task_instance.state}")
                
                if task_instance.state in ['running', 'queued']:
                    current_step = f"Step {i}: {step}"
                elif task_instance.state == 'success' and i < len(steps):
                    # Check if next step is running
                    next_step = steps[i] if i < len(steps) else None
                    if next_step:
                        next_task = session.query(TaskInstance).filter(
                            TaskInstance.dag_id == 'simple_trading_workflow',
                            TaskInstance.run_id == latest_run.run_id,
                            TaskInstance.task_id == next_step
                        ).first()
                        if not next_task or next_task.state in [None, 'none']:
                            current_step = f"Ready for Step {i+1}"
            else:
                print(f"Step {i}: {step} - ⚪ Not started")
        
        print(f"\n🎯 Current Status: {current_step}")
        return current_step
        
    finally:
        session.close()

status_check = PythonOperator(
    task_id='check_status',
    python_callable=check_workflow_status,
    dag=status_dag
)