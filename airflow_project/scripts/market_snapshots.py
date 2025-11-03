"""
Market Snapshots Capture Module
Captures IBKR position data and writes to database every 30 minutes
"""
import time
import threading
import pandas as pd
import random
import datetime
import psycopg2
import os
import sys
import json
from decimal import Decimal
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
import logging

logger = logging.getLogger(__name__)


def safe_float_convert(value):
    """Safely convert any value to float, handling Decimal types"""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


class IBKRPositionApp(EWrapper, EClient):
    """IBKR Position App for capturing market snapshots"""

    def __init__(self):
        EClient.__init__(self, self)
        self.positions = {}
        self.market_data = {}
        self.req_id = 1000
        self.position_data_received = False
        self.market_data_requests = {}
        self.account_updates = {}
        self.account_update_complete = False

    def connectTWS(self, host='127.0.0.1', port=4002):
        """Connect to TWS or IB Gateway"""
        try:
            client_id = random.randint(1, 999)

            self.connect(host, port, client_id)
            thread = threading.Thread(target=self.run)
            thread.daemon = True
            thread.start()
            time.sleep(2)

            if self.isConnected():
                logger.info(f"Connected to TWS/Gateway on {host}:{port}")
                return True
            return False
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    def position(self, account, contract, position, avgCost):
        """Callback for position data"""
        key = f"{contract.symbol}_{contract.secType}_{contract.strike}_{contract.right}_{contract.lastTradeDateOrContractMonth}"

        avg_cost_raw = safe_float_convert(avgCost)
        position_float = safe_float_convert(position)
        multiplier = 100.0 if contract.secType == 'OPT' else 1.0
        avg_cost_per_unit = (avg_cost_raw / multiplier) if avg_cost_raw is not None else None

        self.positions[key] = {
            'Account': account,
            'Symbol': contract.symbol,
            'SecType': contract.secType,
            'Description': f"{contract.symbol} {contract.lastTradeDateOrContractMonth} {contract.strike} {contract.right}",
            'AvgCost': avg_cost_per_unit,
            'Strike': safe_float_convert(contract.strike) if hasattr(contract, 'strike') else None,
            'Right': contract.right if hasattr(contract, 'right') else None,
            'Expiry': contract.lastTradeDateOrContractMonth,
            'Position': position_float,
            'Contract': contract,
            'ConId': contract.conId,
            'CurrentPrice': None,
            'MarketVal': None,
            'UnrealizedPnL': None
        }

    def positionEnd(self):
        """Callback when all positions have been received"""
        self.position_data_received = True
        logger.info("All position data received")

    def updateAccountValue(self, key, val, currency, accountName):
        """Callback for account value updates"""
        pass

    def updatePortfolio(self, contract, position, marketPrice, marketValue, averageCost,
                       unrealizedPNL, realizedPNL, accountName):
        """Callback for portfolio updates with market values"""
        key = f"{contract.symbol}_{contract.secType}_{contract.strike}_{contract.right}_{contract.lastTradeDateOrContractMonth}"

        logger.debug(f"Portfolio update for {key}: Price={marketPrice}, MktVal={marketValue}, PnL={unrealizedPNL}")

        # Store the portfolio update data
        self.account_updates[key] = {
            'MarketPrice': safe_float_convert(marketPrice),
            'MarketValue': safe_float_convert(marketValue),
            'UnrealizedPNL': safe_float_convert(unrealizedPNL),
            'AverageCost': safe_float_convert(averageCost),
            'Position': safe_float_convert(position)
        }

    def accountDownloadEnd(self, accountName):
        """Callback when account download is complete"""
        self.account_update_complete = True
        logger.info(f"Account download complete for {accountName}")

    def error(self, reqId, errorCode, errorString):
        """Callback for error messages"""
        # Only log non-informational errors
        if errorCode not in [2104, 2106, 2158]:
            logger.warning(f"IBKR Error: reqId={reqId}, code={errorCode}, msg={errorString}")

    def get_positions_data(self):
        """Request positions and wait for data"""
        self.reqPositions()
        timeout = 30
        start_time = time.time()

        while not self.position_data_received and (time.time() - start_time) < timeout:
            time.sleep(0.1)

        return len(self.positions)

    def get_account_updates(self, account_id):
        """Request account updates to get market values"""
        logger.info(f"Requesting account updates for {account_id}")
        self.reqAccountUpdates(True, account_id)

        # Wait for account updates
        timeout = 10
        start_time = time.time()
        while not self.account_update_complete and (time.time() - start_time) < timeout:
            time.sleep(0.1)

        # Stop account updates
        self.reqAccountUpdates(False, account_id)

        # Update positions with account data
        logger.info("Updating positions with account data")
        for key, pos in self.positions.items():
            if key in self.account_updates:
                acc_data = self.account_updates[key]
                self.positions[key]['CurrentPrice'] = acc_data.get('MarketPrice')
                self.positions[key]['MarketVal'] = acc_data.get('MarketValue')
                self.positions[key]['UnrealizedPnL'] = acc_data.get('UnrealizedPNL')

    def find_vertical_spreads(self, df):
        """Identify vertical spreads from options positions"""
        options_df = df[df['SecType'] == 'OPT'].copy()
        if options_df.empty:
            return pd.DataFrame()

        spreads = []
        grouped = options_df.groupby(['Symbol', 'Right', 'Expiry'])

        for (symbol, right, expiry), group in grouped:
            if len(group) >= 2:
                for i in range(len(group)):
                    for j in range(i + 1, len(group)):
                        pos1, pos2 = group.iloc[i], group.iloc[j]

                        strike1 = safe_float_convert(pos1['Strike'])
                        strike2 = safe_float_convert(pos2['Strike'])
                        position1 = safe_float_convert(pos1['Position'])
                        position2 = safe_float_convert(pos2['Position'])

                        if all(v is not None for v in [strike1, strike2, position1, position2]):
                            if (position1 > 0 and position2 < 0) or (position1 < 0 and position2 > 0):
                                if abs(position1) == abs(position2):
                                    spread_type = "Bull" if (strike1 < strike2 and position1 > 0) else "Bear"
                                    spread_type += " Call" if right == "C" else " Put"

                                    avg_cost1 = safe_float_convert(pos1['AvgCost'])
                                    avg_cost2 = safe_float_convert(pos2['AvgCost'])
                                    net_cost = (avg_cost1 * position1 + avg_cost2 * position2) / abs(position1)

                                    current1 = safe_float_convert(pos1['CurrentPrice'])
                                    current2 = safe_float_convert(pos2['CurrentPrice'])
                                    current_value = None
                                    market_val = None
                                    unrealized_pnl = None

                                    if current1 is not None and current2 is not None and current1 > 0 and current2 > 0:
                                        current_value = (current1 * position1 + current2 * position2) / abs(position1)
                                        market_val = current_value * abs(position1) * 100
                                        if net_cost is not None:
                                            unrealized_pnl = (current_value - net_cost) * abs(position1) * 100

                                    spreads.append({
                                        'Symbol': symbol,
                                        'Description': f"{spread_type} {strike1}/{strike2} {expiry}",
                                        'AvgCost': net_cost,
                                        'CurrentPrice': current_value,
                                        'Position': abs(position1),
                                        'MarketVal': market_val,
                                        'UnrealizedPnL': unrealized_pnl
                                    })

        return pd.DataFrame(spreads)

    def get_positions_dataframe(self):
        """Convert positions to DataFrame"""
        data = []
        for key, pos in self.positions.items():
            data.append({
                'Symbol': pos['Symbol'],
                'SecType': pos['SecType'],
                'Description': pos['Description'],
                'AvgCost': pos['AvgCost'],
                'CurrentPrice': pos['CurrentPrice'],
                'Position': pos['Position'],
                'MarketVal': pos['MarketVal'],
                'UnrealizedPnL': pos['UnrealizedPnL'],
                'Strike': pos['Strike'],
                'Right': pos['Right'],
                'Expiry': pos['Expiry']
            })
        return pd.DataFrame(data)

    def disconnect_tws(self):
        """Disconnect from TWS"""
        if self.isConnected():
            self.disconnect()


