```markdown
# Bittensor Manager

A powerful tool for managing Bittensor wallets, registrations, and monitoring network statistics.

## Contact & Support
- Telegram Channel: [unluck_1l0ck](https://t.me/unluck_1l0ck)
- Telegram: [@one_lock](https://t.me/@one_lock)
- Twitter/X: [@1l0ck](https://x.com/1l0ck)

## Main Features

### Wallet Management
- Create and manage coldkeys
- Generate multiple hotkeys
- View detailed wallet statistics and balances
- Transfer TAO between wallets
- Manage stake distribution

### Registration Features
1. Simple Registration Mode
   - Immediate registration attempt
   - Best for quick registrations when network is open
   - Allows multiple hotkeys per coldkey

2. Professional Registration Mode
   - Times registration for the next adjustment block
   - Advanced timing control (-19 to +19 seconds)
   - One hotkey per coldkey for precise timing
   - Negative timing: Start N seconds BEFORE target block
   - Positive timing: Wait N seconds AFTER target block

3. Auto Registration Mode
   - Automatic registration across multiple adjustments
   - Multiple hotkeys per coldkey
   - Continues until all hotkeys are registered
   - Cost control with maximum TAO limit

4. Sniper Registration Mode
   - Monitors multiple subnets simultaneously
   - Automatic registration when conditions are met
   - Cost threshold control
   - Customizable check interval
   - Perfect for catching registration windows

### Statistics and Monitoring
- Real-time balance checking
- Detailed subnet statistics
- Stake monitoring
- Registration status tracking
- Daily rewards calculation

## Installation

### System Requirements
- Ubuntu (recommended)
- Python 3.8 or higher
- Active internet connection

### Installation Steps

1. Update system and install requirements:
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
1. Visit https://dash.taostats.io/login
2. Register or login to your account
3. Click "Get API Key" button
4. Copy the obtained key
5. Paste the key in config/config.yaml in the api_key field

## Detailed Usage Guide

### Starting the Manager
```bash
python3 main.py
```

### Wallet Creation
1. Select "Create Coldkey/Hotkey" from main menu
2. Choose "Create new coldkey with hotkeys"
3. Enter coldkey name
4. Specify number of hotkeys
5. Enter and confirm password
6. Save the mnemonic phrase securely

### Registration Modes

#### Simple Registration
- Best for immediate registration attempts
- Use when subnet is open and competition is low
- Supports multiple hotkeys per wallet

#### Professional Registration
- Advanced timing control
- Enter timing adjustment (-19 to +19 seconds)
  - Negative value: Starts N seconds before target block
  - Positive value: Waits N seconds after target block
- One hotkey per coldkey for precise timing
- Shows detailed registration information and cost

#### Auto Registration
- Automated registration across adjustments
- Set maximum TAO cost threshold
- Continues until all hotkeys are registered
- Handles multiple hotkeys efficiently

#### Sniper Registration
- Monitor multiple subnets simultaneously
- Set custom check intervals
- Define maximum registration cost
- Automatic registration when conditions are met
- Real-time status updates

### Statistics and Monitoring
- View comprehensive wallet statistics
- Check TAO balances
- Monitor stake distribution
- Track registration status
- View daily rewards

### Transfer and Unstaking
- Transfer TAO between wallets
- Manage stake distribution
- Unstake from specific hotkeys
- Batch unstaking operations

## Security Considerations

### Wallet Security
- All sensitive data stored locally in ~/.bittensor
- Mnemonic phrases stored securely in data/seeds
- File permissions automatically set to 600
- Regular backups recommended

### Configuration Security
- Never share your config.yaml
- Protect your API keys
- Regular password changes recommended
- Backup mnemonic phrases offline

## Troubleshooting

### Common Issues
1. Check logs in logs/ directory
2. Verify API key configuration
3. Ensure correct file permissions
4. Check network connectivity

### Log Locations
- Main logs: logs/bittensor_manager.log
- Registration logs: logs/registration/
- Individual registration logs named by timestamp

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

## Contributing
Contributions are welcome! Please feel free to submit Pull Requests.

## License
This project is licensed under the MIT License - see the LICENSE file for details.
```
