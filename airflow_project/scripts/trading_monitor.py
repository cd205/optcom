"""
Trading Monitor Module
Refactored from monitor_and_execution_2.ipynb for Airflow compatibility
"""
import os
import sys
import time
import logging
import subprocess
import argparse
import random
from datetime import date
from typing import Optional

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import gateway management
from ib_gateway_utils import IBGatewayManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TradingMonitorConfig:
    """Configuration for the trading monitor"""
    def __init__(self, cycles: int = 1, port: int = 4002, 
                 allow_market_closed: bool = False, interval: int = 60):
        self.cycles = cycles
        self.port = port
        self.allow_market_closed = allow_market_closed
        self.interval = interval
        
        # Set up paths
        self.script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.log_dir = os.path.join(self.script_dir, '..', 'monitor', 'output', 'logs')
        os.makedirs(self.log_dir, exist_ok=True)

def cleanup_old_logs(log_dir: str):
    """
    Clean up old log files, keeping only logs from today
    """
    today = date.today()
    today_str = today.strftime('%Y-%m-%d')
    
    log_files_to_cleanup = [
        os.path.join(log_dir, "trader.log"),
        os.path.join(log_dir, "..", "..", "..", "output", "logs", "price_monitor.log"),
        os.path.join(log_dir, "vertical_spread_order.log")
    ]
    
    total_space_freed = 0
    
    for log_file in log_files_to_cleanup:
        if os.path.exists(log_file):
            try:
                original_size = os.path.getsize(log_file)
                
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                
                today_lines = []
                for line in lines:
                    if line.startswith(today_str):
                        today_lines.append(line)
                
                with open(log_file, 'w') as f:
                    f.writelines(today_lines)
                
                new_size = os.path.getsize(log_file)
                space_freed = original_size - new_size
                total_space_freed += space_freed
                
                if space_freed > 0:
                    logger.info(f"✅ Cleaned {log_file}: {space_freed/1024/1024:.1f}MB freed ({len(today_lines)} lines kept)")
                else:
                    logger.info(f"✓ {log_file}: No cleanup needed")
                    
            except Exception as e:
                logger.error(f"❌ Error cleaning {log_file}: {e}")
    
    if total_space_freed > 0:
        logger.info(f"🎉 Total space freed: {total_space_freed/1024/1024:.1f}MB")
    else:
        logger.info("ℹ️  No log cleanup was needed")

def find_monitor_script(script_name: str) -> str:
    """
    Find monitor script with robust path resolution
    
    Args:
        script_name: Name of the script to find
        
    Returns:
        str: Path to script or None if not found
    """
    # Get the project root directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))  # Go up to optcom-1
    
    script_paths = [
        # Relative paths from airflow_project/scripts
        os.path.join('..', '..', 'monitor', script_name),
        os.path.join('..', 'monitor', script_name),
        # Absolute path
        os.path.join(project_root, 'monitor', script_name),
        # Current directory fallback
        script_name
    ]
    
    for path in script_paths:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            logger.info(f"Found {script_name} at: {abs_path}")
            return abs_path
    
    logger.error(f"Could not find {script_name} in any of these locations:")
    for path in script_paths:
        logger.error(f"  - {os.path.abspath(path)}")
    return None

def run_price_monitor(runtime: int = 120, port: int = 4002) -> bool:
    """
    Run the price monitor script with specified runtime
    
    Args:
        runtime: How long to run the price monitor (in seconds)
        port: IBKR port to connect to
        
    Returns:
        bool: True if successful, False otherwise
    """
    logger.info(f"Starting price monitor with runtime: {runtime} seconds...")
    
    script_path = find_monitor_script('price_monitor.py')
    if not script_path:
        return False
    
    try:
        cmd = [sys.executable, script_path, '--runtime', str(runtime), '--port', str(port)]
        
        # Change to the directory containing the script to ensure proper path resolution
        script_dir = os.path.dirname(script_path)
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True,
            cwd=script_dir  # Run in the script's directory
        )
        
        try:
            timeout_buffer = max(90, runtime // 2)
            stdout, stderr = process.communicate(timeout=runtime + timeout_buffer)
            exit_code = process.returncode
            
            if stdout:
                logger.info(stdout)
            
            if exit_code == 0:
                logger.info("Price monitor completed successfully")
                time.sleep(3)
                return True
            else:
                logger.error(f"Price monitor exited with code {exit_code}")
                return False
                
        except subprocess.TimeoutExpired:
            process.kill()
            logger.error("Price monitor timed out")
            return False
    
    except Exception as e:
        logger.error(f"Error running price monitor: {e}")
        return False

def run_order_placement(port: int = 4002, allow_market_closed: bool = False) -> bool:
    """
    Run the order placement script
    
    Args:
        port: IBKR port to connect to
        allow_market_closed: Whether to allow orders when market is closed
        
    Returns:
        bool: True if successful, False otherwise
    """
    logger.info("Starting order placement...")
    
    script_path = find_monitor_script('vertical_spread_order.py')
    if not script_path:
        return False
    
    try:
        client_id = random.randint(100, 9999)
        
        cmd = [sys.executable, script_path, '--client', str(client_id), '--port', str(port)]
        
        if allow_market_closed:
            cmd.append('--allow-market-closed')
        
        # Change to the directory containing the script to ensure proper path resolution
        script_dir = os.path.dirname(script_path)
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True,
            cwd=script_dir  # Run in the script's directory
        )
        
        try:
            stdout, _ = process.communicate(timeout=120)
            exit_code = process.returncode
            
            if stdout:
                logger.info(stdout)
            
            if exit_code == 0:
                logger.info("Order placement completed successfully")
                return True
            else:
                logger.error(f"Order placement exited with code {exit_code}")
                return False
                
        except subprocess.TimeoutExpired:
            process.kill()
            logger.error("Order placement timed out")
            return False
    
    except Exception as e:
        logger.error(f"Error running order placement: {e}")
        return False

