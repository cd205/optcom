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
logger = logging.getLogger(__name__)

class IBWrapper(EWrapper):
    def __init__(self):
        super().__init__()
        self.next_order_id = None
        self.contract_details = {}
        self.mid_prices = {}
        self.combo_ids = {}

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
    
    def create_limit_order(self, action, quantity, price, parent_id=None, transmit=True):
        order = Order()
        order.action = action
        order.orderType = "LMT"
        order.totalQuantity = quantity
        order.lmtPrice = price
        if parent_id is not None:
            order.parentId = parent_id
        order.transmit = transmit
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
        logger.info(f"Requesting market data for {contract.symbol} {contract.strike} {contract.right} (req_id: {req_id})")
        self.reqMktData(req_id, contract, "", False, False, [])
        time.sleep(5)
        
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
    AND (strategy_status IS NULL OR strategy_status != 'order placed with take profit')
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

def run_trading_app(db_path='../database/option_strategies.db', target_date=None, ibkr_host='127.0.0.1', ibkr_port=7497, client_id=None):
    if target_date is None:
        target_date = datetime.datetime.now().strftime('%Y-%m-%d')
    
    if client_id is None:
        client_id = random.randint(100, 9999)
    
    logger.info(f"Processing strategies for date: {target_date}")
    
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
            take_profit_action = "BUY"
            option_right = "C"
        elif strategy_type == 'Bull Put':
            sell_contract = app.create_option_contract(ticker, expiry, strike_sell, "P")
            buy_contract = app.create_option_contract(ticker, expiry, strike_buy, "P")
            combo_action = "SELL"
            take_profit_action = "BUY"
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
        
        # Get market data
        req_id_sell_price = app.next_order_id
        app.next_order_id += 1
        app.get_price_data(sell_contract, req_id_sell_price)
        
        req_id_buy_price = app.next_order_id
        app.next_order_id += 1
        app.get_price_data(buy_contract, req_id_buy_price)
        
        try:
            # Initialize prices
            sell_price = None
            buy_price = None
            
            # Try to get live prices
            if req_id_sell_price in app.mid_prices:
                prices = app.mid_prices[req_id_sell_price]
                if prices.get('bid') and prices.get('ask') and prices.get('bid') > 0 and prices.get('ask') > 0:
                    sell_price = (prices.get('bid') + prices.get('ask')) / 2
                elif prices.get('model') and prices.get('model') > 0:
                    sell_price = prices.get('model')
                elif prices.get('last') and prices.get('last') > 0:
                    sell_price = prices.get('last')
            
            if req_id_buy_price in app.mid_prices:
                prices = app.mid_prices[req_id_buy_price]
                if prices.get('bid') and prices.get('ask') and prices.get('bid') > 0 and prices.get('ask') > 0:
                    buy_price = (prices.get('bid') + prices.get('ask')) / 2
                elif prices.get('model') and prices.get('model') > 0:
                    buy_price = prices.get('model')
                elif prices.get('last') and prices.get('last') > 0:
                    buy_price = prices.get('last')
            
            # If live prices aren't available, get historical prices
            if not (sell_price and buy_price and sell_price > 0 and buy_price > 0):
                logger.info("Live market data unavailable, using historical prices")
                hist_sell_price, hist_buy_price = get_last_prices_from_db(
                    db_path, ticker, strike_sell, strike_buy, option_right)
                
                if hist_sell_price and hist_sell_price > 0:
                    sell_price = hist_sell_price
                
                if hist_buy_price and hist_buy_price > 0:
                    buy_price = hist_buy_price
            
            # Final validation check
            if not (sell_price and buy_price and sell_price > 0 and buy_price > 0):
                logger.error("No valid price data available for one or both legs")
                update_strategy_status(db_path, row['id'], 'no valid price data', 0)
                continue
            
            logger.info(f"Using prices - Sell: {sell_price}, Buy: {buy_price}")
            
            # Calculate premium
            premium_collected = sell_price - buy_price
            premium_collected_dollar = premium_collected * 100
            
            logger.info(f"Premium collected: {premium_collected} per share, ${premium_collected_dollar:.2f} per contract")
            logger.info(f"Estimated premium in database: ${estimated_premium:.2f} per contract")
            
            # Check if premium is sufficient
            if premium_collected_dollar < estimated_premium:
                update_strategy_status(db_path, row['id'], 'premium too low', premium_collected_dollar)
                continue
            
            # Create and place orders
            sell_conId = sell_details['conId']
            buy_conId = buy_details['conId']
            
            combo_contract = app.create_combo_contract(
                ticker, [buy_contract, sell_contract], [buy_conId, sell_conId])
            
            # Calculate prices
            take_profit_price = premium_collected / 2
            entry_limit_price = premium_collected
            
            # Parent order (entry)
            parent_order_id = app.next_order_id
            app.next_order_id += 1
            parent_order = app.create_limit_order(combo_action, 1, entry_limit_price, transmit=False)
            
            # Child order (take profit)
            take_profit_order_id = app.next_order_id
            app.next_order_id += 1
            take_profit_order = app.create_limit_order(
                take_profit_action, 1, take_profit_price, 
                parent_id=parent_order_id, transmit=True)
            
            # Place the orders
            app.placeOrder(parent_order_id, combo_contract, parent_order)
            app.placeOrder(take_profit_order_id, combo_contract, take_profit_order)
            
            logger.info(f"Placed orders: Entry {parent_order_id}, Take profit {take_profit_order_id}")
            update_strategy_status(db_path, row['id'], 'order placed with take profit', premium_collected_dollar)
            
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
    parser = argparse.ArgumentParser(description='IBKR Market Order Script for Option Spreads with Take Profit')
    
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
    
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    
    run_trading_app(
        db_path=args.db,
        target_date=args.date,
        ibkr_host=args.host,
        ibkr_port=args.port,
        client_id=args.client
    )