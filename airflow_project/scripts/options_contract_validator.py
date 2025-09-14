"""
Options Contract Validator Module
Validates options contracts and corrects expiry dates for Airflow workflow
"""
import sys
import os
import time
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Tuple, Optional
import threading

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

# IBKR API imports
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.utils import iswrapper

# Database imports
from database_utils import connect_to_database, close_database_connection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ContractValidationWrapper(EWrapper):
    """Wrapper for handling IBKR API responses during contract validation"""

    def __init__(self):
        super().__init__()
        self.contract_details = {}
        self.validation_results = {}
        self.errors = {}
        self.pending_requests = set()

    @iswrapper
    def contractDetails(self, reqId: int, contractDetails):
        """Handle successful contract details response"""
        self.contract_details[reqId] = {
            'conId': contractDetails.contract.conId,
            'symbol': contractDetails.contract.symbol,
            'strike': contractDetails.contract.strike,
            'right': contractDetails.contract.right,
            'expiry': contractDetails.contract.lastTradeDateOrContractMonth,
            'valid': True
        }
        logger.info(f"✅ Valid contract found for req_id {reqId}: {contractDetails.contract.symbol} "
                   f"{contractDetails.contract.lastTradeDateOrContractMonth} "
                   f"{contractDetails.contract.strike} {contractDetails.contract.right}")

    @iswrapper
    def contractDetailsEnd(self, reqId: int):
        """Handle end of contract details for a request"""
        if reqId not in self.contract_details:
            # No contract details received means contract doesn't exist
            self.validation_results[reqId] = {'valid': False, 'reason': 'No contract found'}
            logger.warning(f"❌ No contract found for req_id {reqId}")
        else:
            self.validation_results[reqId] = {'valid': True}

        # Remove from pending requests
        if reqId in self.pending_requests:
            self.pending_requests.remove(reqId)

    @iswrapper
    def error(self, reqId: int, errorCode: int, errorString: str, advancedOrderRejectJson=""):
        """Handle API errors"""
        # Filter out informational messages
        if errorCode in [2104, 2106, 2119, 2158]:
            return

        self.errors[reqId] = {
            'errorCode': errorCode,
            'errorString': errorString
        }

        # Mark as invalid if it's a real error about the contract
        if errorCode in [200, 354]:  # Contract not found errors
            self.validation_results[reqId] = {
                'valid': False,
                'reason': f'Error {errorCode}: {errorString}'
            }
            logger.warning(f"❌ Contract validation error for req_id {reqId}: {errorCode} - {errorString}")

            # Remove from pending requests
            if reqId in self.pending_requests:
                self.pending_requests.remove(reqId)
        else:
            logger.info(f"API message for req_id {reqId}: {errorCode} - {errorString}")

class ContractValidationClient(EClient):
    """Client for IBKR API contract validation"""

    def __init__(self, wrapper):
        super().__init__(wrapper)

class IBApp(ContractValidationWrapper, ContractValidationClient):
    """Combined IB API application class"""

    def __init__(self):
        ContractValidationWrapper.__init__(self)
        ContractValidationClient.__init__(self, self)

