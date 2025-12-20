"""
Options Greeks Capture - Airflow Integration
Captures options Greeks from IBKR (live market data) with Black-Scholes fallback
"""
import time
import threading
import pandas as pd
import numpy as np
import random
import datetime
import psycopg2
import os
import sys
import json
from decimal import Decimal
from scipy.stats import norm
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Risk-free rate (3-month Treasury ~5.3%)
RISK_FREE_RATE = 0.053


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


def calculate_greeks_bs(spot_price, strike, time_to_expiry, risk_free_rate, implied_vol, option_type, option_price=None):
    """
    Calculate Black-Scholes Greeks for an option

    Args:
        spot_price: Current price of underlying
        strike: Option strike price
        time_to_expiry: Time to expiration in years
        risk_free_rate: Risk-free interest rate (e.g., 0.053 for 5.3%)
        implied_vol: Implied volatility (e.g., 0.25 for 25%)
        option_type: 'C' for call, 'P' for put
        option_price: Current option price (for time/intrinsic value)

    Returns:
        dict with delta, gamma, theta, vega, rho, intrinsic_value, time_value
    """
    try:
        # Handle edge cases
        if time_to_expiry <= 0:
            # Expired option - only intrinsic value
            if option_type == 'C':
                intrinsic = max(0, spot_price - strike)
                delta = 1.0 if spot_price > strike else 0.0
            else:
                intrinsic = max(0, strike - spot_price)
                delta = -1.0 if strike > spot_price else 0.0

            return {
                'delta': delta,
                'gamma': 0.0,
                'theta': 0.0,
                'vega': 0.0,
                'rho': 0.0,
                'intrinsic_value': intrinsic,
                'time_value': 0.0,
                'implied_volatility': implied_vol
            }

        if implied_vol <= 0:
            implied_vol = 0.25  # Default to 25% if invalid

        # Calculate d1 and d2
        d1 = (np.log(spot_price / strike) + (risk_free_rate + 0.5 * implied_vol**2) * time_to_expiry) / (implied_vol * np.sqrt(time_to_expiry))
        d2 = d1 - implied_vol * np.sqrt(time_to_expiry)

        # Standard normal PDF and CDF
        n_d1 = norm.pdf(d1)
        N_d1 = norm.cdf(d1)
        N_d2 = norm.cdf(d2)

        # Calculate Greeks based on option type
        if option_type == 'C':  # Call option
            delta = N_d1
            theta = (-(spot_price * n_d1 * implied_vol) / (2 * np.sqrt(time_to_expiry))
                    - risk_free_rate * strike * np.exp(-risk_free_rate * time_to_expiry) * N_d2) / 365
            rho = strike * time_to_expiry * np.exp(-risk_free_rate * time_to_expiry) * N_d2 / 100
            intrinsic_value = max(0, spot_price - strike)
        else:  # Put option
            delta = N_d1 - 1
            theta = (-(spot_price * n_d1 * implied_vol) / (2 * np.sqrt(time_to_expiry))
                    + risk_free_rate * strike * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2)) / 365
            rho = -strike * time_to_expiry * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2) / 100
            intrinsic_value = max(0, strike - spot_price)

        # Greeks that are same for both calls and puts
        gamma = n_d1 / (spot_price * implied_vol * np.sqrt(time_to_expiry))
        vega = spot_price * n_d1 * np.sqrt(time_to_expiry) / 100

        # Time value
        time_value = option_price - intrinsic_value if option_price is not None else None

        return {
            'delta': delta,
            'gamma': gamma,
            'theta': theta,
            'vega': vega,
            'rho': rho,
            'intrinsic_value': intrinsic_value,
            'time_value': time_value,
            'implied_volatility': implied_vol
        }

    except Exception as e:
        logger.error(f"Black-Scholes calculation error: {e}")
        return None


