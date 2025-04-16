#!/usr/bin/env python3
import time
import logging
import datetime

# Import your modules
import price_monitor
import vertical_spread_order

def main():
    # Configuration
    CYCLE_WAIT_SECONDS = 60
    DB_PATH = '../database/option_strategies.db'
    IBKR_HOST = '127.0.0.1'
    IBKR_PORT = 7497
    ALLOW_MARKET_CLOSED_ORDERS = True  # Allow orders even when the market is closed

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger()

    # Print startup message
    logger.info("=" * 80)
    logger.info("Starting automated trading system")
    logger.info("=" * 80)

    cycle = 1

    try:
        while True:  # Run indefinitely until the user stops the process
            logger.info(f"Starting cycle {cycle}")

            # Step 1: Run price monitor
            logger.info("Starting price monitor...")
            try:
                price_monitor.monitor_prices(
                    db_path=DB_PATH,
                    ibkr_host=IBKR_HOST,
                    ibkr_port=IBKR_PORT
                )
                logger.info("Price monitor completed successfully")
            except Exception as e:
                logger.error(f"Error running price monitor: {str(e)}")

            # Step 2: Run vertical spread order
            logger.info("Starting vertical spread order...")
            try:
                vertical_spread_order.run_trading_app(
                    db_path=DB_PATH,
                    target_date=datetime.datetime.now().strftime('%Y-%m-%d'),
                    ibkr_host=IBKR_HOST,
                    ibkr_port=IBKR_PORT,
                    allow_market_closed=ALLOW_MARKET_CLOSED_ORDERS
                )
                logger.info("Vertical spread order completed successfully")
            except Exception as e:
                logger.error(f"Error placing vertical spread order: {str(e)}")

            # Wait before starting the next cycle
            logger.info(f"Waiting {CYCLE_WAIT_SECONDS} seconds until next cycle...")
            time.sleep(CYCLE_WAIT_SECONDS)
            
            # Increment cycle counter
            cycle += 1

    except KeyboardInterrupt:
        logger.info("Automated trading system stopped by user")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
    finally:
        logger.info("Automated trading system completed")

if __name__ == "__main__":
    main()
