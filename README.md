# Bittensor Manager

A comprehensive tool for managing Bittensor wallets, registrations, and network statistics monitoring.

# Contacts
* Telegram Channel: [unluck_1l0ck](https://t.me/unluck_1l0ck)
* Telegram: @one_lock
* Twitter/X: @1l0ck

## Features

### Wallet Management
- Create and manage coldkeys/hotkeys
- View wallet balances and addresses
- Transfer TAO between wallets
- Unstake Alpha TAO (DTAO) from specific subnets or all subnets
- Safe unstaking with automatic optimization (99% of stake)
- Support for partial unstaking

### Registration Capabilities
- **Simple Registration**: Immediate registration with support for multiple hotkeys per coldkey
- **Professional Registration**: Register at the next adjustment block with precise timing control (-19 to +19 seconds)
- **Auto Registration**: Automatic registration through multiple adjustments with maximum cost control
- **Sniper Registration (DEGEN mode)**: Aggressively monitor and register when opportunities arise

### Statistics and Monitoring
- Real-time balance checking
- Detailed subnet statistics
- View daily rewards calculations
- Monitor stakes across all subnets

## Installation

### System Requirements
- Ubuntu (recommended)
- Python 3.8+
- Active internet connection

### Setup

1. Update system and install dependencies:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv git -y
```

2. Clone repository:
```bash
git clone https://github.com/yourusername/Bittensor-Manager.git
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
nano config/config.yaml
```

### TaoStats API Setup
1. Go to https://dash.taostats.io/login
2. Register or login
3. Click "Get API Key"
4. Copy the obtained key
5. Add to your config.yaml in the api_key field

## Usage

Start the manager with:
```bash
python main.py
```

### Main Features

#### Wallet Creation
- Create new coldkeys with multiple hotkeys
- Add hotkeys to existing coldkeys

#### Registration
- Choose from Simple, Professional, Auto, or Sniper registration modes
- Control timing for registration attempts
- Set maximum TAO cost for registrations

#### Statistics
- View detailed wallet statistics across subnets
- Calculate daily rewards
- Check TAO balances and wallet addresses

#### TAO Transfers
- Transfer TAO between wallets
- Unstake Alpha TAO with custom tolerance settings

## Security

- All sensitive data is stored locally in ~/.bittensor
- Mnemonic phrases are stored in data/seeds with restricted permissions (600)
- Regular backups are recommended

## Project Structure

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

## License
Project is distributed under MIT License
