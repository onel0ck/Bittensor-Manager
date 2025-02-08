Конечно, вот обновленная версия README.md с добавлением описания всех функций и режимов:

```markdown
# Bittensor Manager

A convenient tool for managing Bittensor wallets, registration, and monitoring statistics.

## Contact & Support

- Telegram_channel: [unluck_1l0ck](https://t.me/unluck_1l0ck)
- Telegram: [@one_lock](https://t.me/@one_lock)
- Twitter/X: [@1l0ck](https://x.com/1l0ck)

## Main Features

- Create and manage coldkeys and hotkeys
- View detailed wallet statistics and balances across all subnets
- Multiple registration modes:
  - Simple Registration (Immediate registration)
  - Professional Registration (Registration at next adjustment)
  - Auto Registration (Automatic registration across multiple adjustments)
  - Sniper Registration (Monitor and auto-register when registration opens)
- Transfer and unstaking TAO
- Monitor registration status in real-time
- Multi-subnet support
- Cost-based registration control

## Installation on Ubuntu

1. Update system and install required packages:
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
apt install nano
nano config/config.yaml
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

### Registration Modes

1. **Simple Registration (Immediate)**
   - For instant registration attempts
   - Useful when registration is currently open
   - Allows multiple hotkeys per coldkey
   - No timing optimization

2. **Professional Registration (Next Adjustment)**
   - Targets the next registration adjustment period
   - Single hotkey per coldkey for precision
   - Includes preparation time optimization
   - Shows detailed registration timing info

3. **Auto Registration (Multiple Adjustments)**
   - Automatically attempts registration across multiple periods
   - Supports multiple hotkeys per coldkey
   - Includes cost control and timing optimization
   - Continues until all registrations complete

4. **Sniper Registration (NEW!)**
   - Monitors multiple subnets simultaneously
   - Auto-registers when registration opens
   - Includes maximum cost control
   - Real-time status updates
   - Supports multiple hotkeys and subnets

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
   - View detailed performance metrics
   - Monitor rewards and emissions

3. Check Balance:
   - Select option "3" in main menu
   - Choose wallets to check
   - View TAO balances
   - Track total stake

4. Register Wallets:
   - Select option "4" in main menu
   - Choose registration mode
   - Follow on-screen instructions
   - Monitor registration progress
   - Receive real-time status updates

5. Transfer/Unstaking:
   - Select option "5" in main menu
   - Choose desired operation
   - Transfer TAO between wallets
   - Unstake from specific hotkeys
   - Manage stake distribution

## Security

- All sensitive data (mnemonic phrases, passwords) is stored locally in ~/.bittensor directory
- The seeds directory contains wallet information and should be protected
- Never share your config.yaml file as it contains your API key
- Regularly backup your mnemonic phrases and store them in a secure place
- Use strong passwords for all wallets
- Keep your system and dependencies updated

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
│   ├── ui/           # User interface/bot
│   └── utils/
├── main.py
└── requirements.txt  # Project dependencies
```

## Troubleshooting

If you encounter issues:
1. Check logs in the logs/ directory
2. Ensure API key is properly configured in config.yaml
3. Verify directory permissions
4. Check network connectivity
5. Verify wallet permissions and access
6. Ensure sufficient TAO balance for operations

Common Issues:
- API rate limit: Wait a few minutes between requests
- Registration closed: Use Sniper mode to auto-register
- Invalid password: Double-check wallet password
- Network errors: Verify internet connection
- Permission denied: Check directory permissions

## License

This project is licensed under the MIT License - see the LICENSE file for details.
Хотите, чтобы я внес какие-то дополнительные изменения или уточнения?
