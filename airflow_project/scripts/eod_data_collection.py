#!/usr/bin/env python3
"""
End-of-Day Orders & Trades Collection Script

Collects ALL orders (completed, open, pending, working) and executions from IBKR API
and stores in PostgreSQL.

The eod_orders table captures all orders regardless of fill status.
The eod_trades table only captures orders that were actually filled/executed.

Usage:
    python eod_data_collection.py [--date YYYY-MM-DD] [--port PORT]

This script can be run:
1. Manually - anytime after market close
2. Via Airflow - scheduled at 5:00 PM ET (Step 6)
"""

import sys
import os
import argparse
from datetime import datetime, date
import time
import queue
import logging
from collections import defaultdict

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.execution import ExecutionFilter
import threading

from database.database_config import DatabaseConnection

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# IBKR Wrapper and Client
# ============================================================================

class EODWrapper(EWrapper):
    """Extended EWrapper with callbacks for orders and executions"""

    def __init__(self):
        EWrapper.__init__(self)
        self.data_queue = queue.Queue()
        self.next_order_id = None

        # Storage for collected data
        self.completed_orders = []
        self.open_orders = []
        self.executions = []
        self.commissions = {}

        # Flags for completion
        self.completed_orders_done = False
        self.open_orders_done = False
        self.executions_done = False

    def nextValidId(self, orderId: int):
        """Connection confirmed"""
        super().nextValidId(orderId)
        self.next_order_id = orderId
        logger.info(f"Connected. Next Valid Order ID: {orderId}")
        self.data_queue.put(("connection_confirmed", None))

    def error(self, reqId: int, errorCode: int, errorString: str, *args):
        """Error callback"""
        if len(args) > 0:
            super().error(reqId, errorCode, errorString, *args)
        else:
            super().error(reqId, errorCode, errorString)

        # Only log actual errors (not info messages)
        if errorCode >= 2000:
            logger.debug(f"Info {errorCode}: {errorString}")
        else:
            logger.error(f"Error {errorCode} for request {reqId}: {errorString}")

        self.data_queue.put(("error", (reqId, errorCode, errorString)))

    # Completed Orders Callbacks

    def completedOrder(self, contract, order, orderState):
        """Callback for completed orders"""
        super().completedOrder(contract, order, orderState)

        order_data = {
            'contract': contract,
            'order': order,
            'orderState': orderState
        }

        self.completed_orders.append(order_data)

        logger.info(f"Completed Order: {order.orderId} | {contract.symbol} | "
                   f"{order.action} {order.totalQuantity} @ {order.orderType} | "
                   f"Status: {orderState.status}")

    def completedOrdersEnd(self):
        """Signals end of completed orders"""
        super().completedOrdersEnd()
        self.completed_orders_done = True
        logger.info(f"✓ Completed Orders End: Received {len(self.completed_orders)} orders")
        self.data_queue.put(("completed_orders_end", len(self.completed_orders)))

    # Open Orders Callbacks

    def openOrder(self, orderId, contract, order, orderState):
        """Callback for open orders"""
        super().openOrder(orderId, contract, order, orderState)

        order_data = {
            'contract': contract,
            'order': order,
            'orderState': orderState
        }

        self.open_orders.append(order_data)

        logger.info(f"Open Order: {order.orderId} | {contract.symbol} | "
                   f"{order.action} {order.totalQuantity} @ {order.orderType} | "
                   f"Status: {orderState.status}")

    def openOrderEnd(self):
        """Signals end of open orders"""
        super().openOrderEnd()
        self.open_orders_done = True
        logger.info(f"✓ Open Orders End: Received {len(self.open_orders)} orders")
        self.data_queue.put(("open_orders_end", len(self.open_orders)))

    # Executions Callbacks

    def execDetails(self, reqId: int, contract, execution):
        """Callback for execution details"""
        super().execDetails(reqId, contract, execution)

        exec_data = {
            'reqId': reqId,
            'contract': contract,
            'execution': execution
        }

        self.executions.append(exec_data)

        logger.info(f"Execution: {execution.execId} | Order: {execution.orderId} | "
                   f"{contract.symbol} | {execution.side} {execution.shares} @ ${execution.price}")

    def execDetailsEnd(self, reqId: int):
        """Signals end of executions"""
        super().execDetailsEnd(reqId)
        self.executions_done = True
        logger.info(f"✓ Executions End: Received {len(self.executions)} executions")
        self.data_queue.put(("executions_end", len(self.executions)))

    def commissionReport(self, commissionReport):
        """Callback for commission reports"""
        super().commissionReport(commissionReport)

        # Store commission by execId
        self.commissions[commissionReport.execId] = {
            'commission': commissionReport.commission,
            'currency': commissionReport.currency,
            'realizedPNL': commissionReport.realizedPNL
        }

        logger.debug(f"Commission: {commissionReport.execId} = "
                    f"${commissionReport.commission} {commissionReport.currency}")


