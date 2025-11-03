from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
import threading
import time
import queue
import logging
import pandas as pd
from datetime import datetime, timedelta

# Set up logging
logger = logging.getLogger(__name__)

class IBAPIWrapper(EWrapper):
    """
    Wrapper class for the IB API callback functions
    """
    def __init__(self):
        EWrapper.__init__(self)
        self.data_queue = queue.Queue()
        self.next_req_id = 1
        self.next_order_id = None
        self.contract_details = {}
        self.historical_data = {}
        self.market_data = {}
        self.errors = {}
        self.req_id_to_ticker = {}  # Maps request IDs to ticker symbols

    def nextValidId(self, orderId: int):
        """
        Callback for the next valid order ID
        """
        super().nextValidId(orderId)
        self.next_order_id = orderId
        logger.debug(f"Next Valid Order ID: {orderId}")
        self.data_queue.put(("connection_confirmed", None))
    
    def error(self, reqId: int, errorCode: int, errorString: str, *args):
        """
        Callback for error messages - modified to handle variable arguments
        """
        # Call parent with appropriate number of arguments
        if len(args) > 0:
            super().error(reqId, errorCode, errorString, *args)
        else:
            super().error(reqId, errorCode, errorString)
            
        self.errors[reqId] = (errorCode, errorString)
        logger.error(f"Error {errorCode} for request {reqId}: {errorString}")
        self.data_queue.put(("error", (reqId, errorCode, errorString)))
    
    def contractDetails(self, reqId: int, contractDetails):
        """
        Callback for contract details
        """
        super().contractDetails(reqId, contractDetails)
        if reqId not in self.contract_details:
            self.contract_details[reqId] = []
        self.contract_details[reqId].append(contractDetails)
    
    def contractDetailsEnd(self, reqId: int):
        """
        Callback for end of contract details
        """
        super().contractDetailsEnd(reqId)
        logger.debug(f"Contract details request {reqId} completed")
        self.data_queue.put(("contract_details", (reqId, self.contract_details.get(reqId, []))))
    
    def historicalData(self, reqId: int, bar):
        """
        Callback for historical data bars
        """
        super().historicalData(reqId, bar)
        if reqId not in self.historical_data:
            self.historical_data[reqId] = []
        self.historical_data[reqId].append(bar)
        
        # Also notify about the bar
        ticker = self.req_id_to_ticker.get(reqId, f"Unknown-{reqId}")
        self.data_queue.put(("historical_bar", (ticker, reqId, bar)))
    
    def historicalDataEnd(self, reqId: int, start: str, end: str):
        """
        Callback for end of historical data
        """
        super().historicalDataEnd(reqId, start, end)
        logger.debug(f"Historical data request {reqId} completed")
        ticker = self.req_id_to_ticker.get(reqId, f"Unknown-{reqId}")
        self.data_queue.put(("historical_data_end", (ticker, reqId)))
    
    def tickPrice(self, reqId: int, tickType: int, price: float, attrib):
        """
        Callback for price updates
        """
        super().tickPrice(reqId, tickType, price, attrib)
        if reqId not in self.market_data:
            self.market_data[reqId] = {}
            
        # Store price based on tick type
        # 1 = bid, 2 = ask, 4 = last, 6 = high, 7 = low, 9 = close
        self.market_data[reqId][tickType] = price
        
        # Get ticker symbol
        ticker = self.req_id_to_ticker.get(reqId, f"Unknown-{reqId}")
        
        # Notify about the price update
        self.data_queue.put(("tick_price", (ticker, reqId, tickType, price)))
        
        # If this is a last price or close price, also notify separately
        if tickType == 4 or tickType == 9:  # Last or close price
            self.data_queue.put(("market_data", (ticker, price, tickType)))
            logger.debug(f"Received price for {ticker}: ${price} (type: {tickType})")
    
    def getNextRequestId(self):
        """
        Get the next available request ID
        """
        req_id = self.next_req_id
        self.next_req_id += 1
        return req_id


class IBAPIClient(EClient):
    """
    Client class to connect to IB API
    """
    def __init__(self, wrapper):
        EClient.__init__(self, wrapper)
        self._lock = threading.Lock()  # Lock for thread safety


