"""
Simple Trading Workflow DAG
5 clear steps with no bells and whistles
test comment added 22/12/2025
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
from options_contract_validator import run_contract_validation
from market_snapshots import run_market_snapshots
from greeks_capture import run_greeks_capture
from eod_data_collection import collect_eod_data
from trade_perspectives_scraper import run_perspectives_scraper

# Simple DAG configuration
default_args = {
    'owner': 'trading',
    'depends_on_past': False,
    'start_date': datetime(2024, 8, 24),
    'retries': 1,  # Allow 1 retry for transient errors
    'retry_delay': timedelta(seconds=30),
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
# STEP 2.5: Validate and correct options contracts
# ============================================================================
def step2_5_validate_contracts(**context):
    """Step 2.5: Validate options contracts and correct expiry dates"""
    print("🔍 STEP 2.5: Validating options contracts...")

    # Check if we should skip this step (if data already existed)
    data_exists = context['task_instance'].xcom_pull(key='data_exists', task_ids='step1_check_data')
    if data_exists:
        print("⏩ Skipping contract validation - using existing data")
        context['task_instance'].xcom_push(key='validation_stats', value={'skipped': True})
        return "SKIPPED: Using existing data"

    try:
        # Run contract validation
        print("Starting options contract validation...")
        stats = run_contract_validation(port=4002)

        # Store results for Step 3
        context['task_instance'].xcom_push(key='validation_stats', value=stats)

        print(f"✅ Contract validation completed:")
        print(f"   Total records: {stats['total_records']}")
        print(f"   Valid original: {stats['valid_original']}")
        print(f"   Corrected dates: {stats['corrected_dates']}")
        print(f"   Failed validation: {stats['failed_validation']}")

        return f"COMPLETED: {stats['corrected_dates']} dates corrected, {stats['failed_validation']} failed"

    except Exception as e:
        print(f"⚠️ Contract validation encountered an error: {e}")
        print("Continuing workflow - this step is non-blocking")
        context['task_instance'].xcom_push(key='validation_stats', value={'error': str(e)})
        return f"ERROR (non-blocking): {str(e)}"

step2_5 = PythonOperator(
    task_id='step2_5_validate_contracts',
    python_callable=step2_5_validate_contracts,
    execution_timeout=timedelta(minutes=10),  # 10 minutes timeout
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
    
    # Start gateways with enhanced 2FA retry support
    print("Starting gateways with 2FA retry...")
    success = manager.start_gateways_with_2fa_retry()
    
    if not success:
        raise Exception("Failed to start gateways")
    
    print("✅ Gateways started successfully")
    return "COMPLETED: Both gateways running"

step4 = PythonOperator(
    task_id='step4_start_gateways',
    python_callable=step4_start_gateways,
    execution_timeout=timedelta(minutes=100),  # 100 minutes for 2FA with retries (90 min + buffer)
    dag=dag
)

# ============================================================================
# STEP 5: Run trading monitor with market snapshots and Greeks capture
# ============================================================================
def step5_trading_monitor(**context):
    """Step 5: Run trading monitor with integrated market snapshots and Greeks capture every 30 minutes"""
    print("📊 STEP 5: Running trading monitor with market snapshots and Greeks capture...")

    import time
    from datetime import datetime, timezone

    # Configuration
    monitor_interval = 120  # 2 minutes between monitor cycles
    snapshot_interval = 1800  # 30 minutes between snapshots and Greeks (30 * 60)
    max_cycles = 1000
    stop_hour = 21  # Stop at 21:15 GMT
    stop_minute = 15

    last_snapshot_time = 0
    cycles_completed = 0

    print(f"Starting integrated monitoring:")
    print(f"  - Trading monitor: every {monitor_interval} seconds")
    print(f"  - Market snapshots + Greeks: every {snapshot_interval} seconds (30 minutes)")
    print(f"  - Auto-stop at {stop_hour:02d}:{stop_minute:02d} GMT")

    for cycle in range(max_cycles):
        cycle_start = time.time()
        cycles_completed += 1

        # Check if we should stop based on time
        now_utc = datetime.now(timezone.utc)
        if now_utc.hour > stop_hour or (now_utc.hour == stop_hour and now_utc.minute >= stop_minute):
            print(f"\n⏰ Reached stop time ({stop_hour:02d}:{stop_minute:02d} GMT). Current time: {now_utc.strftime('%H:%M')} GMT")
            print(f"Stopping trading monitor after {cycles_completed} cycles")
            break

        # Check if it's time for a snapshot
        time_since_last_snapshot = cycle_start - last_snapshot_time
        if time_since_last_snapshot >= snapshot_interval or last_snapshot_time == 0:
            print(f"\n📸 Taking market snapshot (cycle {cycles_completed})...")
            try:
                result = run_market_snapshots(
                    port=4002,
                    account_id="DU9233079"
                )

                if result['success']:
                    print(f"✅ Snapshot captured: {result['snapshots_created']} snapshots, "
                          f"{result['positions_retrieved']} positions")
                else:
                    print(f"⚠️ Snapshot failed: {result.get('error', 'Unknown error')}")
            except Exception as e:
                print(f"⚠️ Snapshot error: {e}")

            # Capture Greeks (immediately after snapshots)
            print(f"\n🔢 Capturing options Greeks...")
            try:
                greeks_result = run_greeks_capture(
                    port=4002,
                    account_id="DU9233079"
                )

                if greeks_result['success']:
                    print(f"✅ Greeks captured: {greeks_result['greeks_captured']} spreads, "
                          f"{greeks_result['positions_retrieved']} positions")
                else:
                    print(f"⚠️ Greeks capture failed: {greeks_result.get('error', 'Unknown error')}")
            except Exception as e:
                print(f"⚠️ Greeks capture error: {e}")

            last_snapshot_time = cycle_start

        # Run one cycle of trading monitor
        print(f"\n🔄 Running trading cycle {cycles_completed}/{max_cycles}...")
        try:
            run_trading_monitor(
                cycles=1,
                port=4002,
                allow_market_closed=True,
                interval=monitor_interval
            )
        except Exception as e:
            print(f"⚠️ Trading monitor error: {e}")
            # Continue anyway - don't break the loop

        # Wait for next cycle (monitor already includes interval wait)
        # No additional sleep needed here

    print(f"\n✅ Trading monitor completed: {cycles_completed} cycles")
    return f"COMPLETED: {cycles_completed} cycles"

step5 = PythonOperator(
    task_id='step5_trading_monitor',
    python_callable=step5_trading_monitor,
    dag=dag
)

# ============================================================================
# STEP 6: Collect end-of-day orders and trades
# ============================================================================
def step6_collect_eod_data(**context):
    """Step 6: Collect completed orders and trades from IBKR"""
    print("📋 STEP 6: Collecting end-of-day orders and trades...")

    from datetime import date

    collection_date = date.today()

    try:
        orders_count, trades_count = collect_eod_data(
            collection_date=collection_date,
            port=4002,
            host='127.0.0.1'
        )

        print(f"✅ EOD collection completed:")
        print(f"   Orders collected: {orders_count}")
        print(f"   Trades collected: {trades_count}")

        # Store results in XCom
        context['task_instance'].xcom_push(key='orders_count', value=orders_count)
        context['task_instance'].xcom_push(key='trades_count', value=trades_count)

        return f"COMPLETED: {orders_count} orders, {trades_count} trades"

    except Exception as e:
        print(f"⚠️ EOD collection error: {e}")
        # Don't fail the workflow - this is informational
        return f"ERROR: {str(e)}"

step6 = PythonOperator(
    task_id='step6_collect_eod_data',
    python_callable=step6_collect_eod_data,
    execution_timeout=timedelta(minutes=5),
    dag=dag
)

# ============================================================================
# STEP 7: Scrape trade perspectives
# ============================================================================
def step7_scrape_perspectives(**context):
    """Step 7: Scrape trade perspectives from optionrecom.com"""
    print("📊 STEP 7: Scraping trade perspectives...")

    try:
        start_time = datetime.now()
        closed_count, open_count = run_perspectives_scraper(headless=True)
        elapsed = (datetime.now() - start_time).total_seconds()

        print(f"✅ Perspectives scraping completed in {elapsed:.1f} seconds:")
        print(f"   Closed perspectives: {closed_count}")
        print(f"   Open perspectives: {open_count}")

        # Store results in XCom for debugging/logging
        context['task_instance'].xcom_push(key='closed_count', value=closed_count)
        context['task_instance'].xcom_push(key='open_count', value=open_count)

        return f"COMPLETED: {closed_count} closed, {open_count} open"

    except Exception as e:
        print(f"⚠️ Perspectives scraping error: {e}")
        # Don't fail the workflow - this is informational/enrichment
        return f"ERROR (non-blocking): {str(e)}"

step7 = PythonOperator(
    task_id='step7_scrape_perspectives',
    python_callable=step7_scrape_perspectives,
    execution_timeout=timedelta(minutes=15),
    dag=dag
)

# ============================================================================
# Define simple linear dependencies
# ============================================================================
step1 >> step2 >> step2_5 >> step3 >> step4 >> step5 >> step6 >> step7

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
        steps = ['step1_check_data', 'step2_run_scraper', 'step2_5_validate_contracts', 'step3_verify_records',
                'step4_start_gateways', 'step5_trading_monitor', 'step6_collect_eod_data', 'step7_scrape_perspectives']
        
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