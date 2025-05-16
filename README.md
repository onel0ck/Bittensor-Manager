# Bittensor Manager

A comprehensive tool for managing Bittensor wallets, registrations, and network statistics monitoring.

# Contacts
* Telegram Channel: [unluck_1l0ck](https://t.me/unluck_1l0ck)
* Telegram: @one_lock
* Twitter/X: @1l0ck

## Features

### Wallet Management
- Create and manage coldkeys/hotkeys with automated naming
- View wallet balances and addresses across multiple wallets
- Transfer TAO between wallets with single or batch operations
- Collect TAO from multiple wallets to a single destination
- Unstake Alpha TAO (DTAO) from specific subnets or all subnets
- Safe unstaking with automatic optimization (99% of stake)
- Support for partial unstaking with customizable tolerance
- Emergency unstaking recovery for difficult cases

### Registration Capabilities
- **Simple Registration**: Immediate registration with support for multiple hotkeys per coldkey
- **Auto Registration**: Automatic registration through multiple adjustments with maximum cost control
- **Sniper Registration (DEGEN mode)**: Aggressively monitor and register when opportunities arise
- **Spread Registration**: Register multiple hotkeys with distributed timing for better success rate
- **Subnet Monitor Registration**: Wait for closed registration to open and register automatically
- **Price Monitor Registration**: Register automatically when price falls below target threshold
- **Professional Registration**: Register at the next adjustment block with precise timing control (-19 to +19 seconds)

### Auto Token Buyer
- Buy subnet tokens with single or batch operations
- Monitor subnet registration status and buy tokens when registration closes
- Monitor for new subnet appearance and buy tokens automatically
- Customizable purchase parameters (amount, tolerance, timing, retries)
- Robust error handling with automatic parameter adjustments for difficult purchases

### Statistics and Monitoring
- Real-time balance checking across multiple wallets
- Detailed subnet statistics with daily rewards calculations
- Monitor stakes across all subnets with USD value estimation
- Advanced parallel processing for faster statistics gathering
- Summary statistics for all wallets in portfolio
- Support for unregistered stakes monitoring and management
- Live TAO price tracking from multiple sources

### Subnet Scanner
- Monitor all subnets for registration status
- Identify subnets with specific characteristics:
  - Few validators
  - Miners only
  - Single validator
  - No active validators
  - Disabled commit-reveal weights
  - High registration difficulty
- Registration activity analysis for target subnets
- Get detailed information about specific subnets

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
- Add hotkeys to existing coldkeys with automatic naming

#### Registration
- Choose from various registration strategies:
  - Simple: Immediate registration attempts
  - Auto: Register across multiple adjustment blocks
  - Sniper: Aggressively monitor for registration opportunities
  - Spread: Distribute registration attempts with optimized timing
  - Subnet Monitor: Wait for open registration window
  - Price Monitor: Register when price falls below target
- Control timing precision from -19 to +19 seconds for optimal success rate
- Set maximum TAO cost for registrations
- Monitor for specific subnet appearance and register automatically

#### Token Buying
- Buy subnet tokens with customizable parameters
- Monitor for registration status changes and buy automatically
- Detect new subnets and purchase tokens when they appear
- Configure buying parameters (amount, tolerance, retries)
- Robust error handling with automatic parameter adjustments

#### Statistics
- View detailed wallet statistics across subnets
- Calculate daily rewards in TAO and USD
- Check TAO balances and wallet addresses
- Get total portfolio value across all wallets
- Monitor both registered and unregistered stakes
- Track live TAO price from multiple sources

#### TAO Transfers
- Transfer TAO between wallets
- Batch transfer to multiple addresses
- Collect TAO from multiple wallets to a single destination
- Unstake Alpha TAO with custom tolerance settings
- Emergency unstaking for difficult cases

#### Subnet Scanner
- Scan all subnets for registration status
- Identify interesting subnets based on specific characteristics
- Analyze registration activity and competition levels
- Get detailed information about specific subnets

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
