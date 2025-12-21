"""
End-of-Day Data Collection DAG

Collects completed orders and trades from IBKR at end of trading day.

Schedule: 21:20 UK time (4:20 PM ET) - Monday to Friday
- Runs after trading monitor stops at 21:15
- Before VM shutdown at 22:00 UK (5:00 PM ET)

Dependencies:
- Requires IB Gateway running (assumes main workflow is still active)
- Uses paper gateway on port 4002

Author: Automated Trading System
"""

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import os
import sys

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from database.database_config import DatabaseConnection

# ============================================================================
# DAG Configuration
# ============================================================================

default_args = {
    'owner': 'trading-system',
    'depends_on_past': False,
    'start_date': datetime(2025, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=2),
}

dag = DAG(
    'eod_data_collection_workflow',
    default_args=default_args,
    description='Collect end-of-day orders and trades from IBKR',
    schedule='20 21 * * 1-5',  # 9:20 PM UK, Monday-Friday
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=['trading', 'eod', 'data-collection'],
)

# ============================================================================
# Helper Functions
# ============================================================================

def check_gateway_status():
    """
    Check if IB Gateway is running on port 4002

    Raises:
        Exception if gateway is not accessible
    """
    import socket

    host = '127.0.0.1'
    port = 4002

    print(f"Checking if IB Gateway is running on {host}:{port}...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)

    try:
        result = sock.connect_ex((host, port))
        if result == 0:
            print(f"✓ IB Gateway is running on port {port}")
            return True
        else:
            raise Exception(f"IB Gateway is not accessible on port {port}. "
                          f"Main workflow should be running to keep gateway active.")
    finally:
        sock.close()


def verify_data_collection(**context):
    """
    Verify that data was collected and inserted into database

    Checks:
    - Records in eod_orders table for today
    - Records in eod_trades table for today
    - Logs summary of collected data
    """
    from datetime import date

    collection_date = date.today()

    print(f"Verifying EOD data collection for {collection_date}...")

    db = DatabaseConnection()

    with db.get_connection() as conn:
        cursor = db.get_cursor(conn)

        # Check orders
        cursor.execute("""
            SELECT COUNT(*),
                   COUNT(DISTINCT underlying_symbol),
                   SUM(CASE WHEN status = 'Filled' THEN 1 ELSE 0 END) as filled_orders
            FROM eod_orders
            WHERE collection_date = %s
        """, (collection_date,))

        result = cursor.fetchone()
        orders_count = result[0] if result[0] else 0
        orders_symbols = result[1] if result[1] else 0
        filled_orders = result[2] if result[2] else 0

        # Check trades
        cursor.execute("""
            SELECT COUNT(*),
                   COUNT(DISTINCT underlying_symbol),
                   SUM(commission)
            FROM eod_trades
            WHERE collection_date = %s
        """, (collection_date,))

        result = cursor.fetchone()
        trades_count = result[0] if result[0] else 0
        trades_symbols = result[1] if result[1] else 0
        total_commission = result[2] if result[2] else 0.0

        # Get trade details
        cursor.execute("""
            SELECT underlying_symbol, spread_name, spread_action, spread_price, commission
            FROM eod_trades
            WHERE collection_date = %s
            ORDER BY execution_time
        """, (collection_date,))

        trades = cursor.fetchall()

    print(f"\n{'='*70}")
    print(f"EOD Data Collection Summary for {collection_date}")
    print(f"{'='*70}")
    print(f"Total Orders: {orders_count} ({filled_orders} filled)")
    print(f"Order Symbols: {orders_symbols}")
    print(f"Total Trades: {trades_count}")
    print(f"Trade Symbols: {trades_symbols}")
    print(f"Total Commission: ${total_commission:.2f}")
    print(f"{'='*70}\n")

    if trades:
        print("Trades Collected:")
        print(f"{'Symbol':<10} {'Spread':<30} {'Action':<8} {'Price':<10} {'Commission':<10}")
        print("-" * 70)
        for trade in trades:
            symbol, spread, action, price, comm = trade
            print(f"{symbol:<10} {spread:<30} {action:<8} ${price:<9.2f} ${comm:<9.2f}")
        print()
    else:
        print("⚠ No trades collected (this may be normal if no trading activity today)\n")

    # Store in XCom for potential downstream tasks
    context['task_instance'].xcom_push(key='orders_count', value=orders_count)
    context['task_instance'].xcom_push(key='filled_orders', value=filled_orders)
    context['task_instance'].xcom_push(key='trades_count', value=trades_count)
    context['task_instance'].xcom_push(key='symbols_count', value=trades_symbols)
    context['task_instance'].xcom_push(key='total_commission', value=total_commission)

    return {
        'orders_count': orders_count,
        'filled_orders': filled_orders,
        'trades_count': trades_count,
        'symbols_count': trades_symbols,
        'total_commission': total_commission
    }


# ============================================================================
# Tasks
# ============================================================================

# Task 1: Check Gateway Status
check_gateway_task = PythonOperator(
    task_id='check_gateway_running',
    python_callable=check_gateway_status,
    dag=dag,
)

# Task 2: Collect EOD Data
collect_eod_task = BashOperator(
    task_id='collect_eod_data',
    bash_command=(
        'cd {{ params.project_root }}/airflow_project && '
        'python scripts/eod_data_collection.py --date {{ ds }} --port 4002'
    ),
    params={
        'project_root': project_root
    },
    dag=dag,
)

# Task 3: Verify Data Collection
verify_data_task = PythonOperator(
    task_id='verify_data_inserted',
    python_callable=verify_data_collection,
    dag=dag,
)

# ============================================================================
# Task Dependencies
# ============================================================================

check_gateway_task >> collect_eod_task >> verify_data_task
