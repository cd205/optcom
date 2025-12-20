#!/usr/bin/env python3
"""
Verify EOD Data Collection

Checks that EOD data was successfully collected and provides summary statistics.

Usage:
    python verify_eod_data.py [--date YYYY-MM-DD] [--days N]
"""

import sys
import os
import argparse
from datetime import datetime, date, timedelta

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from database.database_config import DatabaseConnection


def verify_single_date(collection_date):
    """
    Verify EOD data for a single date

    Args:
        collection_date: Date to verify

    Returns:
        dict: Summary statistics
    """
    db = DatabaseConnection()

    with db.get_connection() as conn:
        cursor = db.get_cursor(conn)

        # Get trades summary
        cursor.execute("""
            SELECT COUNT(*),
                   COUNT(DISTINCT underlying_symbol),
                   SUM(commission),
                   MIN(execution_time),
                   MAX(execution_time)
            FROM eod_trades
            WHERE collection_date = %s
        """, (collection_date,))

        result = cursor.fetchone()
        trades_count = result[0] if result[0] else 0
        symbols_count = result[1] if result[1] else 0
        total_commission = result[2] if result[2] else 0.0
        first_exec = result[3]
        last_exec = result[4]

        # Get trade details
        cursor.execute("""
            SELECT underlying_symbol, spread_name, spread_action,
                   spread_price, buy_leg_price, sell_leg_price,
                   quantity, commission, execution_time
            FROM eod_trades
            WHERE collection_date = %s
            ORDER BY execution_time
        """, (collection_date,))

        trades = cursor.fetchall()

    return {
        'date': collection_date,
        'trades_count': trades_count,
        'symbols_count': symbols_count,
        'total_commission': total_commission,
        'first_execution': first_exec,
        'last_execution': last_exec,
        'trades': trades
    }


def print_single_date_summary(stats):
    """Print summary for a single date"""
    print(f"\n{'='*80}")
    print(f"EOD Data Summary for {stats['date']}")
    print(f"{'='*80}")
    print(f"Total Trades:        {stats['trades_count']}")
    print(f"Unique Symbols:      {stats['symbols_count']}")
    print(f"Total Commission:    ${stats['total_commission']:.2f}")

    if stats['first_execution']:
        print(f"First Execution:     {stats['first_execution']}")
        print(f"Last Execution:      {stats['last_execution']}")

    if stats['trades']:
        print(f"\n{'Symbol':<8} {'Spread':<35} {'Action':<6} {'Spread $':<10} {'Buy $':<8} {'Sell $':<8} {'Qty':<5} {'Comm $':<8}")
        print("-" * 80)
        for trade in stats['trades']:
            symbol, spread, action, spread_price, buy_price, sell_price, qty, comm, exec_time = trade
            print(f"{symbol:<8} {spread[:35]:<35} {action:<6} {spread_price:>9.2f} {buy_price:>7.2f} {sell_price:>7.2f} {qty:>4} {comm:>7.2f}")
        print(f"{'='*80}\n")
    else:
        print(f"\n⚠ No trades found for {stats['date']}")
        print(f"{'='*80}\n")


def verify_multiple_dates(start_date, days):
    """
    Verify EOD data for multiple dates

    Args:
        start_date: Starting date
        days: Number of days to check (backwards from start_date)
    """
    print(f"\nVerifying EOD data for last {days} days starting from {start_date}\n")

    all_stats = []

    for i in range(days):
        check_date = start_date - timedelta(days=i)
        stats = verify_single_date(check_date)
        all_stats.append(stats)

    # Summary table
    print(f"{'='*80}")
    print(f"Multi-Day Summary")
    print(f"{'='*80}")
    print(f"{'Date':<12} {'Trades':<10} {'Symbols':<10} {'Commission':<15} {'First Exec':<20}")
    print("-" * 80)

    total_trades = 0
    total_commission = 0.0

    for stats in all_stats:
        first_exec_str = str(stats['first_execution'])[:19] if stats['first_execution'] else "N/A"
        print(f"{stats['date']!s:<12} {stats['trades_count']:<10} {stats['symbols_count']:<10} "
              f"${stats['total_commission']:<14.2f} {first_exec_str:<20}")
        total_trades += stats['trades_count']
        total_commission += stats['total_commission']

    print("-" * 80)
    print(f"{'TOTALS':<12} {total_trades:<10} {'':<10} ${total_commission:<14.2f}")
    print(f"{'='*80}\n")


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Verify EOD data collection in database'
    )
    parser.add_argument(
        '--date',
        type=str,
        default=date.today().isoformat(),
        help='Date to verify (YYYY-MM-DD), defaults to today'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=1,
        help='Number of days to check (backwards from --date), defaults to 1'
    )

    args = parser.parse_args()

    # Parse date
    try:
        check_date = datetime.strptime(args.date, '%Y-%m-%d').date()
    except ValueError:
        print(f"Error: Invalid date format: {args.date}. Use YYYY-MM-DD")
        sys.exit(1)

    # Run verification
    if args.days == 1:
        stats = verify_single_date(check_date)
        print_single_date_summary(stats)

        # Exit code based on data presence
        if stats['trades_count'] > 0:
            sys.exit(0)
        else:
            print("⚠ Warning: No trades found (this may be normal on non-trading days)")
            sys.exit(0)
    else:
        verify_multiple_dates(check_date, args.days)
        sys.exit(0)


if __name__ == "__main__":
    main()
