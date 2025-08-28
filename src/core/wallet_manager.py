import os
import json
import pexpect
import time
import bittensor as bt
from typing import Dict, List, Optional
from datetime import datetime
from ..utils.logger import setup_logger
from rich.console import Console
console = Console()
logger = setup_logger('wallet_manager', 'logs/wallet_manager.log')

class WalletManager:
    def __init__(self, config):
        self.config = config
        self.seeds_path = config.get('wallet.seeds_path', 'data/seeds')
        os.makedirs(self.seeds_path, exist_ok=True)

    def _run_btcli(self, command: list, inputs: list) -> tuple[str, str, str]:
        cmd = ' '.join(command)
        output = ''
        mnemonic = ''
        address = ''

        child = pexpect.spawn(cmd)
        child.logfile = None

        try:
            input_index = 0
            
            while True:
                try:
                    index = child.expect([
                        'Choose the number',  # 0 - word count prompt
                        'Overwrite\\?',       # 1 - overwrite prompt
                        '\\(y/N\\)',         # 2 - alternative overwrite format
                        'mnemonic',           # 3 - mnemonic in output
                        pexpect.EOF,          # 4 - end of output
                        pexpect.TIMEOUT       # 5 - timeout
                    ], timeout=5)
                    
                    current_output = child.before.decode('utf-8') if child.before else ''
                    output += current_output
                    
                    # Extract mnemonic if present
                    if "mnemonic" in current_output.lower():
                        for line in current_output.split('\n'):
                            if "mnemonic" in line.lower() and ":" in line:
                                mnemonic = line.split(":", 1)[1].strip()
                                break
                    
                    if index == 0:  # Word count prompt
                        child.sendline(inputs[input_index] if input_index < len(inputs) else "12")
                        input_index += 1
                        
                    elif index in [1, 2]:  # Overwrite prompts
                        child.sendline('y')
                        logger.debug("Sent 'y' to overwrite prompt")
                        
                    elif index == 3:  # Mnemonic found
                        continue
                        
                    elif index in [4, 5]:  # EOF or timeout
                        break
                        
                except pexpect.TIMEOUT:
                    break
                except pexpect.EOF:
                    break
            
            # Try to get remaining output
            try:
                child.expect(pexpect.EOF, timeout=1)
                final_output = child.before.decode('utf-8') if child.before else ''
                output += final_output
            except:
                pass

            # Extract mnemonic from full output if not found yet
            if not mnemonic:
                for line in output.split('\n'):
                    if "mnemonic" in line.lower() and ":" in line:
                        mnemonic = line.split(":", 1)[1].strip()
                        break

            # Get wallet and hotkey names
            wallet_name = None
            hotkey_name = None
            for i, arg in enumerate(command):
                if arg == '--wallet.name' and i + 1 < len(command):
                    wallet_name = command[i + 1]
                elif arg == '--wallet.hotkey' and i + 1 < len(command):
                    hotkey_name = command[i + 1]

            if not wallet_name:
                raise Exception("Could not find wallet name in command")

            # Wait for files to be created
            time.sleep(2)

            # Get address
            try:
                if hotkey_name:
                    wallet = bt.wallet(name=wallet_name, hotkey=hotkey_name)
                    address = wallet.hotkey.ss58_address
                else:
                    wallet = bt.wallet(name=wallet_name)
                    address = wallet.coldkeypub.ss58_address
            except Exception as e:
                logger.warning(f"Could not get address immediately, retrying: {e}")
                time.sleep(3)
                try:
                    if hotkey_name:
                        wallet = bt.wallet(name=wallet_name, hotkey=hotkey_name)
                        address = wallet.hotkey.ss58_address
                    else:
                        wallet = bt.wallet(name=wallet_name)
                        address = wallet.coldkeypub.ss58_address
                except Exception as e2:
                    logger.error(f"Failed to get address: {e2}")
                    address = ""

            logger.debug(f"Command completed. Address: {address}")

        except Exception as e:
            logger.error(f"Error in _run_btcli: {str(e)}\nCommand: {cmd}")
            raise
        finally:
            try:
                child.close(force=True)
            except:
                pass

        return output, mnemonic, address


    def batch_add_hotkeys(self, wallet_configs: List[Dict], num_hotkeys: int) -> Dict:
        """
        Add hotkeys to multiple wallets in batch mode
        
        Args:
            wallet_configs: List of dicts with 'name' and optionally 'password'
            num_hotkeys: Number of hotkeys to add to each wallet
            
        Returns:
            Dict with results for each wallet
        """
        results = {}
        
        for config in wallet_configs:
            wallet_name = config.get('name')
            password = config.get('password', '')
            
            try:
                console.print(f"\n[cyan]Processing wallet: {wallet_name}[/cyan]")
                wallet_path = os.path.expanduser(f"~/.bittensor/wallets/{wallet_name}")
                
                if not os.path.exists(wallet_path):
                    console.print(f"[yellow]Wallet {wallet_name} does not exist, skipping[/yellow]")
                    results[wallet_name] = {'success': False, 'error': 'Wallet does not exist'}
                    continue
                
                wallet_info = self._load_wallet_info(wallet_name)
                if wallet_info is None:
                    wallet_info = {
                        'coldkey': {
                            'name': wallet_name,
                            'created_at': datetime.now().isoformat()
                        },
                        'hotkeys': []
                    }
                
                created_hotkeys = []
                base_command = ["btcli", "wallet", "new_hotkey", "--wallet.name", wallet_name]
                base_inputs = ["12"]  # Number of words
                
                for i in range(num_hotkeys):
                    hotkey_name = self._get_next_hotkey_name(wallet_name)
                    console.print(f"  Creating hotkey {hotkey_name}...")
                    
                    command = base_command + ["--wallet.hotkey", hotkey_name]
                    
                    try:
                        _, _, hotkey_address = self._run_btcli(command, base_inputs)
                        
                        wallet_info['hotkeys'].append({
                            'name': hotkey_name,
                            'address': hotkey_address,
                            'created_at': datetime.now().isoformat()
                        })
                        
                        created_hotkeys.append({
                            'name': hotkey_name,
                            'address': hotkey_address
                        })
                        
                        console.print(f"  [green]✓ Created hotkey {hotkey_name}: {hotkey_address}[/green]")
                        time.sleep(1)  # Small delay between hotkey creations
                        
                    except Exception as e:
                        logger.error(f"Failed to create hotkey {hotkey_name} for {wallet_name}: {str(e)}")
                        console.print(f"  [red]✗ Failed to create hotkey {hotkey_name}: {str(e)}[/red]")
                
                if created_hotkeys:
                    self._save_seeds(wallet_name, wallet_info)
                    results[wallet_name] = {
                        'success': True,
                        'hotkeys': created_hotkeys,
                        'count': len(created_hotkeys)
                    }
                    console.print(f"[green]Successfully added {len(created_hotkeys)} hotkeys to {wallet_name}[/green]")
                else:
                    results[wallet_name] = {
                        'success': False,
                        'error': 'No hotkeys were created'
                    }
                    
            except Exception as e:
                logger.error(f"Failed to process wallet {wallet_name}: {str(e)}")
                results[wallet_name] = {
                    'success': False,
                    'error': str(e)
                }
                console.print(f"[red]Failed to process wallet {wallet_name}: {str(e)}[/red]")
        
        return results

    def _get_next_hotkey_name(self, coldkey_name: str) -> str:
        wallet_path = os.path.expanduser(f"~/.bittensor/wallets/{coldkey_name}/hotkeys")
        existing_hotkeys = set()

        if os.path.exists(wallet_path):
            existing_hotkeys = set(os.listdir(wallet_path))

        counter = 1
        while str(counter) in existing_hotkeys:
            counter += 1

        return str(counter)

    def create_wallet(self, coldkey_name: str, num_hotkeys: int, password: str) -> Dict:
        try:
            logger.info(f"Creating coldkey {coldkey_name}")

            coldkey_output, coldkey_mnemonic, coldkey_address = self._run_btcli(
                ["btcli", "wallet", "new_coldkey", "--wallet.name", coldkey_name],
                ["~/.bittensor/wallets/", "12", password, password]
            )

            if not coldkey_mnemonic:
                raise Exception("Failed to extract coldkey mnemonic from btcli output")

            wallet_info = {
                'coldkey': {
                    'name': coldkey_name,
                    'mnemonic': coldkey_mnemonic,
                    'address': coldkey_address,
                    'password': password,
                    'created_at': datetime.now().isoformat()
                },
                'hotkeys': []
            }

            self._save_seeds(coldkey_name, wallet_info)

            base_command = ["btcli", "wallet", "new_hotkey", "--wallet.name", coldkey_name]
            base_inputs = ["~/.bittensor/wallets/", "12"]

            for i in range(num_hotkeys):
                hotkey_name = str(i + 1)
                logger.info(f"Creating hotkey {hotkey_name}")

                command = base_command + ["--wallet.hotkey", hotkey_name]
                _, _, hotkey_address = self._run_btcli(command, base_inputs)

                wallet_info['hotkeys'].append({
                    'name': hotkey_name,
                    'address': hotkey_address,
                    'created_at': datetime.now().isoformat()
                })

                time.sleep(1)

            self._save_seeds(coldkey_name, wallet_info)

            return wallet_info

        except Exception as e:
            logger.error(f"Failed to create wallet {coldkey_name}: {str(e)}")
            raise

    def add_hotkeys(self, coldkey_name: str, num_hotkeys: int) -> Dict:
        try:
            wallet_path = os.path.expanduser(f"~/.bittensor/wallets/{coldkey_name}")
            if not os.path.exists(wallet_path):
                raise Exception(f"Coldkey {coldkey_name} does not exist")

            base_command = ["btcli", "wallet", "new_hotkey", "--wallet.name", coldkey_name]
            base_inputs = ["12"]  # Just the number of words

            wallet_info = self._load_wallet_info(coldkey_name)
            if wallet_info is None:
                wallet_info = {
                    'coldkey': {
                        'name': coldkey_name,
                        'created_at': datetime.now().isoformat()
                    },
                    'hotkeys': []
                }

            for _ in range(num_hotkeys):
                hotkey_name = self._get_next_hotkey_name(coldkey_name)

                command = base_command + ["--wallet.hotkey", hotkey_name]
                _, _, hotkey_address = self._run_btcli(command, base_inputs)

                wallet_info['hotkeys'].append({
                    'name': hotkey_name,
                    'address': hotkey_address,
                    'created_at': datetime.now().isoformat()
                })
                time.sleep(1)

            self._save_seeds(coldkey_name, wallet_info)
            logger.info(f"Seeds saved to data/seeds/{coldkey_name}_seeds.json")

            return wallet_info

        except Exception as e:
            logger.error(f"Failed to add hotkeys to {coldkey_name}: {str(e)}")
            raise

    def _save_seeds(self, coldkey_name: str, wallet_info: Dict):
        try:
            file_path = os.path.join(self.seeds_path, f"{coldkey_name}_seeds.json")
            with open(file_path, 'w') as f:
                json.dump(wallet_info, f, indent=4)
            os.chmod(file_path, 0o600)
            logger.info(f"Saved seeds for {coldkey_name} to {file_path}")

        except Exception as e:
            logger.error(f"Failed to save seeds for {coldkey_name}: {str(e)}")
            raise

    def _load_wallet_info(self, coldkey_name: str) -> Dict:
        try:
            file_path = os.path.join(self.seeds_path, f"{coldkey_name}_seeds.json")
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    return json.load(f)
            return None
        except Exception as e:
            logger.error(f"Failed to load wallet info for {coldkey_name}: {str(e)}")
            return None
            