class IBKRGreeksApp(EWrapper, EClient):
    """Extended IBKR app to capture positions and Greeks"""

    def __init__(self):
        EClient.__init__(self, self)
        self.positions = {}
        self.greeks_data = {}
        self.req_id = 1000
        self.position_data_received = False
        self.account_updates = {}
        self.account_update_complete = False
        self.greeks_requests = {}
        self.greeks_complete = set()

    def connectTWS(self, port=4002, host='127.0.0.1'):
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

    def updatePortfolio(self, contract, position, marketPrice, marketValue, averageCost,
                       unrealizedPNL, realizedPNL, accountName):
        """Callback for portfolio updates with market values"""
        key = f"{contract.symbol}_{contract.secType}_{contract.strike}_{contract.right}_{contract.lastTradeDateOrContractMonth}"

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

    def tickOptionComputation(self, reqId, tickType, tickAttrib, impliedVol, delta,
                             optPrice, pvDividend, gamma, vega, theta, undPrice):
        """Callback for option Greeks from IBKR"""
        if reqId not in self.greeks_requests:
            return

        key = self.greeks_requests[reqId]

        # Initialize Greeks data if not exists
        if key not in self.greeks_data:
            self.greeks_data[key] = {}

        # Store Greeks data (IBKR returns -1 or -2 for invalid values)
        if delta is not None and delta > -1:
            self.greeks_data[key]['delta'] = delta
        if gamma is not None and gamma > -1:
            self.greeks_data[key]['gamma'] = gamma
        if vega is not None and vega > -1:
            self.greeks_data[key]['vega'] = vega
        if theta is not None and theta > -1:
            self.greeks_data[key]['theta'] = theta
        if impliedVol is not None and impliedVol > 0:
            self.greeks_data[key]['implied_volatility'] = impliedVol
        if undPrice is not None and undPrice > 0:
            self.greeks_data[key]['underlying_price'] = undPrice
        if optPrice is not None and optPrice > 0:
            self.greeks_data[key]['option_price'] = optPrice

        # Determine data source based on tickType
        if tickType == 13:  # MODEL_OPTION
            self.greeks_data[key]['source'] = 'ibkr_delayed'
        elif tickType in [10, 11, 12]:  # BID_OPTION, ASK_OPTION, LAST_OPTION
            self.greeks_data[key]['source'] = 'ibkr_live'
        else:
            self.greeks_data[key]['source'] = 'ibkr_delayed'

    def error(self, reqId, errorCode, errorString):
        """Callback for error messages"""
        if errorCode not in [2104, 2106, 2158]:
            logger.warning(f"IBKR Error: reqId={reqId}, code={errorCode}, msg={errorString}")

            # Mark Greeks request as complete even on error
            if reqId in self.greeks_requests:
                key = self.greeks_requests[reqId]
                self.greeks_complete.add(key)

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

        timeout = 10
        start_time = time.time()
        while not self.account_update_complete and (time.time() - start_time) < timeout:
            time.sleep(0.1)

        self.reqAccountUpdates(False, account_id)

        # Update positions with account data
        for key, pos in self.positions.items():
            if key in self.account_updates:
                acc_data = self.account_updates[key]
                self.positions[key]['CurrentPrice'] = acc_data.get('MarketPrice')
                self.positions[key]['MarketVal'] = acc_data.get('MarketValue')
                self.positions[key]['UnrealizedPnL'] = acc_data.get('UnrealizedPNL')

    def fetch_greeks_from_ibkr(self, contract, position_key, timeout=15):
        """Request Greeks for a specific contract from IBKR"""
        req_id = self.req_id
        self.req_id += 1

        self.greeks_requests[req_id] = position_key
        self.greeks_complete.discard(position_key)

        # Request market data (includes Greeks for options)
        self.reqMktData(req_id, contract, "", False, False, [])

        # Wait for Greeks data
        start_time = time.time()
        while position_key not in self.greeks_complete and (time.time() - start_time) < timeout:
            # Check if we have received some Greeks data
            if position_key in self.greeks_data and len(self.greeks_data[position_key]) > 2:
                # We have received enough data
                break
            time.sleep(0.5)

        # Cancel market data subscription
        self.cancelMktData(req_id)

        # Mark as complete
        self.greeks_complete.add(position_key)

        return self.greeks_data.get(position_key, {})

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
                'Expiry': pos['Expiry'],
                'Contract': pos['Contract']
            })
        return pd.DataFrame(data)

    def disconnect_tws(self):
        """Disconnect from TWS"""
        if self.isConnected():
            self.disconnect()


