#!/usr/bin/env python
# IBKR Market Order Script for Option Spreads with Take Profit

import sqlite3
import pandas as pd
import datetime
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract, ComboLeg
from ibapi.order import Order
from ibapi.utils import iswrapper
import time
import threading
import logging
import os
import random
import argparse

# Set up logging directory
log_dir = os.path.join(os.path.dirname(__file__), 'output', 'logs')
os.makedirs(log_dir, exist_ok=True)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, "vertical_spread_order.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

class IBWrapper(EWrapper):
    def __init__(self):
        super().__init__()
        self.next_order_id = None
        self.contract_details = {}
        self.mid_prices = {}
        self.combo_ids = {}  # New - to store combo contract IDs

    @iswrapper
    def nextValidId(self, orderId: int):
        self.next_order_id = orderId
        logger.info(f"Next Valid Order ID: {orderId}")
    
    @iswrapper
    def tickPrice(self, reqId, tickType, price, attrib):
        # We're only interested in bid (1) and ask (2) prices
        if tickType == 1:  # Bid
            if reqId not in self.mid_prices:
                self.mid_prices[reqId] = {"bid": None, "ask": None}
            self.mid_prices[reqId]["bid"] = price
            logger.info(f"Received bid price for req_id {reqId}: {price}")
        elif tickType == 2:  # Ask
            if reqId not in self.mid_prices:
                self.mid_prices[reqId] = {"bid": None, "ask": None}
            self.mid_prices[reqId]["ask"] = price
            logger.info(f"Received ask price for req_id {reqId}: {price}")
    
    @iswrapper
    def tickOptionComputation(self, reqId, tickType, tickAttrib, impliedVol, delta, optPrice, pvDividend, gamma, vega, theta, undPrice):
        # If we don't have market data, try to use the option computation data
        # tickType 12 = last price, tickType 13 = model price
        if optPrice is not None and (tickType == 12 or tickType == 13):
            if reqId not in self.mid_prices:
                self.mid_prices[reqId] = {"bid": None, "ask": None, "last": None, "model": None}
            
            if tickType == 12:  # Last price
                self.mid_prices[reqId]["last"] = optPrice
                logger.info(f"Received last price for req_id {reqId}: {optPrice}")
            elif tickType == 13:  # Model price
                self.mid_prices[reqId]["model"] = optPrice
                logger.info(f"Received model price for req_id {reqId}: {optPrice}")

    @iswrapper
    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson="", connectionClosed=False):
        logger.error(f"Error {reqId}: {errorCode} - {errorString}")
        
        # Check if connection is closed
        if connectionClosed:
            logger.warning("Connection to IBKR was closed")

    # Add method to receive contract details for combo legs
    @iswrapper
    def contractDetails(self, reqId, contractDetails):
        if reqId in self.combo_ids:
            conId = contractDetails.contract.conId
            symbol = contractDetails.contract.symbol
            strike = contractDetails.contract.strike
            right = contractDetails.contract.right
            expiry = contractDetails.contract.lastTradeDateOrContractMonth
            
            logger.info(f"Received contract details: {symbol} {expiry} {strike} {right}, conId: {conId}")
            self.combo_ids[reqId] = {
                "conId": conId,
                "symbol": symbol,
                "strike": strike,
                "right": right,
                "expiry": expiry
            }

    @iswrapper
    def contractDetailsEnd(self, reqId):
        logger.info(f"Contract details request {reqId} completed")

    @iswrapper
    def openOrder(self, orderId, contract, order, orderState):
        logger.info(f"Order {orderId} status: {orderState.status}")
        logger.info(f"Order details: {order.action} {order.totalQuantity} @ {order.lmtPrice if order.orderType == 'LMT' else 'MKT'}")

    @iswrapper
    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        logger.info(f"Order {orderId} status update: {status}, filled: {filled}, remaining: {remaining}, avgFillPrice: {avgFillPrice}")
        
        # We could store order IDs and their corresponding strategy IDs to update
        # the database when orders are filled. For simplicity, we're using the initial update only,
        # but you could implement a more sophisticated tracking system here.

