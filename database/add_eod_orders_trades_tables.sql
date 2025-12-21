-- SQL Migration: Create EOD Orders and Trades tables
-- These tables store end-of-day orders and trades from IBKR API
-- Data collected via reqCompletedOrders() and reqExecutions()

-- ============================================================================
-- EOD_ORDERS TABLE
-- ============================================================================
-- Stores completed orders (filled or unfilled) from IBKR
-- Source: completedOrder() callback from IBKR API
-- One row per spread order

CREATE TABLE IF NOT EXISTS eod_orders (
    id SERIAL PRIMARY KEY,

    -- Order Identification
    order_id INTEGER NOT NULL,
    perm_id INTEGER,
    order_ref TEXT,

    -- Spread Information
    spread_name TEXT NOT NULL,
    bot_leg TEXT NOT NULL,
    sld_leg TEXT NOT NULL,

    -- Order Details
    key_action TEXT NOT NULL,  -- BUY or SELL
    order_type TEXT NOT NULL,  -- LMT, MKT, etc.
    limit_price REAL,
    total_quantity INTEGER,
    filled_quantity INTEGER,
    remaining_quantity INTEGER,
    quantity_display TEXT,  -- e.g., "0/1" or "1/1"

    -- Order Status
    status TEXT,  -- Filled, Cancelled, PreSubmitted, Submitted, etc.
    completed_time TIMESTAMP,
    completed_status TEXT,

    -- Contract Details
    underlying_symbol TEXT NOT NULL,
    sec_type TEXT,  -- BAG for spreads
    currency TEXT DEFAULT 'USD',
    exchange TEXT,

    -- BOT Leg Details
    bot_leg_conid INTEGER,
    bot_leg_strike REAL,
    bot_leg_right TEXT,  -- P or C
    bot_leg_expiry TEXT,
    bot_leg_symbol TEXT,

    -- SLD Leg Details
    sld_leg_conid INTEGER,
    sld_leg_strike REAL,
    sld_leg_right TEXT,  -- P or C
    sld_leg_expiry TEXT,
    sld_leg_symbol TEXT,

    -- Financial Information
    commission REAL,
    commission_currency TEXT,

    -- Metadata
    collection_date DATE NOT NULL,
    collection_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Ensure one order per collection date (use perm_id since order_id can be 0)
    UNIQUE(perm_id, collection_date)
);

-- ============================================================================
-- EOD_TRADES TABLE
-- ============================================================================
-- Stores executed trades (filled orders only) from IBKR
-- Source: execDetails() callback from IBKR API
-- One row per spread execution

CREATE TABLE IF NOT EXISTS eod_trades (
    id SERIAL PRIMARY KEY,

    -- Execution Identification
    exec_id TEXT NOT NULL UNIQUE,
    order_id INTEGER NOT NULL,
    perm_id INTEGER,

    -- Spread Information
    spread_name TEXT NOT NULL,
    bot_leg TEXT NOT NULL,
    sld_leg TEXT NOT NULL,

    -- Trade Details
    spread_action TEXT NOT NULL,  -- BOT or SLD
    spread_price REAL NOT NULL,  -- Net credit/debit
    buy_leg_price REAL NOT NULL,
    sell_leg_price REAL NOT NULL,

    -- Execution Details
    execution_time TIMESTAMP NOT NULL,
    quantity INTEGER,
    cum_qty INTEGER,
    avg_price REAL,

    -- Contract Details
    underlying_symbol TEXT NOT NULL,
    sec_type TEXT,  -- BAG for spreads
    currency TEXT DEFAULT 'USD',
    exchange TEXT,

    -- BOT Leg Details
    bot_leg_conid INTEGER,
    bot_leg_strike REAL,
    bot_leg_right TEXT,  -- P or C
    bot_leg_expiry TEXT,
    bot_leg_symbol TEXT,
    bot_leg_exec_price REAL,
    bot_leg_exec_time TIMESTAMP,
    bot_leg_exec_id TEXT,

    -- SLD Leg Details
    sld_leg_conid INTEGER,
    sld_leg_strike REAL,
    sld_leg_right TEXT,  -- P or C
    sld_leg_expiry TEXT,
    sld_leg_symbol TEXT,
    sld_leg_exec_price REAL,
    sld_leg_exec_time TIMESTAMP,
    sld_leg_exec_id TEXT,

    -- Financial Information
    commission REAL,
    commission_currency TEXT,

    -- Account Information
    account_number TEXT,

    -- Metadata
    collection_date DATE NOT NULL,
    collection_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Link to orders table
    eod_order_id INTEGER REFERENCES eod_orders(id) ON DELETE SET NULL
);

-- ============================================================================
-- INDEXES
-- ============================================================================

