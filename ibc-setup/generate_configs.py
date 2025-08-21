#!/usr/bin/env python3
"""
Generate IBC configuration files from credentials.json
This script reads IBKR credentials from the centralized JSON file and creates
the appropriate INI configuration files for both paper and live trading.
"""

import json
import os
import sys
from pathlib import Path

def load_credentials():
    """Load credentials from the config/credentials.json file"""
    script_dir = Path(__file__).parent
    credentials_path = script_dir.parent / "config" / "credentials.json"
    
    try:
        with open(credentials_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Credentials file not found: {credentials_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in credentials file: {e}")
        sys.exit(1)

def generate_config_template():
    """Generate the base configuration template"""
    return """# IBC Configuration - Generated from credentials.json
# Do not edit manually - this file is auto-generated

# IBC Startup Settings
FIX=no

# Authentication Settings - FROM CREDENTIALS.JSON
IbLoginId={username}
IbPassword={password}

# Second Factor Authentication Settings
SecondFactorDevice=
ReloginAfterSecondFactorAuthenticationTimeout=no
SecondFactorAuthenticationExitInterval=60
SecondFactorAuthenticationTimeout=180
ExitAfterSecondFactorAuthenticationTimeout=no

# Trading Mode
TradingMode={trading_mode}

# Paper Trading Warning
AcceptNonBrokerageAccountWarning={accept_warning}

# Login Settings
LoginDialogDisplayTimeout=60

# TWS Startup Settings
StoreSettingsOnServer=no
MinimizeMainWindow=no
ExistingSessionDetectedAction=primary

# API Configuration
OverrideTwsApiPort=
OverrideTwsMasterClientID=
ReadOnlyLogin=no
ReadOnlyApi=no

# API Precautions (all defaults)
BypassOrderPrecautions=
BypassBondWarning=
BypassNegativeYieldToWorstConfirmation=
BypassCalledBondWarning=
BypassSameActionPairTradeWarning=
BypassPriceBasedVolatilityRiskWarning=
BypassUSStocksMarketDataInSharesWarning=
BypassRedirectOrderWarning=
BypassNoOverfillProtectionPrecaution=

# Market Data Settings
AcceptBidAskLastSizeDisplayUpdateNotification=defer
SendMarketDataInLotsForUSstocks=

# Connection Settings
AcceptIncomingConnectionAction=accept
AllowBlindTrading=no
TrustedTwsApiClientIPs=

# Auto-restart Settings
AutoLogoffTime=
AutoRestartTime=
ColdRestartTime=07:05
ClosedownAt=

# Order Settings
ResetOrderIdsAtStart=no
ConfirmOrderIdReset=ignore/ignore

# Other Settings
SaveTwsSettingsAt=
ConfirmCryptoCurrencyOrders=manual

# Indian TWS Settings
DismissPasswordExpiryWarning=no
DismissNSEComplianceNotice=yes

# IBC Command Server (disabled for security)
CommandServerPort=0
ControlFrom=
BindAddress=
CommandPrompt=
SuppressInfoMessages=yes

# Diagnostic Settings
LogStructureScope=known
LogStructureWhen=never
IncludeStackTraceForExceptions=no
"""

def generate_configs(credentials):
    """Generate both paper and live configuration files"""
    script_dir = Path(__file__).parent
    config_dir = script_dir / "config"
    
    # Ensure config directory exists
    config_dir.mkdir(exist_ok=True)
    
    # Check if IBKR credentials exist
    if 'ibkr' not in credentials:
        print("❌ No 'ibkr' section found in credentials.json")
        print("Please add your IBKR credentials to the JSON file")
        return False
    
    ibkr_creds = credentials['ibkr']
    
    # Generate paper trading config
    if 'paper' in ibkr_creds:
        paper_creds = ibkr_creds['paper']
        paper_config = generate_config_template().format(
            username=paper_creds['username'],
            password=paper_creds['password'],
            trading_mode='paper',
            accept_warning='yes'  # Auto-accept paper trading warning
        )
        
        paper_file = config_dir / "config-paper.ini"
        with open(paper_file, 'w') as f:
            f.write(paper_config)
        print(f"✅ Generated paper trading config: {paper_file}")
    else:
        print("⚠️  No paper trading credentials found in JSON")
    
    # Generate live trading config
    if 'live' in ibkr_creds:
        live_creds = ibkr_creds['live']
        live_config = generate_config_template().format(
            username=live_creds['username'],
            password=live_creds['password'],
            trading_mode='live',
            accept_warning='no'  # Do NOT auto-accept for live trading
        )
        
        live_file = config_dir / "config-live.ini"
        with open(live_file, 'w') as f:
            f.write(live_config)
        print(f"✅ Generated live trading config: {live_file}")
    else:
        print("⚠️  No live trading credentials found in JSON")
    
    # Create default config.ini pointing to paper
    default_config = config_dir / "config.ini"
    paper_config_file = config_dir / "config-paper.ini"
    
    if paper_config_file.exists():
        # Remove existing symlink if it exists
        if default_config.is_symlink():
            default_config.unlink()
        # Create new symlink
        default_config.symlink_to("config-paper.ini")
        print(f"✅ Default config.ini → config-paper.ini")
    
    return True

def main():
    """Main function"""
    print("🔧 Generating IBC configuration files from credentials.json...")
    
    # Load credentials
    credentials = load_credentials()
    
    # Generate configs
    success = generate_configs(credentials)
    
    if success:
        print("\n🎯 Configuration files generated successfully!")
        print("\n📝 Next steps:")
        print("1. Add your IBKR credentials to config/credentials.json")
        print("2. Run this script again to regenerate configs")
        print("3. Test the gateway startup with ./start-dual-gateway.sh start")
    else:
        print("\n❌ Failed to generate configuration files")
        sys.exit(1)

if __name__ == "__main__":
    main()