def get_database_credentials():
    """Load database credentials from config file"""
    # Import here to avoid circular dependencies
    import sys
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config')
    if config_path not in sys.path:
        sys.path.insert(0, config_path)

    from credentials_loader import CredentialsLoader

    loader = CredentialsLoader()
    pg_creds = loader.get_database_config('postgresql')

    return pg_creds


def get_option_strategies(pg_creds):
    """Get option strategies from the database"""
    try:
        conn = psycopg2.connect(
            host=pg_creds['host'],
            port=pg_creds['port'],
            database=pg_creds['database'],
            user=pg_creds['user'],
            password=pg_creds['password']
        )

        query = """
        SELECT id, strategy_type, ticker, trigger_price, strike_buy, strike_sell,
               estimated_premium, options_expiry_date, scrape_date, strategy_status, trade_id
        FROM option_strategies
        WHERE strategy_status IN ('order placed', 'active')
        ORDER BY scrape_date DESC
        """

        db_strategies_df = pd.read_sql_query(query, conn)
        conn.close()
        return db_strategies_df

    except Exception as e:
        logger.error(f"Database query failed: {e}")
        return pd.DataFrame()


def join_spreads_with_database(spreads_df, db_strategies_df):
    """Join IBKR spreads with database strategies"""
    if spreads_df.empty or db_strategies_df.empty:
        return pd.DataFrame()

    joined_data = []
    unmatched_spreads = []

    for _, ibkr_row in spreads_df.iterrows():
        description = ibkr_row['Description']
        symbol = ibkr_row['Symbol']

        parts = description.split()
        strategy_type = ' '.join(parts[:2])
        strike_info = parts[2]
        expiry = parts[3]

        strikes = strike_info.split('/')
        strike1, strike2 = float(strikes[0]), float(strikes[1])

        if "Bull" in strategy_type:
            db_strike_buy = min(strike1, strike2)
            db_strike_sell = max(strike1, strike2)
        else:
            db_strike_buy = max(strike1, strike2)
            db_strike_sell = min(strike1, strike2)

        expiry_date = f"{expiry[:4]}-{expiry[4:6]}-{expiry[6:]}"

        matches = db_strategies_df[
            (db_strategies_df['ticker'] == symbol) &
            (db_strategies_df['strategy_type'] == strategy_type) &
            (db_strategies_df['strike_buy'] == db_strike_buy) &
            (db_strategies_df['strike_sell'] == db_strike_sell) &
            (db_strategies_df['options_expiry_date'].astype(str) == expiry_date)
        ]

        if matches.empty:
            unmatched_spreads.append(f"{symbol} {description}")

        for _, db_row in matches.iterrows():
            joined_data.append({
                'ibkr_symbol': symbol,
                'ibkr_description': description,
                'ibkr_avg_cost': ibkr_row['AvgCost'],
                'ibkr_current_price': ibkr_row['CurrentPrice'],
                'ibkr_unrealized_pnl': ibkr_row['UnrealizedPnL'],
                'ibkr_market_val': ibkr_row['MarketVal'],
                'ibkr_position': ibkr_row['Position'],
                'db_id': db_row['id'],
                'db_ticker': db_row['ticker'],
                'db_strategy_type': db_row['strategy_type'],
                'db_estimated_premium': db_row['estimated_premium'],
                'db_trade_id': db_row['trade_id'],
                'premium_difference': ibkr_row['AvgCost'] - db_row['estimated_premium']
            })

    # Log unmatched spreads
    if unmatched_spreads:
        logger.warning(f"Spreads in IBKR but not in database: {', '.join(unmatched_spreads)}")

    return pd.DataFrame(joined_data)