class OptionsContractValidator:
    """Main class for validating and correcting options contracts"""

    def __init__(self, port: int = 4002):
        self.port = port
        self.app = IBApp()
        self.next_req_id = 1000  # Start with high ID to avoid conflicts

    def connect_to_gateway(self) -> bool:
        """Connect to IB Gateway"""
        try:
            logger.info(f"Connecting to IB Gateway on port {self.port}...")
            self.app.connect("127.0.0.1", self.port, 999)  # Use client ID 999

            # Start API thread
            api_thread = threading.Thread(target=self.app.run, daemon=True)
            api_thread.start()

            # Wait for connection
            time.sleep(3)

            if self.app.isConnected():
                logger.info("✅ Connected to IB Gateway")
                return True
            else:
                logger.error("❌ Failed to connect to IB Gateway")
                return False

        except Exception as e:
            logger.error(f"❌ Error connecting to IB Gateway: {e}")
            return False

    def disconnect(self):
        """Disconnect from IB Gateway"""
        if self.app.isConnected():
            self.app.disconnect()
            logger.info("Disconnected from IB Gateway")

    def create_option_contract(self, ticker: str, expiry_date: str, strike: float, right: str) -> Contract:
        """Create an option contract for validation"""
        contract = Contract()
        contract.symbol = ticker
        contract.secType = "OPT"
        contract.exchange = "SMART"
        contract.currency = "USD"
        contract.lastTradeDateOrContractMonth = expiry_date.replace("-", "")
        contract.strike = strike
        contract.right = right
        contract.multiplier = "100"
        return contract

    def validate_contract(self, ticker: str, expiry_date: str, strike: float, right: str) -> bool:
        """Validate a single option contract"""
        req_id = self.next_req_id
        self.next_req_id += 1

        contract = self.create_option_contract(ticker, expiry_date, strike, right)
        self.app.pending_requests.add(req_id)

        logger.info(f"Validating contract: {ticker} {expiry_date} {strike} {right} (req_id: {req_id})")
        self.app.reqContractDetails(req_id, contract)

        # Wait for response with timeout
        timeout = 10  # 10 seconds timeout
        start_time = time.time()

        while req_id in self.app.pending_requests and (time.time() - start_time) < timeout:
            time.sleep(0.1)

        # Check result
        if req_id in self.app.validation_results:
            return self.app.validation_results[req_id]['valid']
        else:
            logger.warning(f"⏰ Timeout validating contract: {ticker} {expiry_date} {strike} {right}")
            return False

    def validate_spread_contracts(self, ticker: str, expiry_date: str, buy_strike: float, sell_strike: float) -> Tuple[bool, bool]:
        """Validate both legs of an options spread"""
        # Determine if it's calls or puts based on strike relationship
        if buy_strike < sell_strike:
            # Bull call spread or bear put spread - assume calls for now
            buy_valid = self.validate_contract(ticker, expiry_date, buy_strike, "C")
            sell_valid = self.validate_contract(ticker, expiry_date, sell_strike, "C")
        else:
            # Bear call spread or bull put spread - assume puts for now
            buy_valid = self.validate_contract(ticker, expiry_date, buy_strike, "P")
            sell_valid = self.validate_contract(ticker, expiry_date, sell_strike, "P")

        return buy_valid, sell_valid

    def try_date_correction(self, ticker: str, original_date: str, buy_strike: float, sell_strike: float) -> Optional[str]:
        """Try to find a valid expiry date by adjusting +1 or -1 day"""
        original_dt = datetime.strptime(original_date, "%Y-%m-%d").date()

        # Try +1 day
        plus_one = original_dt + timedelta(days=1)
        plus_one_str = plus_one.strftime("%Y-%m-%d")

        logger.info(f"🔍 Trying +1 day correction: {plus_one_str}")
        buy_valid, sell_valid = self.validate_spread_contracts(ticker, plus_one_str, buy_strike, sell_strike)

        if buy_valid and sell_valid:
            logger.info(f"✅ Found valid contracts with +1 day: {plus_one_str}")
            return plus_one_str

        # Try -1 day
        minus_one = original_dt - timedelta(days=1)
        minus_one_str = minus_one.strftime("%Y-%m-%d")

        logger.info(f"🔍 Trying -1 day correction: {minus_one_str}")
        buy_valid, sell_valid = self.validate_spread_contracts(ticker, minus_one_str, buy_strike, sell_strike)

        if buy_valid and sell_valid:
            logger.info(f"✅ Found valid contracts with -1 day: {minus_one_str}")
            return minus_one_str

        logger.warning(f"❌ No valid contracts found for {ticker} with date corrections")
        return None

    def get_todays_trade_ideas(self, cursor) -> List[Dict]:
        """Get all trade ideas scraped today"""
        today = date.today().strftime('%Y-%m-%d')

        query = """
        SELECT id, ticker, strike_buy, strike_sell, options_expiry_date, options_expiry_date_as_scrapped
        FROM option_strategies
        WHERE DATE(scrape_date) = %s
        AND options_expiry_date IS NOT NULL
        AND ticker IS NOT NULL
        AND strike_buy IS NOT NULL
        AND strike_sell IS NOT NULL
        """

        cursor.execute(query, (today,))
        results = cursor.fetchall()

        trade_ideas = []
        for row in results:
            trade_ideas.append({
                'id': row[0],
                'ticker': row[1],
                'strike_buy': float(row[2]),
                'strike_sell': float(row[3]),
                'options_expiry_date': row[4],
                'options_expiry_date_as_scrapped': row[5]
            })

        logger.info(f"Found {len(trade_ideas)} trade ideas to validate")
        return trade_ideas

    def update_corrected_date(self, cursor, trade_id: int, corrected_date: str, original_date: str):
        """Update database with corrected expiry date"""
        update_query = """
        UPDATE option_strategies
        SET options_expiry_date = %s,
            options_expiry_date_as_scrapped = %s
        WHERE id = %s
        """

        cursor.execute(update_query, (corrected_date, original_date, trade_id))
        logger.info(f"📝 Updated trade ID {trade_id}: {original_date} → {corrected_date}")

