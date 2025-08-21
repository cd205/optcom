# IB Gateway Quick Reference

## Location
All commands must be run from: `/home/chris_s_dodd/optcom-2/ibc-setup/`

## Starting Gateway
```bash
./start-dual-gateway.sh start # Start both paper + live accounts
./start-dual-gateway.sh paper     # Start only paper account (port 4001)
./start-dual-gateway.sh live      # Start only live account (port 4002)
```

## Monitoring
```bash
./start-dual-gateway.sh status    # Check if processes are running
./test_both_connections.py        # Test API connections to both accounts
tail -f logs/gateway-paper.log    # Watch paper account logs in real-time
tail -f logs/gateway-live.log     # Watch live account logs in real-time
```

## Stopping
```bash
./start-dual-gateway.sh stop      # Stop both accounts
./start-dual-gateway.sh restart   # Restart both accounts
```

## Ports
- **Paper Trading**: localhost:4001
- **Live Trading**: localhost:4002

## VS Code Terminal
Right-click `ibc-setup` folder → "Open in Integrated Terminal"