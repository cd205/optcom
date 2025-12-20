-- Migration: Update eod_orders constraint to use perm_id instead of order_id
--
-- Context: When orders are placed outside the API session (via TWS/IB Gateway UI),
-- IBKR returns order_id=0 for those orders when queried via API. This causes
-- collisions in the UNIQUE constraint if multiple such orders exist on the same day.
--
-- Solution: Use perm_id (permanent order ID) which is always unique across orders.
--
-- Date: 2025-11-25

-- Drop the old constraint
ALTER TABLE eod_orders DROP CONSTRAINT IF EXISTS eod_orders_order_id_collection_date_key;

-- Add new constraint using perm_id
ALTER TABLE eod_orders ADD CONSTRAINT eod_orders_perm_id_collection_date_key
    UNIQUE (perm_id, collection_date);

-- Verify the constraint was added
SELECT conname, contype, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'eod_orders'::regclass
  AND conname = 'eod_orders_perm_id_collection_date_key';
