import os
import bittensor as bt
from typing import Dict, List, Optional, Tuple
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from ..utils.logger import setup_logger
import time

logger = setup_logger('transfer_manager', 'logs/transfer_manager.log')
console = Console()

class TransferManager:
    def __init__(self, config):
        self.config = config
        self.subtensor = bt.subtensor()

    def verify_wallet_password(self, coldkey: str, password: str) -> bool:
        try:
            wallet = bt.wallet(name=coldkey)
            wallet.coldkey_file.decrypt(password)
            return True
        except Exception as e:
            logger.error(f"Failed to verify password for wallet {coldkey}: {e}")
            return False

    def get_stake_info(self, coldkey_name: str) -> Dict:
        try:
            wallet = bt.wallet(name=coldkey_name)
            metagraph = self.subtensor.metagraph(netuid=1)
            
            stake_info = {
                'total_stake': 0,
                'hotkeys': []
            }
            
            hotkeys_path = f"~/.bittensor/wallets/{coldkey_name}/hotkeys"
            wallet_hotkeys = []
            
            for hotkey_name in os.listdir(os.path.expanduser(hotkeys_path)):
                try:
                    hotkey_wallet = bt.wallet(name=coldkey_name, hotkey=hotkey_name)
                    hotkey_info = {
                        'name': hotkey_name,
                        'address': hotkey_wallet.hotkey.ss58_address,
                        'stake': 0
                    }
                    
                    try:
                        uid = metagraph.hotkeys.index(hotkey_wallet.hotkey.ss58_address)
                        stake = float(metagraph.stake[uid])
                        hotkey_info['stake'] = stake
                        stake_info['total_stake'] += stake
                    except ValueError:
                        pass
                    
                    stake_info['hotkeys'].append(hotkey_info)
                    
                except Exception as e:
                    logger.error(f"Error processing hotkey {hotkey_name}: {e}")
                    continue
            
            return stake_info
            
        except Exception as e:
            logger.error(f"Error getting stake info for {coldkey_name}: {e}")
            raise

    def unstake_from_hotkey(self, coldkey_name: str, hotkey_name: str, amount: Optional[float] = None, password: str = None) -> bool:
        try:
            wallet = bt.wallet(name=coldkey_name, hotkey=hotkey_name)
            if password:
                wallet.coldkey_file.decrypt(password)
            
            if amount is None:
                success = self.subtensor.unstake_all(
                    wallet=wallet,
                    wait_for_inclusion=True,
                    wait_for_finalization=True
                )
            else:
                success = self.subtensor.unstake(
                    wallet=wallet,
                    amount=amount,
                    wait_for_inclusion=True,
                    wait_for_finalization=True
                )
            
            return success
            
        except Exception as e:
            logger.error(f"Error unstaking from {coldkey_name}:{hotkey_name}: {e}")
            return False

    def unstake_all(self, coldkey_name: str, password: str = None) -> bool:
        try:
            stake_info = self.get_stake_info(coldkey_name)
            success = True
            
            for hotkey in stake_info['hotkeys']:
                if hotkey['stake'] > 0:
                    if not self.unstake_from_hotkey(coldkey_name, hotkey['name'], password=password):
                        success = False
                    time.sleep(2)
                    
            return success
            
        except Exception as e:
            logger.error(f"Error unstaking all from {coldkey_name}: {e}")
            return False

    def transfer_tao(self, from_coldkey: str, to_address: str, amount: float, password: str) -> bool:
        try:
            wallet = bt.wallet(name=from_coldkey)
            wallet.coldkey_file.decrypt(password)

            success = self.subtensor.transfer(
                wallet=wallet,
                dest=to_address,
                amount=amount,
                wait_for_inclusion=True,
                wait_for_finalization=True
            )

            return success

        except Exception as e:
            logger.error(f"Error transferring TAO from {from_coldkey}: {e}")
            return False

    def display_stake_summary(self, stake_info: Dict):
        table = Table(title="Staking Summary")
        table.add_column("Hotkey")
        table.add_column("Stake (τ)")
        table.add_column("Address")
        
        for hotkey in stake_info['hotkeys']:
            if hotkey['stake'] > 0:
                table.add_row(
                    hotkey['name'],
                    f"{hotkey['stake']:.9f}",
                    hotkey['address']
                )
                
        table.add_row(
            "[bold]Total[/bold]",
            f"[bold]{stake_info['total_stake']:.9f}[/bold]",
            "",
            style="bold green"
        )
        
        console.print(table)