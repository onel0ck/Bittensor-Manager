import bittensor as bt
import os
from typing import Dict, List, Optional
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.console import Console
from ..utils.logger import setup_logger

logger = setup_logger('stats_manager', 'logs/stats_manager.log')
console = Console()

class StatsManager:
    def __init__(self, config):
        self.config = config
        self.subtensor = bt.subtensor()
        
    def _get_wallet_hotkeys(self, coldkey_name: str) -> List[Dict]:
        try:
            hotkeys_path = os.path.expanduser(f"~/.bittensor/wallets/{coldkey_name}/hotkeys")
            if not os.path.exists(hotkeys_path):
                logger.warning(f"Hotkeys path does not exist: {hotkeys_path}")
                return []

            hotkeys = []
            for hotkey_name in os.listdir(hotkeys_path):
                try:
                    wallet = bt.wallet(name=coldkey_name, hotkey=hotkey_name)
                    ss58_address = wallet.hotkey.ss58_address
                    hotkeys.append({
                        'name': hotkey_name,
                        'ss58_address': ss58_address
                    })
                    logger.debug(f"Found hotkey {hotkey_name} with address {ss58_address}")
                except Exception as e:
                    logger.error(f"Failed to process hotkey {hotkey_name}: {e}")
                    continue

            return hotkeys
        except Exception as e:
            logger.error(f"Failed to get hotkeys for wallet {coldkey_name}: {e}")
            return []

    async def _get_subnet_stats(self, coldkey_name: str, metagraph, netuid: int) -> Optional[Dict]:
        try:
            hotkeys = self._get_wallet_hotkeys(coldkey_name)
            if not hotkeys:
                return None

            neurons = []
            for hotkey in hotkeys:
                try:
                    uid = metagraph.hotkeys.index(hotkey['ss58_address'])
                    neurons.append({
                        'uid': uid,
                        'stake': float(metagraph.stake[uid]),
                        'rank': float(metagraph.ranks[uid]),
                        'trust': float(metagraph.trust[uid]),
                        'consensus': float(metagraph.consensus[uid]),
                        'incentive': float(metagraph.incentive[uid]),
                        'dividends': float(metagraph.dividends[uid]),
                        'emission': float(metagraph.emission[uid]),
                        'hotkey': hotkey['name']
                    })
                    logger.debug(f"Found neuron for hotkey {hotkey['name']} in subnet {netuid}")
                except (ValueError, IndexError):
                    continue
                except Exception as e:
                    logger.error(f"Error processing hotkey {hotkey['name']} in subnet {netuid}: {e}")
                    continue

            if not neurons:
                return None

            total_stake = sum(n['stake'] for n in neurons)
            daily_rewards = sum(n['emission'] * 7200 for n in neurons)

            subnet_stats = {
                'netuid': netuid,
                'neurons': neurons,
                'stake': total_stake,
                'daily_rewards': daily_rewards
            }
            logger.debug(f"Found stats in subnet {netuid}")
            return subnet_stats

        except Exception as e:
            logger.error(f"Failed to get subnet {netuid} stats: {e}")
            return None

    async def get_wallet_stats(self, coldkey_name: str, subnet_list: Optional[List[int]] = None) -> Dict:
        try:
            logger.info(f"Starting to get stats for {coldkey_name}")
            
            wallet = bt.wallet(name=coldkey_name)
            balance = self.subtensor.get_balance(wallet.coldkeypub.ss58_address)
            logger.debug(f"Got balance for {coldkey_name}: {balance}")

            stats = {
                'coldkey': coldkey_name,
                'balance': float(balance),
                'subnets': [],
                'daily_rewards': 0,
                'total_stake': 0
            }

            if subnet_list is None:
                total_subnets = self.subtensor.get_total_subnets()
                logger.info(f"Total number of subnets: {total_subnets}")
                subnet_list = range(total_subnets)

            for netuid in subnet_list:
                try:
                    logger.debug(f"Checking subnet {netuid}")
                    metagraph = self.subtensor.metagraph(netuid)
                    subnet_stats = await self._get_subnet_stats(coldkey_name, metagraph, netuid)
                    if subnet_stats:
                        logger.debug(f"Found stats in subnet {netuid}")
                        stats['subnets'].append(subnet_stats)
                        stats['daily_rewards'] += subnet_stats['daily_rewards']
                        stats['total_stake'] += subnet_stats['stake']
                except Exception as e:
                    logger.error(f"Error processing subnet {netuid}: {str(e)}")
                    continue

            logger.info(f"Final stats: {stats}")
            return stats

        except Exception as e:
            logger.error(f"Failed to get stats for {coldkey_name}: {e}")
            raise