def run_contract_validation(port: int = 4002) -> Dict[str, int]:
    """Main function to run options contract validation"""
    logger.info("🔍 Starting options contract validation...")

    stats = {
        'total_records': 0,
        'valid_original': 0,
        'corrected_dates': 0,
        'failed_validation': 0
    }

    # Connect to database
    conn, cursor = connect_to_database()
    if not conn:
        raise Exception("Failed to connect to database")

    try:
        # Initialize validator
        validator = OptionsContractValidator(port)

        # Connect to IB Gateway
        if not validator.connect_to_gateway():
            raise Exception("Failed to connect to IB Gateway")

        try:
            # Get today's trade ideas
            trade_ideas = validator.get_todays_trade_ideas(cursor)
            stats['total_records'] = len(trade_ideas)

            if not trade_ideas:
                logger.info("✅ No trade ideas found for validation")
                return stats

            # Process each trade idea
            for idea in trade_ideas:
                logger.info(f"Processing trade ID {idea['id']}: {idea['ticker']} {idea['options_expiry_date']}")

                # First validate original date
                buy_valid, sell_valid = validator.validate_spread_contracts(
                    idea['ticker'], idea['options_expiry_date'],
                    idea['strike_buy'], idea['strike_sell']
                )

                if buy_valid and sell_valid:
                    logger.info(f"✅ Original date valid for trade ID {idea['id']}")
                    stats['valid_original'] += 1
                    continue

                # Try date correction
                corrected_date = validator.try_date_correction(
                    idea['ticker'], idea['options_expiry_date'],
                    idea['strike_buy'], idea['strike_sell']
                )

                if corrected_date:
                    # Update database with correction
                    validator.update_corrected_date(
                        cursor, idea['id'], corrected_date, idea['options_expiry_date']
                    )
                    stats['corrected_dates'] += 1
                else:
                    logger.warning(f"❌ Failed to find valid contracts for trade ID {idea['id']}")
                    stats['failed_validation'] += 1

                # Small delay between validations
                time.sleep(0.5)

        finally:
            validator.disconnect()

        # Commit all database changes
        conn.commit()

        # Log final statistics
        logger.info("📊 Contract Validation Summary:")
        logger.info(f"   Total records processed: {stats['total_records']}")
        logger.info(f"   Valid original dates: {stats['valid_original']}")
        logger.info(f"   Dates corrected: {stats['corrected_dates']}")
        logger.info(f"   Failed validations: {stats['failed_validation']}")

        return stats

    finally:
        close_database_connection(conn, cursor)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Validate options contracts and correct expiry dates')
    parser.add_argument('--port', type=int, default=4002, help='IB Gateway port (default: 4002)')

    args = parser.parse_args()

    try:
        stats = run_contract_validation(args.port)
        print(f"✅ Contract validation completed successfully: {stats}")
    except Exception as e:
        print(f"❌ Contract validation failed: {e}")
        sys.exit(1)