class IBKRDataProvider:
    """
    Data provider using the IB API
    """
    def __init__(self, host='127.0.0.1', port=4002, client_id=1):
        """
        Initialize the IBKR data provider
        
        Parameters:
        host (str): IB Gateway host (default: 127.0.0.1)
        port (int): IB Gateway port (default: 4002 for paper trading, 4001 for live)
        client_id (int): Client ID for this connection
        """
        self.host = host
        self.port = port
        self.client_id = client_id
        self.wrapper = IBAPIWrapper()
        self.client = IBAPIClient(self.wrapper)
        self.connected = False
        self.prices = {}  # Cache for latest prices
        self.close_prices = {}  # Cache for close prices
        self.contracts = {}  # Cache for contracts
        
        # Create a thread for the client to run in
        self.api_thread = None
    
    def _run_client(self):
        """
        Run the client in a separate thread
        """
        try:
            self.client.run()
        except Exception as e:
            logger.error(f"Error in client thread: {str(e)}")
    
    def connect(self, max_retries=3):
        """
        Connect to the IB API with retry logic
        
        Parameters:
        max_retries (int): Maximum number of connection attempts
        
        Returns:
        bool: True if connected successfully, False otherwise
        """
        if self.connected:
            logger.warning("Already connected to IBKR")
            return True
        
        for attempt in range(max_retries):
            logger.info(f"Connecting to IB Gateway at {self.host}:{self.port} (attempt {attempt + 1}/{max_retries})")
            
            if self._attempt_connection():
                return True
            
            if attempt < max_retries - 1:
                wait_time = 5 * (attempt + 1)  # Exponential backoff
                logger.warning(f"Connection attempt {attempt + 1} failed, retrying in {wait_time} seconds...")
                time.sleep(wait_time)
        
        logger.error(f"Failed to connect after {max_retries} attempts")
        return False
    
    def _attempt_connection(self):
        """
        Single connection attempt
        
        Returns:
        bool: True if connected successfully, False otherwise
        """
        # Connect to the API
        try:
            self.client.connect(self.host, self.port, self.client_id)
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            return False
        
        # Start a thread to process messages
        self.api_thread = threading.Thread(target=self._run_client, daemon=True)
        self.api_thread.start()
        
        # Wait for connection confirmation - increased timeout for 2FA
        timeout = 30  # seconds - increased from 10 to handle 2FA delays
        start_time = time.time()
        connected = False
        
        while time.time() - start_time < timeout:
            try:
                msg_type, msg_data = self.wrapper.data_queue.get(timeout=2)
                
                if msg_type == "connection_confirmed":
                    connected = True
                    break
                elif msg_type == "error":
                    req_id, error_code, error_msg = msg_data
                    if error_code == 502:  # Connection refused
                        logger.error("Connection refused. Is IB Gateway running?")
                        return False
                    elif error_code == 501:  # Already connected
                        connected = True
                        break
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error waiting for connection: {str(e)}")
        
        if connected:
            logger.info("Connected to IBKR")
            self.connected = True
            
            # Set market data type to delayed if needed
            # 1 = Live, 3 = Delayed
            self.client.reqMarketDataType(3)  # Uncomment if you need delayed data
            
            return True
        else:
            logger.error("Failed to connect to IBKR within timeout")
            try:
                self.client.disconnect()
            except:
                pass
            return False
    
    def disconnect(self):
        """
        Disconnect from the IB API
        """
        if self.connected:
            logger.info("Disconnecting from IBKR")
            try:
                self.client.disconnect()
                self.connected = False
            except Exception as e:
                logger.error(f"Error disconnecting: {str(e)}")
            
            # Wait for the thread to end
            if self.api_thread and self.api_thread.is_alive():
                try:
                    self.api_thread.join(timeout=2)
                except Exception as e:
                    logger.error(f"Error joining thread: {str(e)}")
    
    def create_contract(self, ticker):
        """
        Create a stock contract for a ticker
        
        Parameters:
        ticker (str): Stock ticker symbol
        
        Returns:
        Contract: IB contract object
        """
        if ticker in self.contracts:
            return self.contracts[ticker]
            
        # Create new contract
        contract = Contract()
        contract.symbol = ticker
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"
        
        self.contracts[ticker] = contract
        return contract
    
    def get_last_close_price(self, ticker):
        """
        Get the last close price for a ticker (for previous day)
        
        Parameters:
        ticker (str): Stock ticker symbol
        
        Returns:
        float: Last close price or None if unavailable
        """
        if not self.connected:
            logger.error("Not connected to IBKR")
            return None
        
        # Check if we already have this in cache
        if ticker in self.close_prices:
            logger.info(f"Using cached close price for {ticker}: ${self.close_prices[ticker]}")
            return self.close_prices[ticker]
            
        # Create contract
        contract = self.create_contract(ticker)
        
        # Request historical data for 1 day bar
        req_id = self.wrapper.getNextRequestId()
        self.wrapper.req_id_to_ticker[req_id] = ticker
        
        # Clear any existing data
        if req_id in self.wrapper.historical_data:
            del self.wrapper.historical_data[req_id]
        
        # Variables to track data receipt
        got_close_price = False
        close_price = None
        
        try:
            # Request just 1 day of daily bar data
            self.client.reqHistoricalData(
                req_id,
                contract,
                "",  # End date/time (empty for now)
                "2 D",  # Duration - 2 days to ensure we get yesterday
                "1 day",  # Bar size - daily bars
                "TRADES",  # What to show
                1,  # Use RTH (regular trading hours)
                1,  # Format dates as strings
                False,  # Keep up to date
                []  # Chart options
            )
            
            # Wait for data
            timeout = 5  # seconds
            start_time = time.time()
            
            while time.time() - start_time < timeout and not got_close_price:
                try:
                    msg_type, msg_data = self.wrapper.data_queue.get(timeout=1)
                    
                    if msg_type == "historical_bar" and msg_data[0] == ticker:
                        # We got a historical bar
                        bar = msg_data[2]
                        close_price = bar.close
                        logger.info(f"Got close price for {ticker}: ${close_price}")
                        got_close_price = True
                        
                    elif msg_type == "historical_data_end" and msg_data[0] == ticker:
                        # Historical data request complete
                        break
                        
                    elif msg_type == "error" and msg_data[0] == req_id:
                        logger.error(f"Error getting close price for {ticker}: {msg_data[2]}")
                        break
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"Error processing historical data: {str(e)}")
            
            if got_close_price:
                # Cache the close price
                self.close_prices[ticker] = close_price
                return close_price
            else:
                logger.warning(f"No close price available for {ticker}")
                return None
                
        except Exception as e:
            logger.error(f"Error requesting historical data for {ticker}: {str(e)}")
            return None
    
    def get_latest_price(self, ticker):
        """
        Get the latest price for a ticker.
        If live data is not available, falls back to last close price.
        
        Parameters:
        ticker (str): Stock ticker symbol
        
        Returns:
        float: Latest price or close price, or None if nothing available
        """
        if not self.connected:
            logger.error("Not connected to IBKR")
            return None
            
        # Try to get live price first
        live_price = self._get_live_price(ticker)
        
        # If that fails, try to get close price
        if live_price is None:
            logger.info(f"Live price not available for {ticker}, trying close price")
            close_price = self.get_last_close_price(ticker)
            
            if close_price is not None:
                logger.info(f"Using close price for {ticker}: ${close_price}")
                return close_price
            else:
                logger.warning(f"No price data available for {ticker}")
                return None
        else:
            return live_price
    
    def _get_live_price(self, ticker):
        """
        Get the latest live price for a ticker
        
        Parameters:
        ticker (str): Stock ticker symbol
        
        Returns:
        float: Latest price or None if unavailable
        """
        # Create contract
        contract = self.create_contract(ticker)
        
        # Request market data
        req_id = self.wrapper.getNextRequestId()
        self.wrapper.req_id_to_ticker[req_id] = ticker
        
        # Clear existing data for this request
        if req_id in self.wrapper.market_data:
            del self.wrapper.market_data[req_id]
        
        try:
            # Request market data
            self.client.reqMktData(req_id, contract, "", False, False, [])
            
            # Wait for price data - increased timeout for better reliability
            timeout = 12  # seconds - increased from 3 to handle delays
            start_time = time.time()
            
            received_data = False
            
            while time.time() - start_time < timeout and not received_data:
                try:
                    msg_type, msg_data = self.wrapper.data_queue.get(timeout=0.5)
                    
                    if msg_type == "tick_price" and msg_data[0] == ticker:
                        tick_type = msg_data[2]
                        price = msg_data[3]
                        
                        # Store in market data
                        if req_id not in self.wrapper.market_data:
                            self.wrapper.market_data[req_id] = {}
                        self.wrapper.market_data[req_id][tick_type] = price
                        
                        # 4 = Last price, 9 = Close price
                        if tick_type == 4:  # If we get a last price, we're done
                            received_data = True
                    
                    elif msg_type == "error" and msg_data[0] == req_id:
                        # Error receiving market data
                        error_code = msg_data[1]
                        if error_code == 504:  # Not connected
                            logger.error(f"Not connected for market data request: {ticker}")
                            break
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"Error processing market data: {str(e)}")
            
            # Cancel market data to avoid hitting limits
            try:
                self.client.cancelMktData(req_id)
            except:
                # If we're already disconnected, this will fail
                pass
            
            # Check if we have market data
            if req_id in self.wrapper.market_data:
                # Prioritize data types: Last (4), Close (9), Ask (2), Bid (1)
                for tick_type in [4, 9, 2, 1]:
                    if tick_type in self.wrapper.market_data[req_id]:
                        price = self.wrapper.market_data[req_id][tick_type]
                        logger.info(f"Got price for {ticker}: ${price} (type: {tick_type})")
                        
                        # Cache the price
                        self.prices[ticker] = price
                        return price
            
            # If we get here, we didn't get any price data
            # Try fallback to close price
            logger.warning(f"Live price timeout for {ticker}, trying fallback to close price")
            return self.get_last_close_price(ticker)
            
        except Exception as e:
            logger.error(f"Error requesting market data for {ticker}: {str(e)}")
            return None
    
    def get_historical_data(self, ticker, duration='1 D', bar_size='1 min', what_to_show='TRADES'):
        """
        Get historical data for a ticker
        
        Parameters:
        ticker (str): Stock ticker symbol
        duration (str): Duration string (e.g., '1 D', '1 W', '1 M')
        bar_size (str): Bar size (e.g., '1 min', '5 mins', '1 hour', '1 day')
        what_to_show (str): Type of data to show
        
        Returns:
        pandas.DataFrame: Historical data or None if error
        """
        if not self.connected:
            logger.error("Not connected to IBKR")
            return None
            
        # Create contract
        contract = self.create_contract(ticker)
        
        # Request historical data
        req_id = self.wrapper.getNextRequestId()
        self.wrapper.req_id_to_ticker[req_id] = ticker
        
        # Clear existing historical data for this request
        if req_id in self.wrapper.historical_data:
            del self.wrapper.historical_data[req_id]
        
        try:
            # Request historical data
            self.client.reqHistoricalData(
                req_id,
                contract,
                "",  # End date/time (empty for now)
                duration,  # Duration
                bar_size,  # Bar size
                what_to_show,  # What to show
                1,  # Use RTH
                1,  # Format dates as strings
                False,  # Keep up to date
                []  # Chart options
            )
            
            # Wait for historical data
            timeout = 10  # seconds
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                try:
                    msg_type, msg_data = self.wrapper.data_queue.get(timeout=1)
                    
                    if msg_type == "historical_data_end" and msg_data[0] == ticker:
                        # Historical data request complete
                        bars = self.wrapper.historical_data.get(req_id, [])
                        
                        # Convert bars to DataFrame
                        if bars:
                            data = []
                            for bar in bars:
                                data.append({
                                    'date': bar.date,
                                    'open': bar.open,
                                    'high': bar.high,
                                    'low': bar.low,
                                    'close': bar.close,
                                    'volume': bar.volume,
                                    'wap': bar.wap,
                                    'count': bar.barCount
                                })
                            
                            df = pd.DataFrame(data)
                            return df
                        else:
                            logger.warning(f"No historical data for {ticker}")
                            return None
                            
                    elif msg_type == "error" and msg_data[0] == req_id:
                        logger.error(f"Error getting historical data for {ticker}: {msg_data[2]}")
                        return None
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"Error processing historical data: {str(e)}")
            
            logger.warning(f"Timeout waiting for historical data for {ticker}")
            return None
            
        except Exception as e:
            logger.error(f"Error requesting historical data for {ticker}: {str(e)}")
            return None


# Example usage
if __name__ == "__main__":
    # Set up logging for the example
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Create data provider
    ibkr = IBKRDataProvider(port=4002)  # Use 4002 for IB Gateway paper trading, 4001 for live
    
    try:
        # Connect to IBKR
        if ibkr.connect():
            # Get price for some stocks
            tickers = ['AAPL', 'MSFT', 'GOOGL']
            
            print("\nCurrent prices:")
            for ticker in tickers:
                price = ibkr.get_latest_price(ticker)
                if price is not None:
                    print(f"{ticker}: ${price:.2f}")
                else:
                    print(f"{ticker}: Not available")
            
            # Get historical data for one stock
            print("\nHistorical data for AAPL:")
            hist_data = ibkr.get_historical_data('AAPL', duration='1 D', bar_size='1 hour')
            if hist_data is not None:
                print(hist_data.head())
        else:
            print("Failed to connect to IBKR")
    
    finally:
        # Disconnect
        ibkr.disconnect()