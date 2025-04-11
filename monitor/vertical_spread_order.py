#!/usr/bin/env python
# IBKR Market Order Script for Option Spreads - No Take Profit

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
logger = logging.getLogger(__name__)

class IBWrapper(EWrapper):
    def __init__(self):
        super().__init__()
        self.next_order_id = None
        self.contract_details = {}
        self.mid_prices = {}
        self.combo_ids = {}
        self.market_status = "unknown"  # To track market status

    @iswrapper
    def nextValidId(self, orderId: int):
        self.next_order_id = orderId
        logger.info(f"Next Valid Order ID: {orderId}")
    
    @iswrapper
    def tickPrice(self, reqId, tickType, price, attrib):
        if tickType in (1, 2):  # Bid or Ask
            if reqId not in self.mid_prices:
                self.mid_prices[reqId] = {"bid": None, "ask": None, "last": None, "model": None}
            self.mid_prices[reqId]["bid" if tickType == 1 else "ask"] = price
            logger.info(f"Received {'bid' if tickType == 1 else 'ask'} price for req_id {reqId}: {price}")
    
    @iswrapper
    def tickOptionComputation(self, reqId, tickType, tickAttrib, impliedVol, delta, optPrice, pvDividend, gamma, vega, theta, undPrice):
        if optPrice is not None and tickType in (12, 13):  # 12 = last price, 13 = model price
            if reqId not in self.mid_prices:
                self.mid_prices[reqId] = {"bid": None, "ask": None, "last": None, "model": None}
            self.mid_prices[reqId]["last" if tickType == 12 else "model"] = optPrice
            logger.info(f"Received {'last' if tickType == 12 else 'model'} price for req_id {reqId}: {optPrice}")

    @iswrapper
    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson="", connectionClosed=False):
        logger.error(f"Error {reqId}: {errorCode} - {errorString}")
        # Check for market closed error codes
        if errorCode in [2104, 2119]:  # Known IBKR error codes for market closed
            self.market_status = "closed"
            logger.warning(f"Market appears to be closed: {errorString}")
        
    @iswrapper
    def contractDetails(self, reqId, contractDetails):
        if reqId in self.combo_ids:
            self.combo_ids[reqId] = {
                "conId": contractDetails.contract.conId,
                "symbol": contractDetails.contract.symbol,
                "strike": contractDetails.contract.strike,
                "right": contractDetails.contract.right,
                "expiry": contractDetails.contract.lastTradeDateOrContractMonth
            }
            logger.info(f"Received contract details: {self.combo_ids[reqId]['symbol']} {self.combo_ids[reqId]['expiry']} {self.combo_ids[reqId]['strike']} {self.combo_ids[reqId]['right']}, conId: {self.combo_ids[reqId]['conId']}")

    @iswrapper
    def contractDetailsEnd(self, reqId):
        logger.info(f"Contract details request {reqId} completed")

    @iswrapper
    def openOrder(self, orderId, contract, order, orderState):
        logger.info(f"Order {orderId} status: {orderState.status}")

    @iswrapper
    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        logger.info(f"Order {orderId} status update: {status}, filled: {filled}, remaining: {remaining}")

class IBClient(EClient):
    def __init__(self, wrapper):
        super().__init__(wrapper)