class IBClient(EClient):
    def __init__(self, wrapper):
        super().__init__(wrapper)

class IBApp(IBWrapper, IBClient):
    def __init__(self):
        IBWrapper.__init__(self)
        IBClient.__init__(self, wrapper=self)
        self.connected = False
        self.order_placed = False
        self.request_ids = {}

    def create_option_contract(self, symbol, expiry, strike, right):
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "OPT"
        contract.exchange = "SMART"
        contract.currency = "USD"
        
        # Format the expiry date properly for IBKR (remove hyphens)
        # Convert from "2025-03-28" to "20250328" format
        expiry_formatted = expiry.replace("-", "")
        
        contract.lastTradeDateOrContractMonth = expiry_formatted
        contract.strike = strike
        contract.right = right
        contract.multiplier = "100"
        
        logger.info(f"Created option contract: {symbol} {expiry_formatted} {strike} {right}")
        return contract
    
    def create_combo_contract(self, symbol, leg_contracts, contract_ids=None):
        """Create a BAG contract for a vertical spread"""
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "BAG"
        contract.exchange = "SMART"
        contract.currency = "USD"
        
        combo_legs = []
        
        # If contract_ids provided, use them directly
        if contract_ids:
            buy_contract, sell_contract = leg_contracts
            buy_conId, sell_conId = contract_ids
            
            # For a vertical spread, one leg is BUY and one is SELL
            # First leg - Buy
            leg1 = ComboLeg()
            leg1.conId = buy_conId
            leg1.ratio = 1
            leg1.action = "BUY"
            leg1.exchange = "SMART"
            combo_legs.append(leg1)
            
            # Second leg - Sell
            leg2 = ComboLeg()
            leg2.conId = sell_conId
            leg2.ratio = 1
            leg2.action = "SELL"
            leg2.exchange = "SMART"
            combo_legs.append(leg2)
            
        contract.comboLegs = combo_legs
        
        logger.info(f"Created combo contract for {symbol} with {len(combo_legs)} legs")
        return contract
    
    def create_limit_order(self, action, quantity, price, parent_id=None, transmit=True):
        """Create a limit order"""
        order = Order()
        order.action = action
        order.orderType = "LMT"
        order.totalQuantity = quantity
        order.lmtPrice = price
        
        if parent_id is not None:
            order.parentId = parent_id
            
        order.transmit = transmit
        
        return order
    
    def create_market_order(self, action, quantity, parent_id=None, transmit=True):
        """Create a market order"""
        order = Order()
        order.action = action
        order.orderType = "MKT"
        order.totalQuantity = quantity
        
        if parent_id is not None:
            order.parentId = parent_id
            
        order.transmit = transmit
        
        return order

    def get_contract_details(self, contract, req_id):
        """Request contract details to get conId"""
        self.combo_ids[req_id] = None
        self.reqContractDetails(req_id, contract)
        
        # Wait for contract details to be received
        wait_time = 3
        start_time = time.time()
        while self.combo_ids[req_id] is None and time.time() - start_time < wait_time:
            time.sleep(0.1)
            
        return self.combo_ids.get(req_id)

    def get_price_data(self, contract, req_id):
        """Request market data with increased timeout and better logging."""
        logger.info(f"Requesting market data for {contract.symbol} {contract.strike} {contract.right} (req_id: {req_id})")
        self.reqMktData(req_id, contract, "", False, False, [])
        
        # Allow more time for market data to arrive
        wait_time = 5  # Increased from 2 to 5 seconds
        time.sleep(wait_time)
        
        # Log the received data (or lack thereof)
        if req_id in self.mid_prices:
            bid = self.mid_prices[req_id].get("bid")
            ask = self.mid_prices[req_id].get("ask")
            if bid is not None and ask is not None:
                logger.info(f"Received market data for req_id {req_id}: Bid={bid}, Ask={ask}")
            else:
                logger.warning(f"Incomplete market data for req_id {req_id}: Bid={bid}, Ask={ask}")
        else:
            logger.warning(f"No market data received for req_id {req_id}")