def run_trading_monitor(cycles: int = 1, port: int = 4002, 
                       allow_market_closed: bool = False, interval: int = 60, 
                       **_context) -> int:
    """
    Run the full trading system for specified number of cycles
    Airflow-compatible version
    
    Args:
        cycles: Number of trading cycles to run
        port: IBKR port to connect to
        allow_market_closed: Whether to allow orders when markets are closed
        interval: Seconds to wait between cycle starts
        **context: Airflow context (ignored for standalone execution)
        
    Returns:
        int: Number of completed cycles
    """
    config = TradingMonitorConfig(cycles, port, allow_market_closed, interval)
    
    # Clean up old logs at the start
    logger.info("🧹 Cleaning up old log files...")
    cleanup_old_logs(config.log_dir)
    
    logger.info("=" * 80)
    logger.info(f"Starting automated trading system (port: {port}, cycles: {cycles})")
    logger.info("=" * 80)
    
    cycle_count = 0
    
    # Main loop
    while cycle_count < cycles:
        cycle_count += 1
        logger.info(f"Starting cycle {cycle_count} of {cycles}")
        
        cycle_start = time.time()
        
        # Step 0: Check gateway health with improved logic
        logger.info("Step 0: Checking gateway health...")
        try:
            manager = IBGatewayManager()

            # Use individual status check for better diagnostics
            paper_running, live_running, status, live_2fa_pending = manager.check_individual_status()

            logger.info(f"Gateway Status: Paper={paper_running}, Live={live_running}, Live2FA={live_2fa_pending}")

            # Be more tolerant of 2FA pending states
            if paper_running and (live_running or live_2fa_pending):
                logger.info("✅ Gateways in acceptable state for trading")
                if live_2fa_pending:
                    logger.info("🔐 Live gateway pending 2FA - trading will use paper account")
            elif not paper_running and not live_running:
                logger.warning("⚠️ Both gateways down - attempting smart restart...")

                # Use smart restart instead of aggressive restart
                restart_success = manager.smart_restart_gateway()
                
                if restart_success:
                    logger.info("✅ Smart restart completed, waiting for initialization...")
                    time.sleep(90)  # Wait for gateways to initialize

                    # Re-check status after restart
                    paper_running, live_running, status, live_2fa_pending = manager.check_individual_status()
                    if paper_running or live_running:
                        logger.info("✅ At least one gateway confirmed running after restart")
                    else:
                        logger.warning("⚠️ Gateways still not fully ready - continuing with monitoring...")
                else:
                    logger.warning("⚠️ Smart restart had issues - continuing anyway...")
            elif paper_running:
                logger.info("✅ Paper gateway running - sufficient for most trading operations")
            else:
                logger.info("ℹ️ Only live gateway running - check if paper gateway needed")
                
        except Exception as e:
            logger.error(f"❌ Error checking gateway health: {e}")
            logger.warning("⏩ Continuing with cycle despite gateway check failure")
        
        # Step 1: Run price monitor
        logger.info("Step 1: Running price monitor...")
        monitor_success = run_price_monitor(runtime=120, port=port)
        
        # Step 2: Run order placement if monitoring was successful
        if monitor_success:
            logger.info("Step 2: Running order placement...")
            order_success = run_order_placement(port=port, allow_market_closed=allow_market_closed)
            if not order_success:
                logger.warning("Order placement failed or was incomplete")
        else:
            logger.error("Price monitoring failed, skipping order placement")
        
        # Calculate how long to wait until next cycle
        cycle_duration = time.time() - cycle_start
        wait_time = max(0, interval - cycle_duration)
        
        # Wait for interval before starting the next cycle
        if cycle_count < cycles and wait_time > 0:
            logger.info(f"Cycle {cycle_count} complete. Waiting {wait_time:.1f} seconds until next cycle...")
            time.sleep(wait_time)
    
    logger.info(f"Trading system completed after {cycle_count} cycles")
    return cycle_count

def main():
    """Standalone execution entry point"""
    parser = argparse.ArgumentParser(description='Trading Monitor')
    parser.add_argument('--cycles', type=int, default=1, help='Number of trading cycles to run')
    parser.add_argument('--port', type=int, default=4002, help='IBKR port (4002 for paper, 4001 for live)')
    parser.add_argument('--allow-market-closed', action='store_true', help='Allow orders when markets are closed')
    parser.add_argument('--interval', type=int, default=60, help='Seconds to wait between cycle starts')
    parser.add_argument('--test-mode', action='store_true', help='Run in test mode')
    
    args = parser.parse_args()
    
    logger.info("=== Trading System Configuration ===")
    logger.info(f"Number of cycles: {args.cycles}")
    logger.info(f"IBKR port: {args.port} ({'Paper Trading' if args.port == 4002 else 'Live Trading'})")
    logger.info(f"Allow market closed orders: {args.allow_market_closed}")
    logger.info(f"Interval between cycles: {args.interval} seconds")
    logger.info("=================================")
    
    if args.test_mode:
        logger.info("Running in test mode...")
        args.cycles = 1
    
    cycles_completed = run_trading_monitor(
        cycles=args.cycles,
        port=args.port,
        allow_market_closed=args.allow_market_closed,
        interval=args.interval
    )
    
    logger.info(f"Trading monitor completed: {cycles_completed} cycles")
    return cycles_completed

if __name__ == "__main__":
    main()