def insert_positions_to_database(joined_df, pg_creds):
    """Insert joined position data into ibkr_positions table"""
    if joined_df.empty:
        return False

    try:
        conn = psycopg2.connect(
            host=pg_creds['host'],
            port=pg_creds['port'],
            database=pg_creds['database'],
            user=pg_creds['user'],
            password=pg_creds['password']
        )

        cursor = conn.cursor()

        for _, row in joined_df.iterrows():
            insert_sql = """
            INSERT INTO ibkr_positions (
                ibkr_symbol, ibkr_description, ibkr_avg_cost, ibkr_current_price,
                ibkr_unrealized_pnl, ibkr_market_val, ibkr_position,
                db_id, db_ticker, db_strategy_type, db_estimated_premium,
                db_trade_id, premium_difference
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ibkr_symbol, ibkr_description, db_id)
            DO UPDATE SET
                ibkr_current_price = EXCLUDED.ibkr_current_price,
                ibkr_unrealized_pnl = EXCLUDED.ibkr_unrealized_pnl,
                ibkr_market_val = EXCLUDED.ibkr_market_val,
                updated_at = CURRENT_TIMESTAMP
            """

            cursor.execute(insert_sql, (
                row['ibkr_symbol'],
                row['ibkr_description'],
                row['ibkr_avg_cost'],
                row['ibkr_current_price'],
                row['ibkr_unrealized_pnl'],
                row['ibkr_market_val'],
                row['ibkr_position'],
                row['db_id'],
                row['db_ticker'],
                row['db_strategy_type'],
                row['db_estimated_premium'],
                row['db_trade_id'],
                row['premium_difference']
            ))

        conn.commit()
        cursor.close()
        conn.close()
        logger.info(f"Inserted/updated {len(joined_df)} positions to database")
        return True

    except Exception as e:
        logger.error(f"Database insert failed: {e}")
        return False