def get_strategies_for_date(db_path, date_str=None):
    """Get option strategies from database for a specific date."""
    conn = sqlite3.connect(db_path)
    
    # If no date provided, use today's date
    if date_str is None:
        date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    
    # Convert date_str to datetime for filtering
    target_date = pd.to_datetime(date_str)
    
    # Format for ISO timestamp comparison (handles timestamps like '2025-03-10T08:41:01.483574')
    start_date = target_date.strftime('%Y-%m-%d')
    
    # Query to get rows where scrape_date matches the target day
    # Using date() SQLite function to extract just the date part from the timestamp
    query = f"""
    SELECT * FROM option_strategies 
    WHERE date(scrape_date) = '{start_date}'
    AND timestamp_of_trigger IS NOT NULL
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    return df

def update_strategy_status(db_path, row_id, status, premium):
    """
    Update the strategy status, premium when last checked, and timestamp in the database.
    
    Args:
        db_path: Path to the database
        row_id: Database row ID
        status: Strategy status text
        premium: Premium amount (already in per-contract basis)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get current timestamp
    current_timestamp = int(time.time())
    
    # Update the database with status, premium, and timestamp
    update_query = """
        UPDATE option_strategies 
        SET strategy_status = ?, 
            premium_when_last_checked = ?,
            timestamp_of_order = ?
        WHERE id = ?
    """
    
    try:
        cursor.execute(update_query, (status, premium, current_timestamp, row_id))
        logger.info(f"Updated row {row_id} with status: {status}, premium: {premium}, timestamp: {current_timestamp}")
    except sqlite3.Error as e:
        logger.error(f"Database error updating strategy: {e}")
    
    conn.commit()
    conn.close()

