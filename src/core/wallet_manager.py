import os
import json
import pexpect
import time
import bittensor as bt
from typing import Dict
from datetime import datetime
from ..utils.logger import setup_logger

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
            for input_val in inputs:
                index = child.expect([':', '\?', 'words', 'password', 'Retype', 'Overwrite', '(y/N)', 'mnemonic'])
                
                if index in [5, 6]:
                    child.sendline('y')
                    continue

                current_output = child.before.decode('utf-8')
                output += current_output
                
                if "mnemonic" in current_output.lower():
                    for line in current_output.split('\n'):
                        if "mnemonic" in line.lower() and ":" in line:
                            mnemonic = line.split(":", 1)[1].strip()
                            break
                
                child.sendline(input_val)

            child.expect(pexpect.EOF)
            final_output = child.before.decode('utf-8')
            output += final_output

            if not mnemonic:
                for line in output.split('\n'):
                    if "mnemonic" in line.lower() and ":" in line:
                        mnemonic = line.split(":", 1)[1].strip()
                        break

            wallet_name = None
            for i, arg in enumerate(command):
                if arg == '--wallet.name' and i + 1 < len(command):
                    wallet_name = command[i + 1]
                    break

            if not wallet_name:
                raise Exception("Could not find wallet name in command")

            time.sleep(2)

            try:
                if '--wallet.hotkey' not in cmd:
                    wallet = bt.wallet(name=wallet_name)
                    address = wallet.coldkeypub.ss58_address
                else:
                    hotkey_name = None
                    for i, arg in enumerate(command):
                        if arg == '--wallet.hotkey' and i + 1 < len(command):
                            hotkey_name = command[i + 1]
                            break
                    if not hotkey_name:
                        raise Exception("Could not find hotkey name in command")
                    wallet = bt.wallet(name=wallet_name, hotkey=hotkey_name)
                    address = wallet.hotkey.ss58_address
            except Exception as e:
                logger.warning(f"Could not get address immediately, waiting 3 seconds and trying again: {e}")
                time.sleep(3)
                if '--wallet.hotkey' not in cmd:
                    wallet = bt.wallet(name=wallet_name)
                    address = wallet.coldkeypub.ss58_address
                else:
                    hotkey_name = None
                    for i, arg in enumerate(command):
                        if arg == '--wallet.hotkey' and i + 1 < len(command):
                            hotkey_name = command[i + 1]
                            break
                    wallet = bt.wallet(name=wallet_name, hotkey=hotkey_name)
                    address = wallet.hotkey.ss58_address

            logger.debug(f"Output: {output}")
            logger.debug(f"Mnemonic: {mnemonic}")
            logger.debug(f"Address: {address}")

        except Exception as e:
            logger.error(f"Error in _run_btcli: {str(e)}\nCommand: {cmd}\nOutput: {output}")
            raise
        finally:
            child.close(force=True)

        return output, mnemonic, address
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
            base_inputs = ["~/.bittensor/wallets/", "12"]

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