def capture_market_snapshots(positions_df, spreads_df, joined_df, pg_creds):
    """Capture market snapshots from IBKR data to database"""
    snapshots_created = 0
    snapshots_failed = 0

    logger.info("Capturing market snapshots")

    for _, spread_row in joined_df.iterrows():
        db_trade_id = spread_row['db_trade_id']

        # Get position_id from database
        try:
            conn = psycopg2.connect(
                host=pg_creds['host'],
                port=pg_creds['port'],
                database=pg_creds['database'],
                user=pg_creds['user'],
                password=pg_creds['password']
            )
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM ibkr_positions WHERE db_trade_id = %s LIMIT 1", (db_trade_id,))
            result = cursor.fetchone()
            cursor.close()
            conn.close()

            if not result:
                logger.warning(f"No position found for {db_trade_id}")
                snapshots_failed += 1
                continue
            position_id = str(result[0])
        except Exception as e:
            logger.error(f"Error getting position_id: {e}")
            snapshots_failed += 1
            continue

        # Parse spread to find legs
        description = spread_row['ibkr_description']
        symbol = spread_row['ibkr_symbol']
        parts = description.split()
        strike_info = parts[2]
        expiry = parts[3]
        strikes = strike_info.split('/')
        strike1, strike2 = float(strikes[0]), float(strikes[1])
        right = 'P' if 'Put' in description else 'C'

        # Find legs in positions_df
        leg1 = positions_df[
            (positions_df['Symbol'] == symbol) &
            (positions_df['Strike'] == strike1) &
            (positions_df['Right'] == right) &
            (positions_df['Expiry'] == expiry)
        ]
        leg2 = positions_df[
            (positions_df['Symbol'] == symbol) &
            (positions_df['Strike'] == strike2) &
            (positions_df['Right'] == right) &
            (positions_df['Expiry'] == expiry)
        ]

        if leg1.empty or leg2.empty:
            logger.warning(f"Missing legs for {description}")
            snapshots_failed += 1
            continue

        leg1_row, leg2_row = leg1.iloc[0], leg2.iloc[0]

        # Insert snapshot
        try:
            conn = psycopg2.connect(
                host=pg_creds['host'],
                port=pg_creds['port'],
                database=pg_creds['database'],
                user=pg_creds['user'],
                password=pg_creds['password']
            )
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO market_snapshots (
                    position_id, db_trade_id,
                    spread_market_val, spread_unrealized_pnl, spread_current_price,
                    leg1_symbol, leg1_description, leg1_market_val, leg1_unrealized_pnl,
                    leg1_current_price, leg1_position,
                    leg2_symbol, leg2_description, leg2_market_val, leg2_unrealized_pnl,
                    leg2_current_price, leg2_position
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                position_id,
                db_trade_id,
                safe_float_convert(spread_row['ibkr_market_val']),
                safe_float_convert(spread_row['ibkr_unrealized_pnl']),
                safe_float_convert(spread_row['ibkr_current_price']),
                str(leg1_row['Symbol']),
                str(leg1_row['Description']),
                safe_float_convert(leg1_row['MarketVal']),
                safe_float_convert(leg1_row['UnrealizedPnL']),
                safe_float_convert(leg1_row['CurrentPrice']),
                safe_float_convert(leg1_row['Position']),
                str(leg2_row['Symbol']),
                str(leg2_row['Description']),
                safe_float_convert(leg2_row['MarketVal']),
                safe_float_convert(leg2_row['UnrealizedPnL']),
                safe_float_convert(leg2_row['CurrentPrice']),
                safe_float_convert(leg2_row['Position'])
            ))
            conn.commit()
            cursor.close()
            conn.close()
            snapshots_created += 1
            logger.info(f"Snapshot created for {symbol} {description}")
        except Exception as e:
            logger.error(f"Failed to create snapshot for {symbol}: {e}")
            snapshots_failed += 1

    logger.info(f"Snapshots summary: {snapshots_created} created, {snapshots_failed} failed")
    return snapshots_created