def find_vertical_spreads(df):
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

                                spreads.append({
                                    'Symbol': symbol,
                                    'Description': f"{spread_type} {strike1}/{strike2} {expiry}",
                                })

    return pd.DataFrame(spreads)


def match_spread_to_strategy(symbol, strategy_type, strike1, strike2, expiry, db_strategies_df):
    """
    Match a spread to a database strategy record to get trade_id

    Args:
        symbol: Stock symbol
        strategy_type: e.g., "Bull Put", "Bear Call"
        strike1: First strike price
        strike2: Second strike price
        expiry: Expiry date in YYYYMMDD format
        db_strategies_df: DataFrame of strategies from database

    Returns:
        trade_id or None
    """
    try:
        # Parse expiry to match database format
        expiry_date = datetime.datetime.strptime(expiry, '%Y%m%d').date()

        # Determine which strike is buy vs sell based on strategy type
        if "Bull Put" in strategy_type or "Bear Call" in strategy_type:
            # Bull Put: sell higher strike, buy lower strike
            # Bear Call: sell lower strike, buy higher strike
            if "Bull Put" in strategy_type:
                strike_sell = max(strike1, strike2)
                strike_buy = min(strike1, strike2)
            else:  # Bear Call
                strike_sell = min(strike1, strike2)
                strike_buy = max(strike1, strike2)
        else:
            # Default: assume sell is higher for puts, lower for calls
            if "Put" in strategy_type:
                strike_sell = max(strike1, strike2)
                strike_buy = min(strike1, strike2)
            else:
                strike_sell = min(strike1, strike2)
                strike_buy = max(strike1, strike2)

        # Match in database
        matches = db_strategies_df[
            (db_strategies_df['ticker'] == symbol) &
            (db_strategies_df['strike_buy'] == strike_buy) &
            (db_strategies_df['strike_sell'] == strike_sell) &
            (pd.to_datetime(db_strategies_df['options_expiry_date']).dt.date == expiry_date)
        ]

        if not matches.empty:
            return matches.iloc[0]['trade_id']

        return None
    except Exception as e:
        logger.error(f"Error matching spread to strategy: {e}")
        return None


