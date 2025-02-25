# -*- coding: utf-8 -*-

import bittensor as bt
import os
import subprocess
import re
import time
import asyncio
from typing import Dict, List, Optional, Tuple
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.console import Console
from ..utils.logger import setup_logger
import json
from datetime import datetime
import requests

logger = setup_logger('stats_manager', 'logs/stats_manager.log')
console = Console()

class DataCache:
    def __init__(self, ttl_seconds=300):
        self.cache = {}
        self.ttl_seconds = ttl_seconds
    
    def get(self, key):
        if key in self.cache:
            entry = self.cache[key]
            if time.time() - entry['timestamp'] < self.ttl_seconds:
                return entry['data']
        return None
    
    def set(self, key, data):
        self.cache[key] = {
            'data': data,
            'timestamp': time.time()
        }
    
    def clear(self):
        self.cache = {}

class StatsManager:
    def __init__(self, config):
        self.config = config
        self.subtensor = bt.subtensor()
        self.cache_dir = os.path.expanduser('~/.bittensor/cache')
        os.makedirs(self.cache_dir, exist_ok=True)
        
        cache_ttl = self.config.get('cache.ttl_seconds', 300)
        price_ttl = self.config.get('cache.price_ttl_seconds', 60)
        
        self.data_cache = DataCache(ttl_seconds=cache_ttl)
        self.tao_price_cache = DataCache(ttl_seconds=price_ttl)

    def _get_tao_price(self) -> Optional[float]:
        cached_price = self.tao_price_cache.get('tao_price')
        if cached_price is not None:
            return cached_price
            
        try:
            try:
                response = requests.get(
                    'https://api.coingecko.com/api/v3/simple/price',
                    params={'ids': 'bittensor', 'vs_currencies': 'usd'},
                    timeout=5
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if 'bittensor' in data and 'usd' in data['bittensor']:
                        price = float(data['bittensor']['usd'])
                        logger.info(f"Got TAO price from CoinGecko: ${price}")
                        self.tao_price_cache.set('tao_price', price)
                        return price
            except Exception as e:
                logger.warning(f"Failed to get TAO price from CoinGecko: {e}")
            
            try:
                response = requests.get(
                    'https://api.binance.com/api/v3/ticker/price',
                    params={'symbol': 'TAOUSDT'},
                    timeout=5
                )
                
                if response.status_code == 200:
                    data = response.json()
                    price = float(data['price'])
                    logger.info(f"Got TAO price from Binance: ${price}")
                    self.tao_price_cache.set('tao_price', price)
                    return price
            except Exception as e:
                logger.warning(f"Failed to get TAO price from Binance: {e}")
                
            try:
                api_key = self.config.get('taostats.api_key')
                if api_key:
                    url = f"{self.config.get('taostats.api_url', 'https://api.taostats.io/api')}/prices/latest/v1"
                    headers = {
                        "accept": "application/json",
                        "Authorization": api_key
                    }
                    
                    response = requests.get(url, headers=headers, timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        price = float(data['data'][0]['usd'])
                        logger.info(f"Got TAO price from TaoStats: ${price}")
                        self.tao_price_cache.set('tao_price', price)
                        return price
            except Exception as e:
                logger.warning(f"Failed to get TAO price from TaoStats: {e}")
            
            logger.error("All price sources failed")
            return None
        except Exception as e:
            logger.error(f"Error in _get_tao_price: {e}")
            return None

    def get_active_subnets_direct(self, wallet_name: str) -> List[int]:
        cache_key = f"active_subnets_{wallet_name}"
        cached_data = self.data_cache.get(cache_key)
        if cached_data is not None:
            return cached_data
            
        try:
            cmd = f'btcli wallet overview --wallet.name {wallet_name}'
            process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if process.returncode != 0:
                logger.error(f"Error executing command: {process.stderr}")
                return []
                
            output = process.stdout
            
            subnet_pattern = r'Subnet: (\d+):'
            subnet_matches = re.finditer(subnet_pattern, output)
            
            active_subnets = []
            for match in subnet_matches:
                subnet_id = int(match.group(1))
                active_subnets.append(subnet_id)
            
            if active_subnets:
                self.data_cache.set(cache_key, active_subnets)
                
            return active_subnets
            
        except Exception as e:
            logger.error(f"Error getting active subnets: {e}")
            return []

    def _get_subnet_rate(self, netuid: int) -> float:
        try:
            cache_key = f"subnet_rate_{netuid}"
            cached_rate = self.data_cache.get(cache_key)
            if cached_rate is not None:
                return cached_rate
                
            cmd = f'btcli subnets show --netuid {netuid}'
            process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if process.returncode != 0:
                logger.error(f"Error executing command: {process.stderr}")
                return 0.0
                
            output = process.stdout
            
            rate_pattern = r'Rate:\s*([\d.]+)'
            rate_match = re.search(rate_pattern, output)
            if rate_match:
                rate = float(rate_match.group(1))
                self.data_cache.set(cache_key, rate)
                return rate
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Failed to get subnet rate: {e}")
            return 0.0

    def _get_wallet_hotkeys(self, coldkey_name: str) -> List[Dict]:
        try:
            cache_key = f"wallet_hotkeys_{coldkey_name}"
            cached_hotkeys = self.data_cache.get(cache_key)
            if cached_hotkeys is not None:
                return cached_hotkeys
                
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

            if hotkeys:
                self.data_cache.set(cache_key, hotkeys)
                
            return hotkeys
        except Exception as e:
            logger.error(f"Failed to get hotkeys for wallet {coldkey_name}: {e}")
            return []

    def parse_emission_values(self, wallet_name: str, netuid: int) -> Dict[str, int]:
        try:
            cache_key = f"emissions_{wallet_name}_{netuid}"
            cached_emissions = self.data_cache.get(cache_key)
            if cached_emissions is not None:
                return cached_emissions
                
            cmd = f'COLUMNS=1000 btcli wallet overview --wallet.name {wallet_name} --netuid {netuid}'
            process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if process.returncode != 0:
                logger.error(f"Error executing command: {process.stderr}")
                return {}
                
            output = process.stdout
            
            emissions = {}
            
            lines = output.split('\n')
            for line in lines:
                line_stripped = line.strip()
                if line_stripped.startswith(wallet_name):
                    parts = line.split()
                    if len(parts) < 10:
                        continue
                        
                    try:
                        hotkey_name = parts[1]
                        emission_str = parts[10]
                        
                        if '.' in emission_str:
                            emission_integer_part = emission_str.split('.')[0]
                            integer_digits = re.sub(r'[^0-9]', '', emission_integer_part)
                            if integer_digits:
                                emissions[hotkey_name] = int(integer_digits)
                        else:
                            emission_digits = re.sub(r'[^0-9]', '', emission_str)
                            if emission_digits:
                                emissions[hotkey_name] = int(emission_digits)
                            
                    except Exception as e:
                        logger.error(f"Error parsing line: {line}, Error: {e}")
            
            if not emissions:
                total_line = None
                for i, line in enumerate(lines):
                    if "ρ" in line or "p" in line:
                        total_line = line
                        break
                
                if total_line:
                    rho_match = re.search(r'[pρ](\d+)', total_line)
                    if rho_match:
                        total_emission = int(rho_match.group(1))
                        logger.info(f"Found total emission: {total_emission}, but can't assign to individual hotkeys")
                        
                        hotkeys = self._get_hotkeys_in_subnet(wallet_name, netuid)
                        if hotkeys and len(hotkeys) > 0:
                            avg_emission = total_emission // len(hotkeys)
                            for hotkey in hotkeys:
                                emissions[hotkey] = avg_emission
            
            if emissions:
                self.data_cache.set(cache_key, emissions)
                
            return emissions
            
        except Exception as e:
            logger.error(f"Error parsing emission values: {e}")
            return {}

    def _get_hotkeys_in_subnet(self, wallet_name: str, netuid: int) -> List[str]:
        try:
            cmd = f'btcli wallet overview --wallet.name {wallet_name} --netuid {netuid}'
            process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if process.returncode != 0:
                return []
                
            output = process.stdout
            
            hotkeys = []
            lines = output.split('\n')
            for line in lines:
                if line.strip().startswith(wallet_name):
                    parts = line.split()
                    if len(parts) >= 2:
                        hotkeys.append(parts[1])
                        
            return hotkeys
            
        except Exception as e:
            logger.error(f"Error getting hotkeys in subnet: {e}")
            return []

    async def _get_subnet_stats(self, coldkey_name: str, netuid: int) -> Optional[Dict]:
        try:
            metagraph = self.subtensor.metagraph(netuid)
            
            hotkeys = self._get_wallet_hotkeys(coldkey_name)
            if not hotkeys:
                return None

            emissions_map = self.parse_emission_values(coldkey_name, netuid)
            
            subnet_rate = self._get_subnet_rate(netuid)
            self.tao_price = self._get_tao_price() if not hasattr(self, 'tao_price') or self.tao_price is None else self.tao_price
            alpha_token_price_usd = subnet_rate * self.tao_price if self.tao_price else 0.0

            neurons = []
            total_daily_rewards_alpha = 0
            failed_emissions = []

            for hotkey in hotkeys:
                try:
                    try:
                        uid = metagraph.hotkeys.index(hotkey['ss58_address'])
                    except (ValueError, IndexError):
                        logger.debug(f"Hotkey {hotkey['name']} not found in subnet {netuid}")
                        continue

                    emission_rao = emissions_map.get(hotkey['name'], 0)
                    
                    daily_rewards_alpha = (emission_rao / 1e9) * 7200
                    total_daily_rewards_alpha += daily_rewards_alpha
                    daily_rewards_usd = daily_rewards_alpha * alpha_token_price_usd

                    neuron_data = {
                        'uid': uid,
                        'stake': float(metagraph.stake[uid]) if uid < len(metagraph.stake) else 0.0,
                        'rank': float(metagraph.ranks[uid]) if uid < len(metagraph.ranks) else 0.0,
                        'trust': float(metagraph.trust[uid]) if uid < len(metagraph.trust) else 0.0,
                        'consensus': float(metagraph.consensus[uid]) if uid < len(metagraph.consensus) else 0.0,
                        'incentive': float(metagraph.incentive[uid]) if uid < len(metagraph.incentive) else 0.0,
                        'dividends': float(metagraph.dividends[uid]) if uid < len(metagraph.dividends) else 0.0,
                        'emission': emission_rao,
                        'daily_rewards_alpha': daily_rewards_alpha,
                        'daily_rewards_usd': daily_rewards_usd,
                        'hotkey': hotkey['name']
                    }

                    neurons.append(neuron_data)
                    logger.debug(f"Processed neuron for hotkey {hotkey['name']} in subnet {netuid}")

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

    async def get_wallet_stats(self, coldkey_name: str, subnet_list: Optional[List[int]] = None, hide_zeros: bool = False) -> Dict:
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
                subnet_list = self.get_active_subnets_direct(coldkey_name)
                logger.info(f"Found active subnets: {subnet_list}")

            parallel_enabled = self.config.get('stats.parallel_requests', True)
            max_concurrent = self.config.get('stats.max_concurrent_tasks', 5)
            failed_subnets = []

            if parallel_enabled:
                tasks = []
                for subnet_id in subnet_list:
                    task = asyncio.create_task(self._get_subnet_stats(coldkey_name, subnet_id))
                    tasks.append((subnet_id, task))
                
                for i in range(0, len(tasks), max_concurrent):
                    batch = tasks[i:i+max_concurrent]
                    
                    for subnet_id, task in batch:
                        try:
                            subnet_stats = await task
                            if subnet_stats:
                                if hide_zeros:
                                    subnet_stats['neurons'] = [n for n in subnet_stats['neurons'] 
                                                            if n['stake'] > 0 or n['emission'] > 0]
                                    
                                if subnet_stats['neurons']:
                                    stats['subnets'].append(subnet_stats)
                        except Exception as e:
                            logger.error(f"Error processing subnet {subnet_id}: {e}")
                            failed_subnets.append(subnet_id)
            else:
                for subnet_id in subnet_list:
                    try:
                        subnet_stats = await self._get_subnet_stats(coldkey_name, subnet_id)
                        
                        if subnet_stats:
                            if hide_zeros:
                                subnet_stats['neurons'] = [n for n in subnet_stats['neurons'] 
                                                        if n['stake'] > 0 or n['emission'] > 0]
                                
                            if subnet_stats['neurons']:
                                stats['subnets'].append(subnet_stats)
                    except Exception as e:
                        logger.error(f"Error processing subnet {subnet_id}: {e}")
                        failed_subnets.append(subnet_id)

            if failed_subnets:
                stats['failed_subnets'] = failed_subnets

            stats['subnets'].sort(key=lambda x: sum(n['stake'] for n in x['neurons']), reverse=True)

            logger.info(f"Completed stats collection for {coldkey_name}")
            return stats

        except Exception as e:
            logger.error(f"Failed to get stats for {coldkey_name}: {e}")
            raise

    def _get_active_subnets_fallback(self, wallet_name: str) -> List[int]:
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