class EODClient(EClient):
    """Client for IBKR API"""
    def __init__(self, wrapper):
        EClient.__init__(self, wrapper)


# ============================================================================
# Connection Functions
# ============================================================================

def connect_to_ibkr(host='127.0.0.1', port=4002, client_id=100, timeout=30):
    """
    Connect to IBKR Gateway

    Returns:
        tuple: (wrapper, client, api_thread) or (None, None, None) if failed
    """
    wrapper = EODWrapper()
    client = EODClient(wrapper)

    try:
        client.connect(host, port, client_id)
    except Exception as e:
        logger.error(f"Connection error: {e}")
        return None, None, None

    # Start API thread
    api_thread = threading.Thread(target=client.run, daemon=True)
    api_thread.start()

    # Wait for connection confirmation
    start_time = time.time()
    connected = False

    while time.time() - start_time < timeout:
        try:
            msg_type, msg_data = wrapper.data_queue.get(timeout=2)
            if msg_type == "connection_confirmed":
                connected = True
                break
            elif msg_type == "error":
                req_id, error_code, error_msg = msg_data
                if error_code == 502:
                    logger.error("Connection refused. Is IB Gateway running?")
                    return None, None, None
        except queue.Empty:
            continue

    if connected:
        logger.info("✓ Connected to IBKR")
        return wrapper, client, api_thread
    else:
        logger.error("Connection timeout")
        client.disconnect()
        return None, None, None


def collect_completed_orders(client, wrapper, timeout=15):
    """Request completed orders from IBKR"""
    logger.info("Requesting completed orders...")

    # Reset flags
    wrapper.completed_orders_done = False
    wrapper.completed_orders = []

    # Request completed orders (apiOnly=False gets all orders)
    client.reqCompletedOrders(False)

    # Wait for completion
    start_time = time.time()
    while time.time() - start_time < timeout:
        if wrapper.completed_orders_done:
            break
        time.sleep(0.5)

    if not wrapper.completed_orders_done:
        logger.warning(f"Timeout waiting for completed orders (got {len(wrapper.completed_orders)} so far)")

    return wrapper.completed_orders


def collect_open_orders(client, wrapper, timeout=15):
    """Request open/pending orders from IBKR"""
    logger.info("Requesting open orders...")

    # Reset flags
    wrapper.open_orders_done = False
    wrapper.open_orders = []

    # Request all open orders
    client.reqAllOpenOrders()

    # Wait for completion
    start_time = time.time()
    while time.time() - start_time < timeout:
        if wrapper.open_orders_done:
            break
        time.sleep(0.5)

    if not wrapper.open_orders_done:
        logger.warning(f"Timeout waiting for open orders (got {len(wrapper.open_orders)} so far)")

    return wrapper.open_orders


def collect_executions(client, wrapper, timeout=15):
    """Request executions from IBKR"""
    logger.info("Requesting executions...")

    # Reset flags
    wrapper.executions_done = False
    wrapper.executions = []
    wrapper.commissions = {}

    # Request all executions (empty filter)
    req_id = 1001
    exec_filter = ExecutionFilter()
    client.reqExecutions(req_id, exec_filter)

    # Wait for completion
    start_time = time.time()
    while time.time() - start_time < timeout:
        if wrapper.executions_done:
            break
        time.sleep(0.5)

    if not wrapper.executions_done:
        logger.warning(f"Timeout waiting for executions (got {len(wrapper.executions)} so far)")

    return wrapper.executions, wrapper.commissions


# ============================================================================
# Parsing Functions
# ============================================================================

def format_expiry(expiry_str):
    """Format expiry date to 'Nov28'25' format"""
    if not expiry_str or len(expiry_str) != 8:
        return expiry_str

    try:
        dt = datetime.strptime(expiry_str, '%Y%m%d')
        return dt.strftime("%b%d'%y")
    except:
        return expiry_str