def get_leg_greeks(app, leg_row, risk_free_rate, use_black_scholes=True):
    """Get Greeks for a single option leg"""
    symbol = leg_row['Symbol']
    strike = leg_row['Strike']
    right = leg_row['Right']
    expiry = leg_row['Expiry']
    contract = leg_row['Contract']
    current_price = leg_row['CurrentPrice']

    position_key = f"{symbol}_OPT_{strike}_{right}_{expiry}"

    # Try to fetch Greeks from IBKR
    ibkr_greeks = app.fetch_greeks_from_ibkr(contract, position_key, timeout=15)

    # Parse expiry date
    try:
        expiry_date = datetime.datetime.strptime(expiry, '%Y%m%d')
        time_to_expiry = (expiry_date - datetime.datetime.now()).days / 365.0
    except:
        time_to_expiry = 0.0

    # Determine underlying price
    underlying_price = ibkr_greeks.get('underlying_price')
    if underlying_price is None or underlying_price <= 0:
        if right == 'C':
            underlying_price = strike + (current_price if current_price else 0)
        else:
            underlying_price = strike - (current_price if current_price else 0)

    result = {'underlying_price': underlying_price}

    # Check if we got Greeks from IBKR
    has_ibkr_greeks = ('delta' in ibkr_greeks or 'gamma' in ibkr_greeks or
                      'theta' in ibkr_greeks or 'vega' in ibkr_greeks)

    if has_ibkr_greeks:
        result['delta'] = ibkr_greeks.get('delta')
        result['gamma'] = ibkr_greeks.get('gamma')
        result['theta'] = ibkr_greeks.get('theta')
        result['vega'] = ibkr_greeks.get('vega')
        result['rho'] = None
        result['implied_volatility'] = ibkr_greeks.get('implied_volatility')
        logger.debug(f"  IBKR Greeks for {symbol} {strike}: delta={result['delta']:.4f}")

    # Calculate Black-Scholes Greeks
    if use_black_scholes or not has_ibkr_greeks:
        implied_vol = ibkr_greeks.get('implied_volatility', 0.30)

        bs_greeks = calculate_greeks_bs(
            spot_price=underlying_price,
            strike=strike,
            time_to_expiry=max(time_to_expiry, 0.001),
            risk_free_rate=risk_free_rate,
            implied_vol=implied_vol,
            option_type=right,
            option_price=current_price
        )

        if bs_greeks:
            result['delta_modelled'] = bs_greeks['delta']
            result['gamma_modelled'] = bs_greeks['gamma']
            result['theta_modelled'] = bs_greeks['theta']
            result['vega_modelled'] = bs_greeks['vega']
            result['rho_modelled'] = bs_greeks['rho']
            result['implied_volatility_modelled'] = bs_greeks['implied_volatility']
            result['time_value_modelled'] = bs_greeks['time_value']
            result['intrinsic_value_modelled'] = bs_greeks['intrinsic_value']

            if not has_ibkr_greeks:
                logger.debug(f"  BS Greeks for {symbol} {strike}: delta={bs_greeks['delta']:.4f}")

    time.sleep(0.5)  # Rate limiting
    return result


