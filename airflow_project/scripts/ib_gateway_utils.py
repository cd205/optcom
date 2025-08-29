"""
IB Gateway Utilities Module
Utilities for managing Interactive Brokers Gateway processes
"""
import os
import subprocess
import logging
import time
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

class IBGatewayManager:
    """Manager class for IB Gateway operations"""
    
    def __init__(self, ibc_setup_path: str = None):
        if ibc_setup_path is None:
            # Try to find ibc-setup directory
            possible_paths = [
                '../ibc-setup',
                'ibc-setup',
                '/home/chris_s_dodd/optcom-1/ibc-setup'
            ]
            
            for path in possible_paths:
                if os.path.exists(path) and os.path.exists(os.path.join(path, 'start-dual-gateway.sh')):
                    ibc_setup_path = path
                    break
            
            if ibc_setup_path is None:
                raise FileNotFoundError("Could not find ibc-setup directory")
        
        self.ibc_setup_path = os.path.abspath(ibc_setup_path)
        self.script_path = os.path.join(self.ibc_setup_path, 'start-dual-gateway.sh')
        
        if not os.path.exists(self.script_path):
            raise FileNotFoundError(f"Gateway script not found: {self.script_path}")
    
    def start_gateways(self) -> bool:
        """
        Start both paper and live gateways with smart polling
        
        - Initiates startup (may require 2FA)
        - Polls every 30 seconds to check if gateways are ready
        - Exits immediately once both gateways are running
        - Times out after 15 minutes if gateways never become ready
        
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Starting IB Gateways...")
        logger.info("⏳ Note: Live gateway startup may require 2FA approval on your phone")
        logger.info("⏰ Will check every 30 seconds, allowing up to 15 minutes for authentication...")
        
        # Step 1: Start the gateway startup process (non-blocking)
        try:
            cmd = ['bash', self.script_path, 'start']
            startup_process = subprocess.Popen(
                cmd, 
                cwd=self.ibc_setup_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            logger.info("🚀 Gateway startup initiated...")
            
        except Exception as e:
            logger.error(f"❌ Failed to initiate gateway startup: {e}")
            return False
        
        # Step 2: Smart polling with early exit
        import time
        max_wait_seconds = 900  # 15 minutes
        check_interval = 30     # Check every 30 seconds
        elapsed_time = 0
        
        logger.info("🔍 Starting gateway status polling...")
        
        while elapsed_time < max_wait_seconds:
            # Check if both gateways are ready
            success, status_output = self.check_status()
            
            if success and "Running" in status_output and "4001" in status_output and "4002" in status_output:
                logger.info(f"✅ Both gateways confirmed running after {elapsed_time} seconds!")
                logger.info("🎯 Early exit - no need to wait full 15 minutes")
                
                # Clean up the startup process
                if startup_process.poll() is None:
                    startup_process.terminate()
                
                return True
            
            # Log progress
            if elapsed_time == 0:
                logger.info("⏳ Gateways starting... (this may take a few minutes for 2FA)")
            elif elapsed_time % 120 == 0:  # Every 2 minutes
                logger.info(f"⏳ Still waiting for gateways... ({elapsed_time // 60} minutes elapsed)")
            
            time.sleep(check_interval)
            elapsed_time += check_interval
        
        # Step 3: Timeout handling
        logger.error(f"❌ Gateway startup timed out after {max_wait_seconds // 60} minutes")
        logger.error("💡 Possible causes: 2FA not approved, network issues, or gateway already running")
        
        # Clean up
        if startup_process.poll() is None:
            startup_process.terminate()
        
        # Final check in case they just started
        success, status_output = self.check_status()
        if success and "Running" in status_output:
            logger.info("🎯 Gateways appear to be running now - considering this a success")
            return True
        
        return False
    
    def stop_gateways(self) -> bool:
        """
        Stop all gateway instances
        
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Stopping IB Gateways...")
        
        try:
            cmd = ['bash', self.script_path, 'stop']
            result = subprocess.run(
                cmd,
                cwd=self.ibc_setup_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                logger.info("✅ IB Gateways stopped successfully")
                return True
            else:
                logger.error(f"❌ Failed to stop IB Gateways: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error stopping gateways: {e}")
            return False
    
    def check_status(self) -> Tuple[bool, str]:
        """
        Check the status of both gateways
        
        Returns:
            tuple: (success, status_output)
        """
        logger.info("Checking IB Gateway status...")
        
        try:
            cmd = ['bash', self.script_path, 'status']
            result = subprocess.run(
                cmd,
                cwd=self.ibc_setup_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Status command should always return 0, the output tells us the actual status
            status_output = result.stdout
            logger.info("Gateway status check completed")
            logger.info(status_output)
            
            # Check if both gateways are running by looking for key indicators
            paper_running = "Paper Gateway: Running" in status_output
            live_running = "Live Gateway: Running" in status_output
            
            both_running = paper_running and live_running
            
            return both_running, status_output
            
        except Exception as e:
            logger.error(f"❌ Error checking gateway status: {e}")
            return False, f"Error: {e}"
    
    def restart_gateway(self, gateway_type: Optional[str] = None) -> bool:
        """
        Restart gateway(s)
        
        Args:
            gateway_type: 'paper', 'live', or None (both)
            
        Returns:
            bool: True if successful, False otherwise
        """
        if gateway_type:
            logger.info(f"Restarting {gateway_type} gateway...")
            cmd = ['bash', self.script_path, 'restart', gateway_type]
        else:
            logger.info("Restarting both gateways...")
            cmd = ['bash', self.script_path, 'restart']
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.ibc_setup_path,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                logger.info("✅ Gateway restart completed successfully")
                return True
            else:
                logger.error(f"❌ Failed to restart gateway: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error restarting gateway: {e}")
            return False

def start_ib_gateways(**context) -> bool:
    """
    Airflow-compatible function to start IB Gateways
    
    Args:
        **context: Airflow context (ignored)
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        manager = IBGatewayManager()
        return manager.start_gateways()
    except Exception as e:
        logger.error(f"Failed to start IB Gateways: {e}")
        return False

def check_ib_gateway_status(**context) -> Tuple[bool, str]:
    """
    Airflow-compatible function to check IB Gateway status with automatic restart
    
    This function ensures both gateways are running before proceeding.
    If gateways are not running, it attempts to restart them automatically.
    
    Args:
        **context: Airflow context (ignored)
        
    Returns:
        tuple: (success, status_output)
    """
    try:
        manager = IBGatewayManager()
        
        # Enhanced status check with retry and restart logic
        max_attempts = 3
        retry_delay = 60  # seconds
        
        for attempt in range(max_attempts):
            logger.info(f"Gateway status check attempt {attempt + 1}/{max_attempts}")
            
            # Check current status
            success, status = manager.check_status()
            
            if success:
                # Both gateways running, now verify API ports are listening
                if _verify_api_ports_listening(status):
                    logger.info("✅ Both gateways running with API ports listening")
                    return True, status
                else:
                    logger.warning("⚠️ Gateways running but API ports not ready yet")
                    # Continue to retry logic below
            else:
                logger.warning(f"❌ Gateway status check failed: {status}")
            
            # If we're here, gateways need restart or API ports aren't ready
            if attempt < max_attempts - 1:  # Don't restart on last attempt
                logger.info(f"🔄 Attempting to restart gateways (attempt {attempt + 1})")
                
                # Try to restart the gateways
                restart_success = manager.restart_gateway()
                
                if restart_success:
                    logger.info("✅ Gateway restart initiated, waiting for startup...")
                    # Give gateways time to start up and authenticate
                    time.sleep(90)  # Longer wait for restart and 2FA
                else:
                    logger.error("❌ Failed to restart gateways")
                    if attempt < max_attempts - 1:
                        logger.info(f"⏳ Waiting {retry_delay} seconds before next attempt...")
                        time.sleep(retry_delay)
            else:
                logger.error("❌ Final attempt failed")
        
        # Final check after all attempts
        final_success, final_status = manager.check_status()
        if final_success and _verify_api_ports_listening(final_status):
            logger.info("✅ Gateways finally ready after retries")
            return True, final_status
        else:
            raise Exception(f"Gateway startup failed after {max_attempts} attempts. Final status: {final_status}")
        
    except Exception as e:
        logger.error(f"Gateway status check with restart failed: {e}")
        raise


def _verify_api_ports_listening(status_output: str) -> bool:
    """
    Verify that required API ports are listening based on configuration
    
    Args:
        status_output: Output from gateway status check
        
    Returns:
        bool: True if required API ports are listening
    """
    from airflow.models import Variable
    
    paper_port_ok = "API Port 4002: Listening" in status_output
    live_port_ok = "API Port 4001: Listening" in status_output
    
    # Check if we're in paper-only mode (trading port 4002)
    trading_port = Variable.get('trading_port', default_var='4002')
    paper_only_mode = trading_port == '4002'
    
    if paper_only_mode:
        # In paper-only mode, only require paper gateway
        if paper_port_ok:
            logger.info("✅ Paper gateway API ready (paper-only mode)")
            return True
        else:
            logger.warning("⚠️ Paper gateway API not listening")
            return False
    else:
        # Full mode - require both gateways
        if paper_port_ok and live_port_ok:
            logger.info("✅ Both gateway APIs ready (full mode)")
            return True
        elif paper_port_ok and not live_port_ok:
            logger.warning("⚠️ Paper gateway API ready, but live gateway API not listening (may need 2FA)")
            return False
        elif not paper_port_ok and live_port_ok:
            logger.warning("⚠️ Live gateway API ready, but paper gateway API not listening")
            return False
        else:
            logger.warning("⚠️ Neither gateway API is listening")
            return False

def stop_ib_gateways(**context) -> bool:
    """
    Airflow-compatible function to stop IB Gateways
    
    Args:
        **context: Airflow context (ignored)
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        manager = IBGatewayManager()
        return manager.stop_gateways()
    except Exception as e:
        logger.error(f"Failed to stop IB Gateways: {e}")
        return False

def main():
    """Standalone execution for testing"""
    import argparse
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    parser = argparse.ArgumentParser(description='IB Gateway Manager')
    parser.add_argument('action', choices=['start', 'stop', 'status', 'restart'],
                       help='Action to perform')
    parser.add_argument('--gateway-type', choices=['paper', 'live'],
                       help='Specific gateway type (for restart)')
    
    args = parser.parse_args()
    
    try:
        manager = IBGatewayManager()
        
        if args.action == 'start':
            success = manager.start_gateways()
        elif args.action == 'stop':
            success = manager.stop_gateways()
        elif args.action == 'status':
            success, status = manager.check_status()
            print(status)
        elif args.action == 'restart':
            success = manager.restart_gateway(args.gateway_type)
        
        if not success:
            exit(1)
            
    except Exception as e:
        logger.error(f"Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()