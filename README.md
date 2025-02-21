# Bittensor Manager
A tool for managing Bittensor wallets, registrations, and network statistics monitoring.

## Contacts
* Telegram Channel: [unluck_1l0ck](https://t.me/unluck_1l0ck)
* Telegram: @one_lock
* Twitter/X: @1l0ck

## Main Features

### Wallet Management
* Creating and managing coldkey/hotkey
* View detailed wallet statistics and balances
* View wallet balances and addresses
* Transfer TAO between wallets
* Unstaking Alpha TAO (DTAO):
  * Unstake from specific subnet or all subnets simultaneously
  * Automatic mode with single password for all wallets
  * Manual mode with individual passwords
  * Safe unstaking with automatic optimal amount calculation (99% of stake)
  * Support for partial unstaking with 30% tolerance
  * Detailed display of stakes for each subnet and hotkey

### Registration Modes
1. Simple Registration (Simple)
   * Immediate registration attempt
   * Support for multiple hotkeys for one coldkey

2. Professional Registration (Professional)
   * Registration at the next adjustment block
   * Timing control (-19 to +19 seconds)
   * One hotkey per coldkey for precise timing
   * Negative timing: Start N seconds BEFORE target block
   * Positive timing: Wait N seconds AFTER target block

3. Auto Registration (Auto)
   * Automatic registration through multiple adjustments
   * Support for multiple hotkeys
   * Control maximum cost in TAO

4. Sniper Registration (DEGEN mode)
   * Monitoring of specific target subnet for registration
   * Support for multiple hotkeys across multiple coldkeys
   * Automatic registration attempt when opportunity arises
   * Works in DEGEN mode - aggressive approach to registration
   * Default password option available for all wallets

### Statistics and Monitoring
* Real-time balance checking
* View wallet addresses
* Detailed subnet statistics
* Staking monitoring
* Daily rewards calculation

## Installation

### System Requirements
* Ubuntu (recommended)
* Python 3.8 or higher
* Active internet connection

### Installation Steps
1. Update system and install dependencies:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv git -y
```

2. Clone repository:
```bash
git clone https://github.com/onel0ck/Bittensor-Manager.git
cd Bittensor-Manager
```

3. Create and activate virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

4. Install dependencies:
```bash
pip install -r requirements.txt
```

5. Configure settings:
```bash
cp config/config.yaml.example config/config.yaml
nano config/config.yaml
```

### API Key Setup
1. Go to https://dash.taostats.io/login
2. Register or login
3. Click "Get API Key"
4. Copy the obtained key
5. Paste the key in config/config.yaml in the api_key field

### Project Structure
```
bittensor-manager/
├── config/
│   └── config.yaml
├── data/
│   └── seeds/
├── logs/
├── src/
│   ├── core/
│   ├── ui/
│   └── utils/
├── main.py
└── requirements.txt
```

## Security

### Wallet Security
* All sensitive data is stored locally in ~/.bittensor
* Mnemonic phrases are stored in data/seeds
* File permissions are automatically set to 600
* Regular backups are recommended

### Logs
* Main logs: logs/bittensor_manager.log
* Registration logs: logs/registration/
* Individual registration logs are named by timestamp

## License
Project is distributed under MIT License