def capture_greeks_for_positions(app, positions_df, db_strategies_df, use_black_scholes_fallback=True):
    """
    Capture Greeks for all option positions as spreads (both legs on same row)

    Args:
        app: IBKRGreeksApp instance
        positions_df: DataFrame of positions
        db_strategies_df: DataFrame of strategies from database
        use_black_scholes_fallback: Use Black-Scholes if IBKR data unavailable

    Returns:
        DataFrame with Greeks data for spreads (both legs on same row, one row per spread)
    """
    # Get positions dataframe with spreads identified
    spreads_df = find_vertical_spreads(positions_df)

    if spreads_df.empty:
        logger.warning("No vertical spreads found in positions")
        return pd.DataFrame()

    logger.info(f"Processing Greeks for {len(spreads_df)} spreads")

    greeks_records = []
    processed_spreads = set()  # Track to ensure only one row per spread

    for _, spread_row in spreads_df.iterrows():
        description = spread_row['Description']
        symbol = spread_row['Symbol']

        # Parse spread description to get strikes
        parts = description.split()
        strategy_type = ' '.join(parts[:2])  # e.g., "Bull Put"
        strike_info = parts[2]
        expiry = parts[3]

        strikes = strike_info.split('/')
        strike1, strike2 = float(strikes[0]), float(strikes[1])
        right = 'P' if 'Put' in strategy_type else 'C'

        # Create unique key for this spread to avoid duplicates
        spread_key = f"{symbol}_{expiry}_{strike1}_{strike2}_{right}"
        if spread_key in processed_spreads:
            logger.debug(f"Skipping duplicate spread: {description}")
            continue
        processed_spreads.add(spread_key)

        # Match to database strategy to get trade_id
        db_trade_id = match_spread_to_strategy(symbol, strategy_type, strike1, strike2, expiry, db_strategies_df)

        # Find both legs in positions
        leg1_data = positions_df[
            (positions_df['Symbol'] == symbol) &
            (positions_df['Strike'] == strike1) &
            (positions_df['Right'] == right) &
            (positions_df['Expiry'] == expiry)
        ]

        leg2_data = positions_df[
            (positions_df['Symbol'] == symbol) &
            (positions_df['Strike'] == strike2) &
            (positions_df['Right'] == right) &
            (positions_df['Expiry'] == expiry)
        ]

        if leg1_data.empty or leg2_data.empty:
            logger.warning(f"Missing leg data for {description}")
            continue

        leg1 = leg1_data.iloc[0]
        leg2 = leg2_data.iloc[0]

        logger.info(f"Processing spread: {description} (trade_id: {db_trade_id})")

        # Get Greeks for both legs
        leg1_greeks = get_leg_greeks(app, leg1, RISK_FREE_RATE, use_black_scholes_fallback)
        leg2_greeks = get_leg_greeks(app, leg2, RISK_FREE_RATE, use_black_scholes_fallback)

        # Calculate spread-level Greeks (net of both legs)
        spread_greeks = {}
        for greek in ['delta', 'gamma', 'theta', 'vega', 'rho']:
            leg1_val = leg1_greeks.get(greek)
            leg2_val = leg2_greeks.get(greek)
            if leg1_val is not None and leg2_val is not None:
                spread_greeks[f'spread_{greek}'] = leg1_val + leg2_val

            leg1_val_mod = leg1_greeks.get(f'{greek}_modelled')
            leg2_val_mod = leg2_greeks.get(f'{greek}_modelled')
            if leg1_val_mod is not None and leg2_val_mod is not None:
                spread_greeks[f'spread_{greek}_modelled'] = leg1_val_mod + leg2_val_mod

        # Build record with both legs - manually map each field with correct prefix
        greeks_record = {
            'db_trade_id': db_trade_id,
            'spread_symbol': symbol,
            'spread_type': strategy_type,
            'underlying_price': leg1_greeks.get('underlying_price'),

            # Leg 1 data
            'leg1_description': f"{symbol} {expiry} {strike1} {right}",
            'leg1_strike': strike1,
            'leg1_right': right,
            'leg1_expiry': expiry,
            'leg1_current_price': leg1['CurrentPrice'],
            'leg1_position': leg1['Position'],
            'leg1_delta': leg1_greeks.get('delta'),
            'leg1_gamma': leg1_greeks.get('gamma'),
            'leg1_theta': leg1_greeks.get('theta'),
            'leg1_vega': leg1_greeks.get('vega'),
            'leg1_rho': leg1_greeks.get('rho'),
            'leg1_implied_volatility': leg1_greeks.get('implied_volatility'),
            'leg1_delta_modelled': leg1_greeks.get('delta_modelled'),
            'leg1_gamma_modelled': leg1_greeks.get('gamma_modelled'),
            'leg1_theta_modelled': leg1_greeks.get('theta_modelled'),
            'leg1_vega_modelled': leg1_greeks.get('vega_modelled'),
            'leg1_rho_modelled': leg1_greeks.get('rho_modelled'),
            'leg1_implied_volatility_modelled': leg1_greeks.get('implied_volatility_modelled'),
            'leg1_time_value_modelled': leg1_greeks.get('time_value_modelled'),
            'leg1_intrinsic_value_modelled': leg1_greeks.get('intrinsic_value_modelled'),

            # Leg 2 data
            'leg2_description': f"{symbol} {expiry} {strike2} {right}",
            'leg2_strike': strike2,
            'leg2_right': right,
            'leg2_expiry': expiry,
            'leg2_current_price': leg2['CurrentPrice'],
            'leg2_position': leg2['Position'],
            'leg2_delta': leg2_greeks.get('delta'),
            'leg2_gamma': leg2_greeks.get('gamma'),
            'leg2_theta': leg2_greeks.get('theta'),
            'leg2_vega': leg2_greeks.get('vega'),
            'leg2_rho': leg2_greeks.get('rho'),
            'leg2_implied_volatility': leg2_greeks.get('implied_volatility'),
            'leg2_delta_modelled': leg2_greeks.get('delta_modelled'),
            'leg2_gamma_modelled': leg2_greeks.get('gamma_modelled'),
            'leg2_theta_modelled': leg2_greeks.get('theta_modelled'),
            'leg2_vega_modelled': leg2_greeks.get('vega_modelled'),
            'leg2_rho_modelled': leg2_greeks.get('rho_modelled'),
            'leg2_implied_volatility_modelled': leg2_greeks.get('implied_volatility_modelled'),
            'leg2_time_value_modelled': leg2_greeks.get('time_value_modelled'),
            'leg2_intrinsic_value_modelled': leg2_greeks.get('intrinsic_value_modelled'),

            # Spread-level Greeks
            **spread_greeks
        }

        greeks_records.append(greeks_record)

    logger.info(f"Created {len(greeks_records)} unique spread records")
    return pd.DataFrame(greeks_records)