-- EOD_ORDERS indexes
CREATE INDEX IF NOT EXISTS idx_eod_orders_order_id ON eod_orders(order_id);
CREATE INDEX IF NOT EXISTS idx_eod_orders_perm_id ON eod_orders(perm_id);
CREATE INDEX IF NOT EXISTS idx_eod_orders_collection_date ON eod_orders(collection_date);
CREATE INDEX IF NOT EXISTS idx_eod_orders_status ON eod_orders(status);
CREATE INDEX IF NOT EXISTS idx_eod_orders_underlying_symbol ON eod_orders(underlying_symbol);
CREATE INDEX IF NOT EXISTS idx_eod_orders_completed_time ON eod_orders(completed_time);

-- EOD_TRADES indexes
CREATE INDEX IF NOT EXISTS idx_eod_trades_order_id ON eod_trades(order_id);
CREATE INDEX IF NOT EXISTS idx_eod_trades_perm_id ON eod_trades(perm_id);
CREATE INDEX IF NOT EXISTS idx_eod_trades_exec_id ON eod_trades(exec_id);
CREATE INDEX IF NOT EXISTS idx_eod_trades_collection_date ON eod_trades(collection_date);
CREATE INDEX IF NOT EXISTS idx_eod_trades_execution_time ON eod_trades(execution_time);
CREATE INDEX IF NOT EXISTS idx_eod_trades_underlying_symbol ON eod_trades(underlying_symbol);
CREATE INDEX IF NOT EXISTS idx_eod_trades_eod_order_id ON eod_trades(eod_order_id);

-- ============================================================================
-- COMMENTS
-- ============================================================================

-- EOD_ORDERS table comments
COMMENT ON TABLE eod_orders IS 'End-of-day orders from IBKR API (completed orders including filled and unfilled)';
COMMENT ON COLUMN eod_orders.order_id IS 'IBKR order ID (may not be unique across accounts)';
COMMENT ON COLUMN eod_orders.perm_id IS 'Permanent order ID from IBKR (use for reliable record keeping)';
COMMENT ON COLUMN eod_orders.spread_name IS 'Descriptive spread name (e.g., "TQQQ Bull Spread")';
COMMENT ON COLUMN eod_orders.bot_leg IS 'Bought leg description (e.g., "Nov28''25 85 PUT")';
COMMENT ON COLUMN eod_orders.sld_leg IS 'Sold leg description (e.g., "Nov28''25 96 PUT")';
COMMENT ON COLUMN eod_orders.key_action IS 'Order action: BUY or SELL';
COMMENT ON COLUMN eod_orders.order_type IS 'Order type: LMT, MKT, etc.';
COMMENT ON COLUMN eod_orders.quantity_display IS 'Filled/Total quantity display (e.g., "0/1" or "1/1")';
COMMENT ON COLUMN eod_orders.collection_date IS 'Date when this data was collected (trading date)';
COMMENT ON COLUMN eod_orders.bot_leg_conid IS 'IBKR contract ID for bought leg';
COMMENT ON COLUMN eod_orders.sld_leg_conid IS 'IBKR contract ID for sold leg';

-- EOD_TRADES table comments
COMMENT ON TABLE eod_trades IS 'End-of-day executed trades from IBKR API (filled orders only)';
COMMENT ON COLUMN eod_trades.exec_id IS 'Unique execution ID from IBKR';
COMMENT ON COLUMN eod_trades.order_id IS 'IBKR order ID linking to eod_orders';
COMMENT ON COLUMN eod_trades.perm_id IS 'Permanent order ID from IBKR';
COMMENT ON COLUMN eod_trades.spread_name IS 'Descriptive spread name (e.g., "TSM Nov28 270/260 Bull Put")';
COMMENT ON COLUMN eod_trades.bot_leg IS 'Bought leg description (e.g., "TSM Nov28''25 260 PUT")';
COMMENT ON COLUMN eod_trades.sld_leg IS 'Sold leg description (e.g., "TSM Nov28''25 270 PUT")';
COMMENT ON COLUMN eod_trades.spread_action IS 'Trade action: BOT (bought) or SLD (sold)';
COMMENT ON COLUMN eod_trades.spread_price IS 'Net spread price (credit/debit)';
COMMENT ON COLUMN eod_trades.buy_leg_price IS 'Execution price for bought leg';
COMMENT ON COLUMN eod_trades.sell_leg_price IS 'Execution price for sold leg';
COMMENT ON COLUMN eod_trades.execution_time IS 'When the trade was executed';
COMMENT ON COLUMN eod_trades.collection_date IS 'Date when this data was collected (trading date)';
COMMENT ON COLUMN eod_trades.eod_order_id IS 'Foreign key to eod_orders table';
COMMENT ON COLUMN eod_trades.bot_leg_exec_id IS 'Individual execution ID for bought leg';
COMMENT ON COLUMN eod_trades.sld_leg_exec_id IS 'Individual execution ID for sold leg';