class IBApp(IBWrapper, IBClient):
    def __init__(self):
        IBWrapper.__init__(self)
        IBClient.__init__(self, wrapper=self)

    def create_option_contract(self, symbol, expiry, strike, right):
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "OPT"
        contract.exchange = "SMART"
        contract.currency = "USD"
        contract.lastTradeDateOrContractMonth = expiry.replace("-", "")
        contract.strike = strike
        contract.right = right
        contract.multiplier = "100"
        
        logger.info(f"Created option contract: {symbol} {contract.lastTradeDateOrContractMonth} {strike} {right}")
        return contract
    
    def create_combo_contract(self, symbol, leg_contracts, contract_ids):
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "BAG"
        contract.exchange = "SMART"
        contract.currency = "USD"
        
        buy_contract, sell_contract = leg_contracts
        buy_conId, sell_conId = contract_ids
        
        # Create legs
        leg1 = ComboLeg()
        leg1.conId = buy_conId
        leg1.ratio = 1
        leg1.action = "BUY"
        leg1.exchange = "SMART"
        
        leg2 = ComboLeg()
        leg2.conId = sell_conId
        leg2.ratio = 1
        leg2.action = "SELL"
        leg2.exchange = "SMART"
        
        contract.comboLegs = [leg1, leg2]
        logger.info(f"Created combo contract for {symbol} with 2 legs")
        return contract
    
    def create_limit_order(self, action, quantity, price):
        """
        Create a limit order with time in force of 1 DAY
        
        Parameters:
        action (str): "BUY" or "SELL"
        quantity (int): Number of contracts
        price (float): Desired price
        
        Returns:
        Order: IBKR order object
        """
        # Ensure price is negative for vertical spreads
        # Negative price means we're collecting a credit
        if price > 0:
            price = -abs(price)
        
        # Round price to nearest $0.05 increment for most options
        price_increment = 0.05
        rounded_price = round(price / price_increment) * price_increment
        
        # Ensure at least 2 decimal places
        rounded_price = round(rounded_price, 2)
        
        order = Order()
        order.action = action
        order.orderType = "LMT"
        order.totalQuantity = quantity  # Always set to 1
        order.lmtPrice = rounded_price
        order.tif = "DAY"  # Set time in force to 1 DAY
        order.transmit = True
        
        logger.info(f"Created {action} limit order: Quantity={quantity}, Price=${rounded_price:.2f}, TIF=DAY")
        return order
    
    def get_contract_details(self, contract, req_id):
        self.combo_ids[req_id] = None
        self.reqContractDetails(req_id, contract)
        
        wait_time = 3
        start_time = time.time()
        while self.combo_ids[req_id] is None and time.time() - start_time < wait_time:
            time.sleep(0.1)
        return self.combo_ids.get(req_id)

    def get_price_data(self, contract, req_id):
        """
        Request and retrieve market data for a contract.
        
        Parameters:
        contract (Contract): Option contract
        req_id (int): Request ID to track this specific request
        
        Returns:
        dict: Pricing data including bid, ask, last, and model prices
        """
        logger.info(f"Requesting market data for {contract.symbol} {contract.strike} {contract.right} (req_id: {req_id})")
        
        # Clear any previous data for this req_id
        if req_id in self.mid_prices:
            del self.mid_prices[req_id]
            
        # Initialize with empty data
        self.mid_prices[req_id] = {"bid": None, "ask": None, "last": None, "model": None}
        
        # Request market data
        self.reqMktData(req_id, contract, "", False, False, [])
        
        # Wait for data to arrive
        wait_time = 5  # Wait up to 5 seconds for market data
        start_time = time.time()
        while time.time() - start_time < wait_time:
            # Check if we have received both bid and ask
            if (self.mid_prices[req_id]["bid"] is not None and 
                self.mid_prices[req_id]["ask"] is not None):
                # We have our data, no need to wait further
                break
            time.sleep(0.2)
        
        # Cancel the market data subscription
        self.cancelMktData(req_id)
        
        # Return the price data
        data = self.mid_prices.get(req_id, {"bid": None, "ask": None, "last": None, "model": None})
        
        if data["bid"] is not None and data["ask"] is not None:
            logger.info(f"Received market data for req_id {req_id}: Bid={data['bid']}, Ask={data['ask']}")
        else:
            logger.warning(f"Incomplete market data for req_id {req_id}: Bid={data['bid']}, Ask={data['ask']}")
            
        return data