def write_greeks_to_database(greeks_df, pg_creds):
    """
    Write Greeks data to options_greeks table (dual-leg structure)

    Args:
        greeks_df: DataFrame with Greeks data for spreads (both legs on same row)
        pg_creds: PostgreSQL credentials

    Returns:
        Number of records written
    """
    if greeks_df.empty:
        logger.warning("No Greeks data to write")
        return 0

    try:
        conn = psycopg2.connect(
            host=pg_creds['host'],
            port=pg_creds['port'],
            database=pg_creds['database'],
            user=pg_creds['user'],
            password=pg_creds['password']
        )

        cursor = conn.cursor()
        records_written = 0

        for _, row in greeks_df.iterrows():
            # Look up position_id from ibkr_positions (if it exists)
            cursor.execute("""
                SELECT id FROM ibkr_positions
                WHERE ibkr_symbol = %s
                LIMIT 1
            """, (row['spread_symbol'],))

            result = cursor.fetchone()
            position_id = result[0] if result else None

            # Insert Greeks data with both legs on same row
            insert_sql = """
            INSERT INTO options_greeks (
                position_id, db_trade_id, snapshot_timestamp,
                spread_symbol, spread_type,

                leg1_description, leg1_strike, leg1_right, leg1_expiry,
                leg1_current_price, leg1_position,
                leg1_delta, leg1_gamma, leg1_theta, leg1_vega, leg1_rho, leg1_implied_volatility,
                leg1_delta_modelled, leg1_gamma_modelled, leg1_theta_modelled,
                leg1_vega_modelled, leg1_rho_modelled, leg1_implied_volatility_modelled,
                leg1_time_value_modelled, leg1_intrinsic_value_modelled,

                leg2_description, leg2_strike, leg2_right, leg2_expiry,
                leg2_current_price, leg2_position,
                leg2_delta, leg2_gamma, leg2_theta, leg2_vega, leg2_rho, leg2_implied_volatility,
                leg2_delta_modelled, leg2_gamma_modelled, leg2_theta_modelled,
                leg2_vega_modelled, leg2_rho_modelled, leg2_implied_volatility_modelled,
                leg2_time_value_modelled, leg2_intrinsic_value_modelled,

                spread_delta, spread_gamma, spread_theta, spread_vega, spread_rho,
                spread_delta_modelled, spread_gamma_modelled, spread_theta_modelled,
                spread_vega_modelled, spread_rho_modelled,

                underlying_price
            ) VALUES (
                %s, %s, CURRENT_TIMESTAMP,
                %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s
            )
            """

            cursor.execute(insert_sql, (
                position_id,
                row.get('db_trade_id'),
                row.get('spread_symbol'),
                row.get('spread_type'),

                # Leg 1
                row.get('leg1_description'),
                row.get('leg1_strike'),
                row.get('leg1_right'),
                row.get('leg1_expiry'),
                row.get('leg1_current_price'),
                row.get('leg1_position'),
                row.get('leg1_delta'),
                row.get('leg1_gamma'),
                row.get('leg1_theta'),
                row.get('leg1_vega'),
                row.get('leg1_rho'),
                row.get('leg1_implied_volatility'),
                row.get('leg1_delta_modelled'),
                row.get('leg1_gamma_modelled'),
                row.get('leg1_theta_modelled'),
                row.get('leg1_vega_modelled'),
                row.get('leg1_rho_modelled'),
                row.get('leg1_implied_volatility_modelled'),
                row.get('leg1_time_value_modelled'),
                row.get('leg1_intrinsic_value_modelled'),

                # Leg 2
                row.get('leg2_description'),
                row.get('leg2_strike'),
                row.get('leg2_right'),
                row.get('leg2_expiry'),
                row.get('leg2_current_price'),
                row.get('leg2_position'),
                row.get('leg2_delta'),
                row.get('leg2_gamma'),
                row.get('leg2_theta'),
                row.get('leg2_vega'),
                row.get('leg2_rho'),
                row.get('leg2_implied_volatility'),
                row.get('leg2_delta_modelled'),
                row.get('leg2_gamma_modelled'),
                row.get('leg2_theta_modelled'),
                row.get('leg2_vega_modelled'),
                row.get('leg2_rho_modelled'),
                row.get('leg2_implied_volatility_modelled'),
                row.get('leg2_time_value_modelled'),
                row.get('leg2_intrinsic_value_modelled'),

                # Spread-level Greeks
                row.get('spread_delta'),
                row.get('spread_gamma'),
                row.get('spread_theta'),
                row.get('spread_vega'),
                row.get('spread_rho'),
                row.get('spread_delta_modelled'),
                row.get('spread_gamma_modelled'),
                row.get('spread_theta_modelled'),
                row.get('spread_vega_modelled'),
                row.get('spread_rho_modelled'),

                row.get('underlying_price')
            ))
            records_written += 1

        conn.commit()
        cursor.close()
        conn.close()

        logger.info(f"Successfully wrote {records_written} Greeks records to database")
        return records_written

    except Exception as e:
        logger.error(f"Failed to write Greeks to database: {e}")
        import traceback
        traceback.print_exc()
        return 0