def format_leg_description(contract, include_symbol=True):
    """Format option leg description"""
    expiry = format_expiry(contract.lastTradeDateOrContractMonth)
    strike = int(contract.strike) if contract.strike == int(contract.strike) else contract.strike
    right = "PUT" if contract.right == "P" else "CALL"

    if include_symbol:
        return f"{contract.symbol} {expiry} {strike} {right}"
    else:
        return f"{expiry} {strike} {right}"


def parse_combo_legs(contract):
    """Parse BAG contract into individual legs"""
    if contract.secType != "BAG" or not hasattr(contract, 'comboLegs'):
        return None

    legs = {'buy_leg': None, 'sell_leg': None}

    for leg in contract.comboLegs:
        if leg.action == "BUY":
            legs['buy_leg'] = leg
        elif leg.action == "SELL":
            legs['sell_leg'] = leg

    return legs


# ============================================================================
# Database Insert Functions
# ============================================================================

def insert_orders_to_db(all_orders, collection_date):
    """
    Parse all orders (completed + open) and insert into eod_orders table

    Args:
        all_orders: List of order dictionaries (from both completed and open orders)
        collection_date: Date of collection

    Returns:
        int: Number of rows inserted
    """
    if not all_orders:
        logger.info("No orders to insert")
        return 0

    db = DatabaseConnection()
    inserted = 0

    insert_query = """
        INSERT INTO eod_orders (
            order_id, perm_id, order_ref, spread_name, bot_leg, sld_leg,
            key_action, order_type, limit_price, total_quantity, filled_quantity,
            remaining_quantity, quantity_display, status, completed_time, completed_status,
            underlying_symbol, sec_type, currency, exchange,
            bot_leg_conid, sld_leg_conid,
            commission, commission_currency, collection_date
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (perm_id, collection_date) DO UPDATE SET
            order_id = EXCLUDED.order_id,
            status = EXCLUDED.status,
            filled_quantity = EXCLUDED.filled_quantity,
            remaining_quantity = EXCLUDED.remaining_quantity,
            quantity_display = EXCLUDED.quantity_display,
            completed_time = EXCLUDED.completed_time,
            completed_status = EXCLUDED.completed_status
    """

    with db.get_connection() as conn:
        cursor = db.get_cursor(conn)

        for order_data in all_orders:
            contract = order_data['contract']
            order = order_data['order']
            orderState = order_data['orderState']

            # Only process BAG (spread) orders
            if contract.secType != "BAG":
                logger.debug(f"Skipping non-BAG order {order.orderId}: {contract.secType}")
                continue

            # Parse combo legs
            legs = parse_combo_legs(contract)
            if not legs or not legs['buy_leg'] or not legs['sell_leg']:
                logger.debug(f"Skipping order {order.orderId}: Not a valid spread")
                continue

            buy_leg = legs['buy_leg']
            sell_leg = legs['sell_leg']

            # Format leg descriptions (just show "BUY leg" / "SELL leg" since we don't have full contract details)
            bot_leg_desc = f"BUY leg (conId:{buy_leg.conId})" if hasattr(buy_leg, 'conId') else "BUY leg"
            sld_leg_desc = f"SELL leg (conId:{sell_leg.conId})" if hasattr(sell_leg, 'conId') else "SELL leg"

            # Create spread name
            spread_name = f"{contract.symbol} Spread"

            # Quantity display
            filled = orderState.completedQuantity if hasattr(orderState, 'completedQuantity') else 0
            total = order.totalQuantity
            quantity_display = f"{filled}/{total}"

            # Completed time (use current time if not available)
            completed_time = datetime.now()

            # Handle limit price - check for infinity or very large values
            limit_price = None
            if hasattr(order, 'lmtPrice'):
                try:
                    lmt = float(order.lmtPrice)
                    # Check if it's a reasonable value (not infinity or extremely large)
                    if abs(lmt) < 1e10:
                        limit_price = lmt
                except (ValueError, OverflowError):
                    pass

            # Handle commission - check for reasonable values
            commission = None
            if hasattr(orderState, 'commission'):
                try:
                    comm = float(orderState.commission)
                    if abs(comm) < 1e10:
                        commission = comm
                except (ValueError, OverflowError):
                    pass

            try:
                cursor.execute(insert_query, (
                    order.orderId,
                    order.permId if hasattr(order, 'permId') else None,
                    order.orderRef if hasattr(order, 'orderRef') else None,
                    spread_name,
                    bot_leg_desc,
                    sld_leg_desc,
                    order.action,
                    order.orderType,
                    limit_price,
                    order.totalQuantity,
                    filled,
                    order.totalQuantity - filled,
                    quantity_display,
                    orderState.status,
                    completed_time,
                    orderState.completedStatus if hasattr(orderState, 'completedStatus') else None,
                    contract.symbol,
                    contract.secType,
                    contract.currency,
                    contract.exchange if hasattr(contract, 'exchange') else None,
                    buy_leg.conId if hasattr(buy_leg, 'conId') else None,
                    sell_leg.conId if hasattr(sell_leg, 'conId') else None,
                    commission,
                    'USD',
                    collection_date
                ))
                inserted += 1
                logger.debug(f"Inserted order {order.orderId}: {spread_name}")

            except Exception as e:
                logger.error(f"Error inserting order {order.orderId}: {e}")
                continue

        conn.commit()

    logger.info(f"✓ Inserted {inserted} orders into eod_orders")
    return inserted


