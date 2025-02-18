# -*- coding: utf-8 -*-

import bittensor as bt
import os
import subprocess
import re
import time
from typing import Dict, List, Optional, Tuple
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.console import Console
from ..utils.logger import setup_logger
import json
from datetime import datetime
import requests

logger = setup_logger('stats_manager', 'logs/stats_manager.log')
console = Console()

class StatsManager:
    def __init__(self, config):
        self.config = config
        self.subtensor = bt.subtensor()
        self.cache_dir = os.path.expanduser('~/.bittensor/cache')
        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_tao_price(self) -> Optional[float]:
        try:
            response = requests.get('https://api.binance.com/api/v3/ticker/price', params={'symbol': 'TAOUSDT'})
            if response.status_code == 200:
                data = response.json()
                return float(data['price'])
            return None
        except Exception as e:
            logger.error(f"Failed to get TAO price: {e}")
            return None

    def _get_subnet_rate(self, netuid: int) -> float:
        try:
            temp_file = "subnet_output.txt"
            cmd = f'COLUMNS=1000 btcli subnets show --netuid {netuid} > {temp_file}'
            
            process = subprocess.run(cmd, shell=True)
            
            with open(temp_file, 'r') as f:
                output = f.read()
                
            subprocess.run(f'rm {temp_file}', shell=True)
            
            rate_pattern = r'Rate:\s*([\d.]+)\s*τ/ב'
            rate_match = re.search(rate_pattern, output)
            if rate_match:
                return float(rate_match.group(1))
            return 0.0
            
        except Exception as e:
            logger.error(f"Failed to get subnet rate: {e}")
            return 0.0

    def _get_active_subnets(self, wallet_name: str) -> List[int]:
        try:
            temp_file = "overview_output.txt"
            cmd = f'COLUMNS=1000 btcli wallet overview --wallet.name {wallet_name} > {temp_file}'
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    process = subprocess.run(cmd, shell=True)
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    logger.warning(f"Connection error, retrying... ({attempt + 1}/{max_retries})")
                    time.sleep(2)
            
            with open(temp_file, 'r') as f:
                output = f.read()
            
            subprocess.run(f'rm {temp_file}', shell=True)
            
            active_subnets = []
            current_subnet = None
            
            for line in output.split('\n'):
                subnet_match = re.search(r'Subnet:\s*(\d+):', line)
                if subnet_match:
                    current_subnet = int(subnet_match.group(1))
                
                if current_subnet is not None and ('STAKE' in line or 'EMISSION' in line):
                    numbers = re.findall(r'\d+\.\d+|\d+', line)
                    if numbers and any(float(n) > 0 for n in numbers):
                        active_subnets.append(current_subnet)
                        current_subnet = None
            
            return list(set(active_subnets))
            
        except Exception as e:
            logger.error(f"Failed to get active subnets: {e}")
            return []

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

    def _get_emission_data(self, wallet_name: str, netuid: int) -> Tuple[Optional[int], Optional[str]]:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                temp_file = "cli_output.txt"
                cmd = f'COLUMNS=1000 btcli wallet overview --netuid {netuid} --wallet.name {wallet_name} > {temp_file}'
                
                process = subprocess.run(cmd, shell=True)
                
                with open(temp_file, 'r') as f:
                    output = f.read()
                    
                subprocess.run(f'rm {temp_file}', shell=True)

                rho_pattern = u'[\u03C1p](\d+)'
                rho_matches = re.findall(rho_pattern, output)
                if rho_matches:
                    emission_value = int(rho_matches[0])
                    logger.debug(f"Found rho emission value: {emission_value}")
                    return emission_value, output

                emission_pattern = r'EMISSION[^0-9]*(\d+)'
                emission_matches = re.findall(emission_pattern, output)
                if emission_matches:
                    emission_value = int(emission_matches[0])
                    logger.debug(f"Found EMISSION value: {emission_value}")
                    return emission_value, output

                logger.warning(f"No emission value found in output for wallet {wallet_name}")
                return None, output

            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Error getting CLI emission after {max_retries} attempts: {str(e)}")
                    return None, None
                logger.warning(f"Attempt {attempt + 1} failed, retrying...")
                time.sleep(2)

    async def _get_subnet_stats(self, coldkey_name: str, metagraph, netuid: int) -> Optional[Dict]:
        try:
            hotkeys = self._get_wallet_hotkeys(coldkey_name)
            if not hotkeys:
                return None

            subnet_rate = self._get_subnet_rate(netuid)
            alpha_token_price_usd = subnet_rate * self.tao_price if self.tao_price else 0.0

            neurons = []
            total_daily_rewards_alpha = 0
            failed_emissions = []

            for hotkey in hotkeys:
                try:
                    uid = metagraph.hotkeys.index(hotkey['ss58_address'])
                    
                    emission_rao, cli_output = self._get_emission_data(coldkey_name, netuid)
                    
                    if emission_rao is None:
                        try:
                            emission_rao = int(float(metagraph.emission[uid]) * 1e9)
                            logger.debug(f"Using metagraph emission for {hotkey['name']}: {emission_rao}")
                        except Exception as e:
                            logger.error(f"Failed to get metagraph emission: {e}")
                            failed_emissions.append(hotkey['name'])
                            emission_rao = 0

                    daily_rewards_alpha = (emission_rao / 1e9) * 7200
                    total_daily_rewards_alpha += daily_rewards_alpha

                    daily_rewards_usd = daily_rewards_alpha * alpha_token_price_usd

                    neuron_data = {
                        'uid': uid,
                        'stake': float(metagraph.stake[uid]),
                        'rank': float(metagraph.ranks[uid]),
                        'trust': float(metagraph.trust[uid]),
                        'consensus': float(metagraph.consensus[uid]),
                        'incentive': float(metagraph.incentive[uid]),
                        'dividends': float(metagraph.dividends[uid]),
                        'emission': emission_rao,
                        'daily_rewards_alpha': daily_rewards_alpha,
                        'daily_rewards_usd': daily_rewards_usd,
                        'hotkey': hotkey['name']
                    }

                    neurons.append(neuron_data)
                    logger.debug(f"Processed neuron for hotkey {hotkey['name']} in subnet {netuid}")

                except (ValueError, IndexError):
                    logger.debug(f"Hotkey {hotkey['name']} not found in subnet {netuid}")
                    continue
                except Exception as e:
                    logger.error(f"Error processing hotkey {hotkey['name']} in subnet {netuid}: {e}")
                    continue

            if not neurons:
                return None

            subnet_stats = {
                'netuid': netuid,
                'neurons': neurons,
                'stake': sum(n['stake'] for n in neurons),
                'daily_rewards_alpha': total_daily_rewards_alpha,
                'rate_usd': alpha_token_price_usd,
                'failed_emissions': failed_emissions if failed_emissions else None,
                'timestamp': datetime.now().isoformat()
            }

            return subnet_stats

        except Exception as e:
            logger.error(f"Failed to get subnet {netuid} stats: {e}")
            return None

    async def get_wallet_stats(self, coldkey_name: str, subnet_list: Optional[List[int]] = None) -> Dict:
        try:
            self.tao_price = self._get_tao_price()
            logger.info(f"Current TAO price: ${self.tao_price}")

            logger.info(f"Starting to get stats for {coldkey_name}")

            wallet = bt.wallet(name=coldkey_name)
            balance = self.subtensor.get_balance(wallet.coldkeypub.ss58_address)
            logger.debug(f"Got balance for {coldkey_name}: {balance}")

            stats = {
                'coldkey': coldkey_name,
                'wallet_address': wallet.coldkeypub.ss58_address,
                'balance': float(balance),
                'subnets': [],
                'timestamp': datetime.now().isoformat()
            }

            if subnet_list is None:
                subnet_list = self._get_active_subnets(coldkey_name)
                logger.info(f"Found active subnets: {subnet_list}")

            failed_subnets = []
            for netuid in subnet_list:
                try:
                    logger.debug(f"Checking subnet {netuid}")
                    metagraph = self.subtensor.metagraph(netuid)
                    subnet_stats = await self._get_subnet_stats(coldkey_name, metagraph, netuid)
                    
                    if subnet_stats:
                        stats['subnets'].append(subnet_stats)
                except Exception as e:
                    logger.error(f"Error processing subnet {netuid}: {str(e)}")
                    failed_subnets.append(netuid)
                    continue

            if failed_subnets:
                stats['failed_subnets'] = failed_subnets

            logger.info(f"Completed stats collection for {coldkey_name}")
            return stats

        except Exception as e:
            logger.error(f"Failed to get stats for {coldkey_name}: {e}")
            raise