def get_strategies_for_date(db_path, date_str=None):
    conn = sqlite3.connect(db_path)
    
    if date_str is None:
        date_str = datetime.datetime.now().strftime('%Y-%m-%d')
        
    target_date = pd.to_datetime(date_str)
    start_date = target_date.strftime('%Y-%m-%d')
    
    logger.info(f"Getting strategies for date: {start_date}")

    query = f"""
    SELECT * FROM option_strategies 
    WHERE date(scrape_date) = '{start_date}'
    AND timestamp_of_trigger IS NOT NULL
    AND (strategy_status IS NULL OR strategy_status != 'order placed')
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_last_prices_from_db(db_path, ticker, strike_sell, strike_buy, right):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Query sell leg price
    sell_price = None
    cursor.execute("""
        SELECT last_price_when_checked FROM option_strategies 
        WHERE ticker = ? AND strike_sell = ? AND last_price_when_checked IS NOT NULL
        ORDER BY timestamp_of_price_when_last_checked DESC LIMIT 1
    """, (ticker, strike_sell))
    result = cursor.fetchone()
    if result: sell_price = result[0]
    
    # Query buy leg price
    buy_price = None
    cursor.execute("""
        SELECT last_price_when_checked FROM option_strategies 
        WHERE ticker = ? AND strike_buy = ? AND last_price_when_checked IS NOT NULL
        ORDER BY timestamp_of_price_when_last_checked DESC LIMIT 1
    """, (ticker, strike_buy))
    result = cursor.fetchone()
    if result: buy_price = result[0]
    
    conn.close()
    
    if sell_price: logger.info(f"Found historical sell price for {ticker} {strike_sell} {right}: {sell_price}")
    if buy_price: logger.info(f"Found historical buy price for {ticker} {strike_buy} {right}: {buy_price}")
    
    return sell_price, buy_price

def update_strategy_status(db_path, row_id, status, premium):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    current_timestamp = int(time.time())
    
    try:
        cursor.execute("""
            UPDATE option_strategies 
            SET strategy_status = ?, premium_when_last_checked = ?, timestamp_of_order = ?
            WHERE id = ?
        """, (status, premium, current_timestamp, row_id))
        logger.info(f"Updated row {row_id} with status: {status}, premium: {premium}")
    except sqlite3.Error as e:
        logger.error(f"Database error updating strategy: {e}")
    
    conn.commit()
    conn.close()

def calculate_spread_premium(sell_data, buy_data):
    """
    Calculate the current market premium for a vertical spread
    
    Parameters:
    sell_data (dict): Market data for the sell leg
    buy_data (dict): Market data for the buy leg
    
    Returns:
    tuple: (premium amount, description of calculation method used)
    """
    premium = None
    calc_method = "unknown"
    
    # Check if we have bid/ask for both legs
    if (sell_data["bid"] is not None and sell_data["ask"] is not None and
        buy_data["bid"] is not None and buy_data["ask"] is not None):
        # Use midpoint prices for more accurate premium calculation
        sell_midpoint = (sell_data["bid"] + sell_data["ask"]) / 2
        buy_midpoint = (buy_data["bid"] + buy_data["ask"]) / 2
        premium = (sell_midpoint - buy_midpoint) * 100  # Convert to premium per contract
        calc_method = "midpoint"
    # Fallback to bid/ask if midpoints can't be calculated
    elif sell_data["bid"] is not None and buy_data["ask"] is not None:
        # Conservative estimate: what we can sell at bid and buy at ask
        premium = (sell_data["bid"] - buy_data["ask"]) * 100
        calc_method = "conservative"
    # Use last prices if available
    elif sell_data["last"] is not None and buy_data["last"] is not None:
        premium = (sell_data["last"] - buy_data["last"]) * 100
        calc_method = "last"
    # Use model prices if available
    elif sell_data["model"] is not None and buy_data["model"] is not None:
        premium = (sell_data["model"] - buy_data["model"]) * 100
        calc_method = "model"
        
    return premium, calc_method

def run_trading_app(db_path='../database/option_strategies.db', target_date=None, 
                   ibkr_host='127.0.0.1', ibkr_port=7497, client_id=None, 
                   allow_market_closed=False):
    if target_date is None:
        target_date = datetime.datetime.now().strftime('%Y-%m-%d')
    
    if client_id is None:
        client_id = random.randint(100, 9999)
    
    logger.info(f"Processing strategies for date: {target_date}")
    logger.info(f"Market closed orders allowed: {allow_market_closed}")
    
    # Get strategies
    df = get_strategies_for_date(db_path, target_date)
    if df.empty:
        logger.info(f"No strategies found for {target_date}")
        return
    
    logger.info(f"Found {len(df)} strategies to process")
    
    # Connect to IBKR
    app = IBApp()
    app.connect(ibkr_host, ibkr_port, client_id)
    
    ibkr_thread = threading.Thread(target=app.run)
    ibkr_thread.start()
    
    timeout = 10
    start_time = time.time()
    while not app.next_order_id and time.time() - start_time < timeout:
        time.sleep(0.1)
    
    if not app.next_order_id:
        logger.error("Failed to connect to IBKR or get valid order ID")
        app.disconnect()
        return
    
    # Process strategies
    for idx, row in df.iterrows():
        ticker = row['ticker']
        expiry = row['options_expiry_date']
        strategy_type = row['strategy_type']
        strike_buy = row['strike_buy']
        strike_sell = row['strike_sell']
        estimated_premium = row['estimated_premium']
        
        logger.info(f"Processing {strategy_type} for {ticker}, expiry {expiry}")
        
        # Set up contracts based on strategy type
        if strategy_type == 'Bear Call':
            sell_contract = app.create_option_contract(ticker, expiry, strike_sell, "C")
            buy_contract = app.create_option_contract(ticker, expiry, strike_buy, "C")
            combo_action = "SELL"
            option_right = "C"
        elif strategy_type == 'Bull Put':
            sell_contract = app.create_option_contract(ticker, expiry, strike_sell, "P")
            buy_contract = app.create_option_contract(ticker, expiry, strike_buy, "P")
            combo_action = "BUY"
            option_right = "P"
        else:
            logger.error(f"Unknown strategy type: {strategy_type}")
            continue
        
        # Get contract details
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
        
        try:
            # Check for valid estimated premium
            if estimated_premium is None or pd.isna(estimated_premium) or float(estimated_premium) <= 0:
                logger.error(f"Invalid estimated premium: {estimated_premium}")
                update_strategy_status(db_path, row['id'], 'invalid premium', 0)
                continue
            
            # Get current market prices
            req_id_sell_price = app.next_order_id
            app.next_order_id += 1
            sell_price_data = app.get_price_data(sell_contract, req_id_sell_price)
            
            req_id_buy_price = app.next_order_id
            app.next_order_id += 1
            buy_price_data = app.get_price_data(buy_contract, req_id_buy_price)
            
            # Calculate the actual market premium
            market_premium, calc_method = calculate_spread_premium(sell_price_data, buy_price_data)
            
            # Determine if we should place an order
            place_order = False
            
            # Ensure price is negative for credit collected
            limit_price = -abs(float(estimated_premium) / 100)
            limit_price = round(limit_price * 20) / 20  # Round to nearest 0.05 increment
            
            if market_premium is not None:
                logger.info(f"Calculated market premium: ${market_premium:.2f} using {calc_method} method")
                logger.info(f"Estimated premium: ${estimated_premium:.2f}")
                
                # Compare estimated vs market premium
                if market_premium >= float(estimated_premium):
                    place_order = True
                    logger.info(f"Market premium (${market_premium:.2f}) is >= estimated premium (${estimated_premium:.2f})")
                    # Use market premium for limit price when it's better
                    market_limit_price = -abs(market_premium / 100)  # Make sure it's negative
                    market_limit_price = round(market_limit_price * 20) / 20  # Round to nearest 0.05
                    limit_price = market_limit_price
                else:
                    logger.info(f"Market premium (${market_premium:.2f}) is less than estimated premium (${estimated_premium:.2f})")
                    # Check if market is closed but we're allowed to place orders
                    if app.market_status == "closed" and allow_market_closed:
                        place_order = True
                        logger.info("Market appears closed but allow_market_closed flag is set, placing order with estimated premium")
            else:
                logger.warning("Could not calculate market premium")
                # If market is closed but we allow orders, use estimated premium
                if app.market_status == "closed" and allow_market_closed:
                    place_order = True
                    logger.info("Market appears closed but allow_market_closed flag is set, using estimated premium")
                else:
                    update_strategy_status(db_path, row['id'], 'insufficient market data', 0)
                    continue
            
            # Place the order if conditions are met
            if place_order:
                logger.info(f"Placing order with limit price: ${limit_price:.2f} per share (TIF=DAY, Quantity=1)")
                
                # Create and place orders
                sell_conId = sell_details['conId']
                buy_conId = buy_details['conId']
                
                combo_contract = app.create_combo_contract(
                    ticker, [buy_contract, sell_contract], [buy_conId, sell_conId])
                
                # Place the entry order
                order_id = app.next_order_id
                app.next_order_id += 1
                order = app.create_limit_order(combo_action, 1, limit_price)
                
                app.placeOrder(order_id, combo_contract, order)
                
                logger.info(f"Placed entry order: ID {order_id}")
                update_strategy_status(db_path, row['id'], 'order placed', 
                                      market_premium if market_premium is not None else estimated_premium)
            else:
                logger.info("No order placed due to insufficient premium")
                update_strategy_status(db_path, row['id'], 'premium too low', 
                                      market_premium if market_premium is not None else 0)
            
        except Exception as e:
            logger.error(f"Error processing order: {str(e)}")
            import traceback
            logger.error(f"Exception details: {traceback.format_exc()}")
            update_strategy_status(db_path, row['id'], 'error', 0)
    
    # Cleanup
    time.sleep(3)
    app.disconnect()
    logger.info("Disconnected from IBKR")

def parse_arguments():
    parser = argparse.ArgumentParser(description='IBKR Market Order Script for Option Spreads - No Take Profit')
    
    parser.add_argument('--db', type=str, default='../database/option_strategies.db',
                       help='Path to SQLite database')
    parser.add_argument('--host', type=str, default='127.0.0.1',
                       help='IBKR TWS/Gateway host')
    parser.add_argument('--port', type=int, default=7497,
                       help='IBKR TWS/Gateway port (7497 for paper, 7496 for live)')
    parser.add_argument('--date', type=str, default=None,
                       help='Target date for strategies (YYYY-MM-DD format, default: today)')
    parser.add_argument('--client', type=int, default=None,
                       help='Client ID for IBKR connection (random if not specified)')
    parser.add_argument('--allow-market-closed', action='store_true',
                       help='Allow orders to be placed even if market is closed')
    
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    
    run_trading_app(
        db_path=args.db,
        target_date=args.date,
        ibkr_host=args.host,
        ibkr_port=args.port,
        client_id=args.client,
        allow_market_closed=args.allow_market_closed
    )