def run_trading_app(db_path='database/option_strategies.db', target_date=None, ibkr_host='127.0.0.1', ibkr_port=7497, client_id=None):
    """
    Main function to process and place orders.
    
    Args:
        db_path (str): Path to the SQLite database
        target_date (str, optional): Date string in 'YYYY-MM-DD' format.
            If None, today's date will be used.
        ibkr_host (str): IBKR TWS/Gateway host address
        ibkr_port (int): IBKR TWS/Gateway port number
        client_id (int): Client ID for IBKR connection (random if None)
    """
    # Use the provided date or default to today's date
    if target_date is None:
        target_date = datetime.datetime.now().strftime('%Y-%m-%d')
    
    # Use random client ID if not provided
    if client_id is None:
        client_id = random.randint(100, 9999)
    
    logger.info(f"Processing strategies for date: {target_date}")
    
    # Get strategies for the target date
    df = get_strategies_for_date(db_path, target_date)
    
    if df.empty:
        logger.info(f"No strategies found for {target_date}")
        return
    
    logger.info(f"Found {len(df)} strategies to process")
    
    # Initialize IBKR app
    app = IBApp()
    
    # Connect to IBKR
    app.connect(ibkr_host, ibkr_port, client_id)
    
    # Start a thread to process IBKR messages
    ibkr_thread = threading.Thread(target=app.run)
    ibkr_thread.start()
    
    # Wait for connection and valid order ID
    timeout = 10
    start_time = time.time()
    while not app.next_order_id and time.time() - start_time < timeout:
        time.sleep(0.1)
    
    if not app.next_order_id:
        logger.error("Failed to connect to IBKR or get valid order ID")
        app.disconnect()
        return
    
    # Process each strategy
    for idx, row in df.iterrows():
        ticker = row['ticker']
        expiry = row['options_expiry_date']
        strategy_type = row['strategy_type']
        strike_buy = row['strike_buy']
        strike_sell = row['strike_sell']
        estimated_premium = row['estimated_premium']
        
        logger.info(f"Processing {strategy_type} for {ticker}, expiry {expiry}")
        
        # Determine contract details based on strategy type
        if strategy_type == 'Bear Call':
            # For Bear Call: Sell lower strike call, buy higher strike call
            sell_contract = app.create_option_contract(ticker, expiry, strike_sell, "C")
            buy_contract = app.create_option_contract(ticker, expiry, strike_buy, "C")
            # For Bear Call spreads (credit spread), we SELL the spread
            combo_action = "SELL"
            take_profit_action = "BUY"  # To close a short position
        elif strategy_type == 'Bull Put':
            # For Bull Put: Sell higher strike put, buy lower strike put
            sell_contract = app.create_option_contract(ticker, expiry, strike_sell, "P")
            buy_contract = app.create_option_contract(ticker, expiry, strike_buy, "P")
            # For Bull Put spreads (credit spread), we SELL the spread
            combo_action = "SELL"
            take_profit_action = "BUY"  # To close a short position
        else:
            logger.error(f"Unknown strategy type: {strategy_type}")
            continue
        
        # Get contract details to get conId for combo legs
        req_id_sell = app.next_order_id
        app.next_order_id += 1
        sell_details = app.get_contract_details(sell_contract, req_id_sell)
        
        req_id_buy = app.next_order_id
        app.next_order_id += 1
        buy_details = app.get_contract_details(buy_contract, req_id_buy)
        
        if not sell_details or not buy_details:
            logger.error(f"Could not get contract details for one or both legs")
            update_strategy_status(db_path, row['id'], 'missing contract details', 0)
            continue
        
        # Get market data for both legs
        req_id_sell_price = app.next_order_id
        app.next_order_id += 1
        app.get_price_data(sell_contract, req_id_sell_price)
        
        req_id_buy_price = app.next_order_id
        app.next_order_id += 1
        app.get_price_data(buy_contract, req_id_buy_price)
        
        # Calculate mid prices for both legs
        try:
            # Check if we have the necessary market data
            if req_id_sell_price not in app.mid_prices:
                logger.error(f"No market data received for sell leg (req_id: {req_id_sell_price})")
                update_strategy_status(db_path, row['id'], 'missing market data', 0)
                continue
                
            if req_id_buy_price not in app.mid_prices:
                logger.error(f"No market data received for buy leg (req_id: {req_id_buy_price})")
                update_strategy_status(db_path, row['id'], 'missing market data', 0)
                continue
                
            # Try to get prices in this order: bid/ask first, then model, then last
            sell_price = None
            buy_price = None
            
            # For sell leg
            sell_bid = app.mid_prices[req_id_sell_price].get('bid')
            sell_ask = app.mid_prices[req_id_sell_price].get('ask')
            sell_model = app.mid_prices[req_id_sell_price].get('model')
            sell_last = app.mid_prices[req_id_sell_price].get('last')
            
            # For buy leg
            buy_bid = app.mid_prices[req_id_buy_price].get('bid')
            buy_ask = app.mid_prices[req_id_buy_price].get('ask')
            buy_model = app.mid_prices[req_id_buy_price].get('model')
            buy_last = app.mid_prices[req_id_buy_price].get('last')
            
            # Determine sell price (prefer bid/ask mid, then model, then last)
            if sell_bid is not None and sell_ask is not None:
                sell_price = (sell_bid + sell_ask) / 2
                logger.info(f"Using bid/ask mid for sell leg: {sell_price}")
            elif sell_model is not None:
                sell_price = sell_model
                logger.info(f"Using model price for sell leg: {sell_price}")
            elif sell_last is not None:
                sell_price = sell_last
                logger.info(f"Using last price for sell leg: {sell_price}")
            else:
                logger.error("No valid price data for sell leg")
                update_strategy_status(db_path, row['id'], 'no valid price data', 0)
                continue
                
            # Determine buy price (prefer bid/ask mid, then model, then last)
            if buy_bid is not None and buy_ask is not None:
                buy_price = (buy_bid + buy_ask) / 2
                logger.info(f"Using bid/ask mid for buy leg: {buy_price}")
            elif buy_model is not None:
                buy_price = buy_model
                logger.info(f"Using model price for buy leg: {buy_price}")
            elif buy_last is not None:
                buy_price = buy_last
                logger.info(f"Using last price for buy leg: {buy_price}")
            else:
                logger.error("No valid price data for buy leg")
                update_strategy_status(db_path, row['id'], 'no valid price data', 0)
                continue
            
            # Premium collected is the difference (sell price - buy price)
            premium_collected = sell_price - buy_price
            
            # Convert premium_collected to dollar value per contract (multiply by 100)
            premium_collected_dollar = premium_collected * 100
            
            logger.info(f"Prices - Sell: {sell_price}, Buy: {buy_price}")
            logger.info(f"Premium collected: {premium_collected} per share, ${premium_collected_dollar:.2f} per contract")
            logger.info(f"Estimated premium in database: ${estimated_premium:.2f} per contract")
            
            # Check if premium is sufficient - compare with estimated premium
            if premium_collected_dollar >= estimated_premium:
                # Create combo contract for vertical spread
                sell_conId = sell_details['conId']
                buy_conId = buy_details['conId']
                
                combo_contract = app.create_combo_contract(
                    ticker, 
                    [buy_contract, sell_contract],
                    [buy_conId, sell_conId]
                )
                
                # Calculate take profit price (50% of estimated premium)
                take_profit_price = premium_collected / 2  # Using half of the actual premium
                
                # For credit spreads, the limit price is the credit received (positive)
                entry_limit_price = premium_collected
                
                # Place combo order with parent-child structure
                parent_order_id = app.next_order_id
                app.next_order_id += 1
                
                # Parent order (entry)
                parent_order = app.create_limit_order(combo_action, 1, entry_limit_price, transmit=False)
                
                # Child order (take profit) - 50% of premium
                take_profit_order_id = app.next_order_id
                app.next_order_id += 1
                
                # For credit spreads (SELL), take profit is BUY at 50% of original price
                take_profit_order = app.create_limit_order(
                    take_profit_action, 
                    1, 
                    take_profit_price, 
                    parent_id=parent_order_id,
                    transmit=True  # This will transmit both orders
                )
                
                # Place the orders
                app.placeOrder(parent_order_id, combo_contract, parent_order)
                logger.info(f"Placed {combo_action} order {parent_order_id} for {ticker} spread")
                
                app.placeOrder(take_profit_order_id, combo_contract, take_profit_order)
                logger.info(f"Placed take profit order {take_profit_order_id} at {take_profit_price}")
                
                # Update database with status, actual premium, and timestamp
                update_strategy_status(db_path, row['id'], 'order placed with take profit', premium_collected_dollar)
            else:
                # Premium too low, update database with the per-contract dollar amount
                update_strategy_status(db_path, row['id'], 'premium too low', premium_collected_dollar)
        
        except Exception as e:
            logger.error(f"Error processing order: {str(e)}")
            # Log more details about the exception for debugging
            import traceback
            logger.error(f"Exception details: {traceback.format_exc()}")
            update_strategy_status(db_path, row['id'], 'error', 0)
    
    # Clean up
    time.sleep(3)  # Give time for orders to process
    app.disconnect()
    logger.info("Disconnected from IBKR")

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='IBKR Market Order Script for Option Spreads with Take Profit')
    
    parser.add_argument('--db', type=str, default='database/option_strategies.db',
                        help='Path to SQLite database')
    parser.add_argument('--host', type=str, default='127.0.0.1',
                        help='IBKR TWS/Gateway host')
    parser.add_argument('--port', type=int, default=7497,
                        help='IBKR TWS/Gateway port (7497 for paper, 7496 for live)')
    parser.add_argument('--date', type=str, default=None,
                        help='Target date for strategies (YYYY-MM-DD format, default: today)')
    parser.add_argument('--client', type=int, default=None,
                        help='Client ID for IBKR connection (random if not specified)')
    
    return parser.parse_args()

if __name__ == "__main__":
    # Parse command line arguments
    args = parse_arguments()
    
    # Run the trading app
    run_trading_app(
        db_path=args.db,
        target_date=args.date,
        ibkr_host=args.host,
        ibkr_port=args.port,
        client_id=args.client
    )