def run_market_snapshots(port=4002, account_id="DU9233079", **context):
    """
    Main function to capture market snapshots

    Args:
        port (int): IB Gateway port (default: 4002 for paper trading)
        account_id (str): IBKR account ID
        **context: Airflow context (ignored)

    Returns:
        dict: Summary of snapshot operation
    """
    logger.info("="*80)
    logger.info("Starting market snapshots capture")
    logger.info("="*80)

    try:
        # Load database credentials
        pg_creds = get_database_credentials()

        # Connect to IBKR
        app = IBKRPositionApp()
        connected = app.connectTWS(port=port)

        if not connected:
            logger.error("Failed to connect to IB Gateway - gateway may not be running")
            return {
                'success': False,
                'error': 'Gateway connection failed',
                'snapshots_created': 0
            }

        # Get positions
        num_positions = app.get_positions_data()
        logger.info(f"Retrieved {num_positions} positions from IBKR")

        # Get account updates (includes market values and prices)
        app.get_account_updates(account_id)

        # Get dataframes
        positions_df = app.get_positions_dataframe()
        spreads_df = app.find_vertical_spreads(positions_df)
        logger.info(f"Identified {len(spreads_df)} spreads")

        # Get database strategies and join
        db_strategies_df = get_option_strategies(pg_creds)
        logger.info(f"Retrieved {len(db_strategies_df)} strategies from database")

        snapshots_created = 0

        if not spreads_df.empty and not db_strategies_df.empty:
            joined_df = join_spreads_with_database(spreads_df, db_strategies_df)
            logger.info(f"Matched {len(joined_df)} spreads with database")

            if not joined_df.empty:
                # Insert positions
                insert_positions_to_database(joined_df, pg_creds)

                # Capture market snapshots
                snapshots_created = capture_market_snapshots(positions_df, spreads_df, joined_df, pg_creds)

        # Disconnect
        app.disconnect_tws()

        logger.info("="*80)
        logger.info(f"Market snapshots capture complete: {snapshots_created} snapshots created")
        logger.info("="*80)

        return {
            'success': True,
            'snapshots_created': snapshots_created,
            'positions_retrieved': num_positions,
            'spreads_identified': len(spreads_df),
            'matched_spreads': len(joined_df) if not spreads_df.empty and not db_strategies_df.empty else 0
        }

    except Exception as e:
        logger.error(f"Market snapshots capture failed: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'snapshots_created': 0
        }


if __name__ == "__main__":
    # Standalone execution for testing
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    result = run_market_snapshots()
    print("\nResult:", result)
