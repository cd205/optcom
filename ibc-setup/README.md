# IBC Gateway Setup - Interactive Brokers Automated Trading

This setup provides a production-ready IB Gateway configuration using IBC (Interactive Brokers Controller) following best practices from the official IBC documentation.

## 🏗️ What's Been Set Up

- **IBC 3.23.0**: Latest version downloaded and configured
- **TWS/Gateway**: Offline version installed and properly structured  
- **Xvfb**: Virtual display for headless server operation
- **Security**: Best practices configuration with encrypted credentials support
- **Automation**: Startup/shutdown scripts with logging

## 📁 Directory Structure

```
ibc-setup/
├── config/
│   ├── config.ini          # IBC configuration file
│   └── config.ini.backup   # Original backup
├── ibc/                    # IBC application files
├── tws/                    # TWS/Gateway installation
├── logs/                   # Log files
├── start-gateway.sh        # Main startup script
├── test_connection.py      # Connection test utility
└── README.md              # This file
```

## 🚀 Getting Started

### 1. Update Your Credentials

Edit the configuration file with your actual IB credentials:

```bash
nano config/config.ini
```

Update these lines:
```ini
# Replace with your actual Interactive Brokers credentials
IbLoginId=YOUR_IB_USERNAME
IbPassword=YOUR_IB_PASSWORD

# Set trading mode: 'paper' for demo, 'live' for real trading
TradingMode=paper
```

### 2. Start the Gateway

```bash
# Start the Gateway
./start-gateway.sh start

# Check status
./start-gateway.sh status

# Restart if needed
./start-gateway.sh restart

# Stop the Gateway
./start-gateway.sh stop
```

### 3. Test the Connection

```bash
# Test if API port is accessible
./test_connection.py

# Or check manually
ss -tln | grep 4001
```

### 4. Update Your Python Script

Your notebook should connect using:
```python
from ibapi.client import EClient
from ibapi.wrapper import EWrapper

# Connection settings
host = '127.0.0.1'
port = 4001        # Gateway API port
clientId = 1       # Unique client ID

# Connect to Gateway
app.connect(host, port, clientId)
```

## ⚙️ Configuration Details

### Security Features
- ✅ Encrypted credential storage support
- ✅ Trusted API client IP restrictions  
- ✅ Automatic session management
- ✅ Read-only mode options

### Automation Features
- ✅ Daily auto-restart at 11:45 PM
- ✅ Weekly cold restart on Sundays at 6:00 AM
- ✅ Automatic settings backup every 4 hours
- ✅ Headless operation with Xvfb

### API Configuration
- ✅ Port 4001 (Gateway default)
- ✅ Accepts connections from localhost
- ✅ Paper trading mode enabled
- ✅ Market data in shares format

## 📊 Monitoring

### Log Files
- `logs/startup.log`: Startup script logs
- `logs/gateway.log`: IBC and Gateway logs  
- `logs/gateway.pid`: Process ID file

### Status Commands
```bash
# Check if Gateway is running
./start-gateway.sh status

# View recent logs
tail -f logs/gateway.log

# Check API port
ss -tln | grep 4001
```

## 🔧 Troubleshooting

### Gateway Won't Start
1. Check logs: `tail -f logs/gateway.log`
2. Verify credentials in `config/config.ini`
3. Ensure no other TWS/Gateway instances are running
4. Try restarting: `./start-gateway.sh restart`

### Connection Errors in Python
1. Test connection: `./test_connection.py`
2. Check if port 4001 is listening: `ss -tln | grep 4001`
3. Verify Gateway logs for authentication issues
4. Ensure clientId is unique in your Python code

### Display Issues (Headless)
The setup uses Xvfb for virtual display. If you see display errors:
1. Check if Xvfb is running: `ps aux | grep xvfb`
2. Display is set to `:99` for headless operation
3. Logs will show "Using Xvfb display" when active

### Authentication Issues
1. Double-check credentials in `config/config.ini`
2. For live accounts, ensure 2FA is properly configured
3. Demo account: username=`edemo`, password=`demouser`
4. Check IB account status and permissions

## 🔄 Production Deployment

### Environment Variables (Recommended)
For security, use environment variables instead of hardcoded credentials:

```bash
export IB_USERNAME="your_username"  
export IB_PASSWORD="your_password"
```

Then update `config/config.ini`:
```ini
IbLoginId=${IB_USERNAME}
IbPassword=${IB_PASSWORD}
```

### Systemd Service (Optional)
Create a systemd service for automatic startup:

```bash
sudo tee /etc/systemd/system/ib-gateway.service << EOF
[Unit]
Description=IB Gateway with IBC
After=network.target

[Service]
Type=simple
User=chris_s_dodd
WorkingDirectory=/home/chris_s_dodd/optcom-2/ibc-setup
ExecStart=/home/chris_s_dodd/optcom-2/ibc-setup/start-gateway.sh start
ExecStop=/home/chris_s_dodd/optcom-2/ibc-setup/start-gateway.sh stop
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable ib-gateway
sudo systemctl start ib-gateway
```

## 📚 References

- [IBC User Guide](https://github.com/IbcAlpha/IBC/blob/master/userguide.md)
- [Interactive Brokers API Documentation](https://interactivebrokers.github.io/tws-api/)
- [IBC GitHub Repository](https://github.com/IbcAlpha/IBC)

## 🛟 Support

If you encounter issues:
1. Check the logs in the `logs/` directory
2. Verify your IB account credentials and permissions
3. Ensure network connectivity to IB servers
4. Review IBC documentation for advanced configuration options

---

**Note**: This setup is configured for paper trading by default. Change `TradingMode=live` in `config/config.ini` for live trading, and ensure you understand the risks involved.