def insert_trades_to_db(executions, commissions, collection_date):
    """
    Parse executions and insert trades into eod_trades table

    Returns:
        int: Number of rows inserted
    """
    # Group executions by permId (permanent order ID)
    # This handles cases where orderId is 0 for orders placed outside API session
    orders = defaultdict(list)
    for exec_dict in executions:
        execution = exec_dict['execution']
        orders[execution.permId].append(exec_dict)

    db = DatabaseConnection()
    inserted = 0

    insert_query = """
        INSERT INTO eod_trades (
            exec_id, order_id, perm_id, spread_name, bot_leg, sld_leg,
            spread_action, spread_price, buy_leg_price, sell_leg_price,
            execution_time, quantity, underlying_symbol,
            commission, commission_currency, collection_date
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (exec_id) DO UPDATE SET
            spread_price = EXCLUDED.spread_price,
            buy_leg_price = EXCLUDED.buy_leg_price,
            sell_leg_price = EXCLUDED.sell_leg_price,
            commission = EXCLUDED.commission
    """

    with db.get_connection() as conn:
        cursor = db.get_cursor(conn)

        for perm_id, exec_list in orders.items():
            # Filter out the BAG-level executions, keep only individual leg executions
            leg_execs = [e for e in exec_list if e['contract'].secType in ('OPT', 'FOP')]

            if not leg_execs:
                logger.debug(f"Skipping perm_id {perm_id}: No option leg executions found")
                continue

            # Group into BOT and SLD legs
            bot_legs = [e for e in leg_execs if e['execution'].side == "BOT"]
            sld_legs = [e for e in leg_execs if e['execution'].side == "SLD"]

            # Only process if we have both legs (spread)
            if len(bot_legs) == 0 or len(sld_legs) == 0:
                logger.debug(f"Skipping perm_id {perm_id}: Not a complete spread (BOT: {len(bot_legs)}, SLD: {len(sld_legs)})")
                continue

            # Use first execution of each side
            bot_exec = bot_legs[0]
            sld_exec = sld_legs[0]

            bot_contract = bot_exec['contract']
            sld_contract = sld_exec['contract']
            bot_execution = bot_exec['execution']
            sld_execution = sld_exec['execution']

            # Format legs
            bot_leg = format_leg_description(bot_contract, include_symbol=True)
            sld_leg = format_leg_description(sld_contract, include_symbol=True)

            # Calculate spread price
            buy_leg_price = bot_execution.price
            sell_leg_price = sld_execution.price
            spread_price = sell_leg_price - buy_leg_price

            # Spread action
            spread_action = "BOT" if bot_execution.side == "BOT" else "SLD"

            # Spread name
            bot_strike = int(bot_contract.strike) if bot_contract.strike == int(bot_contract.strike) else bot_contract.strike
            sld_strike = int(sld_contract.strike) if sld_contract.strike == int(sld_contract.strike) else sld_contract.strike
            expiry = format_expiry(bot_contract.lastTradeDateOrContractMonth)
            right_name = "Put" if bot_contract.right == "P" else "Call"
            spread_name = f"{bot_contract.symbol} {expiry} {bot_strike}/{sld_strike} Bull {right_name}"

            # Get commission
            total_commission = 0.0
            commission_currency = "USD"
            for exec_dict in exec_list:
                exec_id = exec_dict['execution'].execId
                if exec_id in commissions:
                    total_commission += commissions[exec_id]['commission']
                    commission_currency = commissions[exec_id]['currency']

            # Insert
            try:
                # Get the actual order_id from the first execution
                order_id = bot_execution.orderId

                cursor.execute(insert_query, (
                    f"{bot_execution.execId}+{sld_execution.execId}",
                    order_id,
                    bot_execution.permId,
                    spread_name,
                    bot_leg,
                    sld_leg,
                    spread_action,
                    spread_price,
                    buy_leg_price,
                    sell_leg_price,
                    bot_execution.time,
                    bot_execution.shares,
                    bot_contract.symbol,
                    total_commission,
                    commission_currency,
                    collection_date
                ))
                inserted += 1
                logger.debug(f"Inserted trade for perm_id {perm_id}: {spread_name}")
            except Exception as e:
                logger.error(f"Error inserting trade for perm_id {perm_id}: {e}")

        conn.commit()

    logger.info(f"✓ Inserted {inserted} trades into eod_trades")
    return inserted


