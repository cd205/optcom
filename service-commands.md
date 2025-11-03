# Trading Workflow Service Commands

## Service Management
```bash
# Start the service manually
sudo systemctl start trading-workflow.service

# Stop the service
sudo systemctl stop trading-workflow.service

# Restart the service
sudo systemctl restart trading-workflow.service

# Check service status
sudo systemctl status trading-workflow.service

# Enable auto-start on boot (already done)
sudo systemctl enable trading-workflow.service

# Disable auto-start on boot
sudo systemctl disable trading-workflow.service
```

## Monitoring and Logs
```bash
# View service logs (systemd journal)
sudo journalctl -u trading-workflow.service

# View service logs in real-time
sudo journalctl -f -u trading-workflow.service

# View startup script logs
cat /home/chris_s_dodd/optcom-1/trading-workflow-startup.log

# View startup script logs in real-time
tail -f /home/chris_s_dodd/optcom-1/trading-workflow-startup.log

# View Airflow logs
cat /home/chris_s_dodd/optcom-1/airflow_project/airflow.log

# View Airflow logs in real-time
tail -f /home/chris_s_dodd/optcom-1/airflow_project/airflow.log
```

## Process Monitoring
```bash
# Check if Airflow processes are running
ps aux | grep airflow

# Check if IBC Gateway processes are running
ps aux | grep java

# Check Airflow webserver (should respond on port 8080)
curl -f http://localhost:8080/health

# Monitor system resources used by the service
sudo systemctl status trading-workflow.service
```

## Troubleshooting
```bash
# If service fails, check detailed logs
sudo journalctl -xeu trading-workflow.service

# View last 50 lines of service logs
sudo journalctl -n 50 -u trading-workflow.service

# Check if service is enabled for boot
sudo systemctl is-enabled trading-workflow.service

# Reload systemd if you modify service files
sudo systemctl daemon-reload
```

## Files Created
- **Service file**: `/etc/systemd/system/trading-workflow.service`
- **Startup script**: `/home/chris_s_dodd/optcom-1/start-trading-workflow.sh`
- **Startup logs**: `/home/chris_s_dodd/optcom-1/trading-workflow-startup.log`
- **Airflow logs**: `/home/chris_s_dodd/optcom-1/airflow_project/airflow.log`