# Bittensor Manager

A convenient tool for managing Bittensor wallets, registration, and monitoring statistics.

## Contact & Support

- TTelegram_channel: [unluck_1l0ck](https://t.me/unluck_1l0ck)
- Telegram: [@one_lock](https://t.me/@one_lock)
- Twitter/X: [@1l0ck](https://x.com/1l0ck)

## Main Features

- Create and manage coldkeys and hotkeys
- View wallet statistics and balances
- Register in subnets with three modes:
  - Simple Registration (Immediate registration)
  - Professional Registration (Registration at next adjustment)
  - Auto Registration (Automatic registration across multiple adjustments)
- Transfer and unstaking TAO
- Monitor registration status

## Installation on Ubuntu

1. Update system and install required packages:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv git -y
```

2. Clone repository:
```bash
git clone https://github.com/yourusername/bittensor-manager.git
cd bittensor-manager
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
```

6. Get API key:
- Go to https://dash.taostats.io/login
- Register or login to your account
- Click "Get API Key" button
- Copy the obtained key
- Paste the key in config/config.yaml in the api_key field

## Usage

Start the manager:
```bash
python3 main.py
```

### Basic Operations

1. Create Wallet:
   - Select option "1" in main menu
   - Enter coldkey name
   - Specify number of hotkeys
   - Enter password
   - Save the mnemonic phrase in a secure place

2. View Statistics:
   - Select option "2" in main menu
   - Choose wallets to view
   - Select specific subnets or all subnets

3. Check Balance:
   - Select option "3" in main menu
   - Choose wallets to check

4. Register Wallets:
   - Select option "4" in main menu
   - Choose registration mode:
     - Simple: for immediate registration
     - Professional: for registration at next adjustment
     - Auto: for automatic registration across multiple adjustments
   - Follow on-screen instructions

5. Transfer/Unstaking:
   - Select option "5" in main menu
   - Choose desired operation
   - Follow on-screen instructions

## Security

- All sensitive data (mnemonic phrases, passwords) is stored locally in ~/.bittensor directory
- The seeds directory contains wallet information and should be protected
- Never share your config.yaml file as it contains your API key
- Regularly backup your mnemonic phrases and store them in a secure place

## Project Structure
```
bittensor-manager/
├── config/
│   └── config.yaml     # Configuration file (created from config.yaml.example)
├── data/
│   └── seeds/         # Directory for wallet information
├── logs/              # Directory for logs
├── src/              
│   ├── core/          # Core functionality
│   ├── ui/           # User interface
│   └── utils/        # Utilities
├── main.py           # Main script
└── requirements.txt  # Project dependencies
```

## Troubleshooting

If you encounter issues:
1. Check logs in the logs/ directory
2. Ensure API key is properly configured in config.yaml
3. Check internet connection
4. Verify directory permissions

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