def get_database_credentials():
    """Load database credentials from config file"""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config_path = os.path.join(project_root, 'config')
    credentials_file = os.path.join(config_path, 'credentials.json')

    with open(credentials_file, 'r') as f:
        creds = json.load(f)

    return creds['database']['postgresql']


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


def run_greeks_capture(port=4002, account_id="DU9233079", **context):
    """
    Main function to capture options Greeks

    Args:
        port (int): IB Gateway port (default: 4002 for paper trading)
        account_id (str): IBKR account ID
        **context: Airflow context (ignored)

    Returns:
        dict: Summary of Greeks capture operation
    """
    logger.info("="*80)
    logger.info("Starting options Greeks capture")
    logger.info("="*80)

    try:
        # Load database credentials
        pg_creds = get_database_credentials()

        # Connect to IBKR
        app = IBKRGreeksApp()
        connected = app.connectTWS(port=port)

        if not connected:
            logger.error("Failed to connect to IB Gateway - gateway may not be running")
            return {
                'success': False,
                'error': 'Gateway connection failed',
                'greeks_captured': 0
            }

        # Get positions
        logger.info("Fetching positions...")
        num_positions = app.get_positions_data()
        logger.info(f"Retrieved {num_positions} positions")

        # Get account updates
        app.get_account_updates(account_id)

        # Get positions DataFrame
        positions_df = app.get_positions_dataframe()

        if positions_df.empty:
            logger.warning("No positions found")
            app.disconnect_tws()
            return {
                'success': True,
                'greeks_captured': 0,
                'positions_retrieved': 0
            }

        # Get database strategies
        db_strategies_df = get_option_strategies(pg_creds)
        logger.info(f"Retrieved {len(db_strategies_df)} strategies from database")

        # Capture Greeks
        logger.info("Capturing Greeks for option spreads...")
        greeks_df = capture_greeks_for_positions(app, positions_df, db_strategies_df)

        # Write to database
        records_written = write_greeks_to_database(greeks_df, pg_creds)

        # Disconnect
        app.disconnect_tws()

        logger.info(f"Greeks capture completed: {records_written} spreads captured")
        return {
            'success': True,
            'greeks_captured': records_written,
            'positions_retrieved': num_positions
        }

    except Exception as e:
        logger.error(f"Greeks capture failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e),
            'greeks_captured': 0
        }