# ============================================================================
# Main Collection Function
# ============================================================================

def collect_eod_data(collection_date, port=4002, host='127.0.0.1'):
    """
    Main function to collect EOD orders and trades

    Args:
        collection_date: Date to collect data for
        port: IBKR gateway port (4002 for paper, 4001 for live)
        host: IBKR gateway host

    Returns:
        tuple: (orders_count, trades_count)
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Starting EOD Data Collection for {collection_date}")
    logger.info(f"Connecting to {host}:{port}")
    logger.info(f"{'='*60}\n")

    # Connect to IBKR
    wrapper, client, api_thread = connect_to_ibkr(host=host, port=port, client_id=100)

    if not client:
        logger.error("Failed to connect to IBKR. Exiting.")
        return 0, 0

    try:
        # Collect completed orders
        logger.info("\n[1/5] Collecting Completed Orders...")
        completed_orders = collect_completed_orders(client, wrapper, timeout=15)
        logger.info(f"✓ Collected {len(completed_orders)} completed orders\n")

        # Collect open/pending orders
        logger.info("[2/5] Collecting Open/Pending Orders...")
        open_orders = collect_open_orders(client, wrapper, timeout=15)
        logger.info(f"✓ Collected {len(open_orders)} open orders\n")

        # Combine all orders
        all_orders = completed_orders + open_orders
        logger.info(f"Total orders to process: {len(all_orders)} (completed: {len(completed_orders)}, open: {len(open_orders)})\n")

        # Collect executions (trades)
        logger.info("[3/5] Collecting Executions...")
        executions, commissions = collect_executions(client, wrapper, timeout=15)
        logger.info(f"✓ Collected {len(executions)} executions\n")

        # Save orders to database
        logger.info("[4/5] Saving Orders to Database...")
        orders_count = insert_orders_to_db(all_orders, collection_date)

        # Save trades to database
        logger.info("[5/5] Saving Trades to Database...")
        trades_count = insert_trades_to_db(executions, commissions, collection_date)

        logger.info(f"\n{'='*60}")
        logger.info(f"EOD Data Collection Complete")
        logger.info(f"Total Orders: {orders_count} (completed: {len(completed_orders)}, open: {len(open_orders)})")
        logger.info(f"Trades: {trades_count}")
        logger.info(f"{'='*60}\n")

        return orders_count, trades_count

    except Exception as e:
        logger.error(f"Error during collection: {e}", exc_info=True)
        return 0, 0

    finally:
        # Disconnect
        logger.info("Disconnecting from IBKR...")
        client.disconnect()
        time.sleep(1)


# ============================================================================
# CLI Entry Point
# ============================================================================

def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Collect end-of-day orders and trades from IBKR'
    )
    parser.add_argument(
        '--date',
        type=str,
        default=date.today().isoformat(),
        help='Collection date (YYYY-MM-DD), defaults to today'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=4002,
        help='IBKR gateway port (4002 for paper, 4001 for live)'
    )
    parser.add_argument(
        '--host',
        type=str,
        default='127.0.0.1',
        help='IBKR gateway host'
    )

    args = parser.parse_args()

    # Parse collection date
    try:
        collection_date = datetime.strptime(args.date, '%Y-%m-%d').date()
    except ValueError:
        logger.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD")
        sys.exit(1)

    # Run collection
    orders_count, trades_count = collect_eod_data(
        collection_date=collection_date,
        port=args.port,
        host=args.host
    )

    # Exit with appropriate code
    if orders_count > 0 or trades_count > 0:
        logger.info("✓ Collection successful")
        sys.exit(0)
    else:
        logger.warning("No data collected (this may be normal if no orders/trades today)")
        sys.exit(0)


if __name__ == "__main__":
    main()
