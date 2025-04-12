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

    def get_unregistered_stakes(self, wallet_name: str) -> Dict[str, Dict]:
        cache_key = f"stake_info_{wallet_name}"
        cached_info = self.data_cache.get(cache_key)
        if cached_info is not None:
            return cached_info
            
        try:
            logs_dir = os.path.expanduser('~/.bittensor/logs')
            os.makedirs(logs_dir, exist_ok=True)
            
            temp_file = "stake_list_output.txt"
            cmd = f'COLUMNS=2000 btcli stake list --wallet.name {wallet_name} --no_prompt > {temp_file}'
            
            subprocess.run(cmd, shell=True)
            
            with open(temp_file, 'r') as f:
                output = f.read()
            
            debug_file = os.path.join(logs_dir, f"stake_list_debug_{wallet_name}.txt")
            with open(debug_file, 'w') as f:
                f.write(output)
            logger.info(f"Saved stake list output to {debug_file}")
            
            subprocess.run(f'rm {temp_file}', shell=True)
            
            stake_info = {}
            
            hotkey_sections = output.split('Hotkey:')
            logger.info(f"Found {len(hotkey_sections)-1} hotkey sections for {wallet_name}")
            
            for idx, section in enumerate(hotkey_sections[1:], 1):
                lines = section.strip().split('\n')
                
                hotkey_line = lines[0]
                hotkey_parts = hotkey_line.strip().split()
                if not hotkey_parts:
                    logger.warning(f"Could not extract hotkey from line: '{hotkey_line}'")
                    continue
                    
                hotkey = hotkey_parts[0].strip()
                logger.info(f"Processing hotkey {idx}: {hotkey}")
                stake_info[hotkey] = {}
                
                table_start = False
                subnet_data = []
                
                for line in lines:
                    if '━━━━' in line:
                        table_start = True
                        continue
                        
                    if table_start and '│' in line and not line.strip().startswith('─') and not 'Total' in line:
                        subnet_data.append(line)
                
                logger.info(f"Found {len(subnet_data)} subnet entries for hotkey {hotkey}")
                
                for subnet_idx, subnet_line in enumerate(subnet_data, 1):
                    parts = subnet_line.split('│')
                    if len(parts) < 7:
                        logger.warning(f"Not enough columns in subnet line {subnet_idx} for hotkey {hotkey}")
                        continue
                        
                    try:
                        netuid_part = parts[0].strip()
                        name_part = parts[1].strip()
                        value_part = parts[2].strip()
                        stake_part = parts[3].strip()
                        price_part = parts[4].strip()
                        registered_part = parts[6].strip() if len(parts) > 6 else ''
                        
                        logger.info(f"Processing subnet {subnet_idx} for hotkey {hotkey}: netuid_part='{netuid_part}', stake='{stake_part}', registered='{registered_part}'")
                        
                        netuid = None
                        digits_only = ''.join(c for c in netuid_part if c.isdigit())
                        if digits_only:
                            netuid = int(digits_only)
                            logger.info(f"Extracted netuid {netuid} from '{netuid_part}'")
                        else:
                            logger.warning(f"Could not extract netuid from '{netuid_part}'")
                            continue
                            
                        alpha_stake = 0.0
                        stake_match = re.search(r'([0-9.]+)', stake_part)
                        if stake_match:
                            try:
                                alpha_stake = float(stake_match.group(1))
                            except ValueError:
                                logger.warning(f"Could not convert '{stake_match.group(1)}' to float")
                        
                        tao_value = 0.0
                        value_match = re.search(r'τ\s+([0-9.]+)', value_part)
                        if value_match:
                            try:
                                tao_value = float(value_match.group(1))
                            except ValueError:
                                logger.warning(f"Could not convert '{value_match.group(1)}' to float")
                        
                        is_registered = 'YES' in registered_part
                        
                        if alpha_stake > 0:
                            stake_info[hotkey][netuid] = {
                                'stake': alpha_stake,
                                'token_name': name_part,
                                'token_symbol': re.sub(r'[0-9.\s]', '', stake_part) if stake_part else "",
                                'token_price': 0.0,
                                'tao_value': tao_value,
                                'is_registered': is_registered
                            }
                            logger.info(f"Added stake for hotkey {hotkey} in subnet {netuid}: stake={alpha_stake}, registered={is_registered}")
                                
                    except Exception as e:
                        logger.error(f"Error parsing stake line for hotkey {hotkey}, subnet {subnet_idx}: {e}")
                        continue
            
            if stake_info:
                self.data_cache.set(cache_key, stake_info)
                
            return stake_info
            
        except Exception as e:
            logger.error(f"Failed to get stakes info: {e}")
            return {}

    def get_all_unregistered_stake_subnets(self, wallet_name: str) -> List[int]:
        """Получает все подсети с незарегистрированными стейками."""
        subnets = set()
        
        try:
            stake_info = self.get_unregistered_stakes(wallet_name)
            
            for hotkey_address, hotkey_stakes in stake_info.items():
                for netuid_key, subnet_stake in hotkey_stakes.items():
                    logger.info(f"Checking stake in subnet {netuid_key} for hotkey {hotkey_address}: stake={subnet_stake.get('stake', 0)}, registered={subnet_stake.get('is_registered', True)}")
                    
                    if subnet_stake.get('stake', 0) > 0 and not subnet_stake.get('is_registered', True):
                        subnets.add(netuid_key)
                        logger.info(f"Found unregistered stake in subnet {netuid_key} for hotkey {hotkey_address}: {subnet_stake.get('stake', 0)}")
            
            result = list(subnets)
            logger.info(f"All subnets with unregistered stakes: {result}")
            return result
        except Exception as e:
            logger.error(f"Error getting unregistered stake subnets: {e}")
            return []

    def _has_unregistered_stake_in_subnet(self, stake_info, hotkey_address, netuid):
        if hotkey_address in stake_info:
            if netuid in stake_info[hotkey_address]:
                return not stake_info[hotkey_address][netuid].get('is_registered', True)
            if str(netuid) in stake_info[hotkey_address]:
                return not stake_info[hotkey_address][str(netuid)].get('is_registered', True)
        return False

    def _get_unregistered_stake_amount(self, stake_info, hotkey_address, netuid):
        if not self._has_unregistered_stake_in_subnet(stake_info, hotkey_address, netuid):
            return 0.0
        
        if netuid in stake_info[hotkey_address]:
            return stake_info[hotkey_address][netuid]['stake']
        
        if str(netuid) in stake_info[hotkey_address]:
            return stake_info[hotkey_address][str(netuid)]['stake']
        
        return 0.0

    def _get_unregistered_stake_for_hotkey(self, coldkey_name: str, hotkey_name: str, netuid: int) -> float:
        try:
            temp_file = "hotkey_stake_info.txt"
            cmd = f'COLUMNS=2000 btcli stake list --wallet.name {coldkey_name} --wallet.hotkey {hotkey_name} > {temp_file}'
            
            subprocess.run(cmd, shell=True)
            
            with open(temp_file, 'r') as f:
                output = f.read()
                
            subprocess.run(f'rm {temp_file}', shell=True)
                
            found_subnet = False
            
            for line in output.split('\n'):
                if not found_subnet:
                    subnet_pattern = rf'^\s*{netuid}\s+\|'
                    if re.search(subnet_pattern, line):
                        found_subnet = True
                        
                        parts = line.split('│')
                        if len(parts) >= 4:
                            stake_part = parts[3].strip()
                            
                            if stake_part:
                                stake_match = re.search(r'([0-9.]+)', stake_part)
                                if stake_match:
                                    return float(stake_match.group(1))
            
            return 0.0
                
        except Exception as e:
            logger.error(f"Error getting unregistered stake for {coldkey_name}:{hotkey_name} in subnet {netuid}: {e}")
            return 0.0

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

    async def _get_subnet_stats(self, coldkey_name: str, netuid: int, include_unregistered: bool = False) -> Optional[Dict]:
        try:
            logger.info(f"Getting stats for subnet {netuid} with include_unregistered={include_unregistered}")
            
            try:
                metagraph = self.subtensor.metagraph(netuid)
                logger.info(f"Successfully loaded metagraph for subnet {netuid}")
            except Exception as e:
                logger.error(f"Error loading metagraph for subnet {netuid}: {e}")
                if include_unregistered:
                    logger.info(f"Will attempt to process unregistered stakes for subnet {netuid} despite metagraph error")
                    metagraph = None
                else:
                    return None
            
            hotkeys = self._get_wallet_hotkeys(coldkey_name)
            if not hotkeys:
                logger.info(f"No hotkeys found for wallet {coldkey_name}")
                return None

            emissions_map = {}
            try:
                emissions_map = self.parse_emission_values(coldkey_name, netuid)
            except Exception as e:
                logger.warning(f"Error parsing emission values for subnet {netuid}: {e}")
            
            unregistered_stakes = []
            
            if include_unregistered:
                logger.info(f"Checking for unregistered stakes in subnet {netuid}")
                stake_info = self.get_unregistered_stakes(coldkey_name)
                
                for hotkey_data in hotkeys:
                    hotkey_name = hotkey_data['name']
                    hotkey_address = hotkey_data['ss58_address']
                    
                    try:
                        uid = -1
                        is_registered = False
                        
                        if metagraph:
                            try:
                                uid = metagraph.hotkeys.index(hotkey_address)
                                is_registered = True
                            except (ValueError, IndexError):
                                pass
                        
                        if not is_registered and hotkey_address in stake_info:
                            found_stake = False
                            
                            if netuid in stake_info[hotkey_address]:
                                subnet_stake = stake_info[hotkey_address][netuid]
                                if subnet_stake.get('stake', 0) > 0 and not subnet_stake.get('is_registered', True):
                                    found_stake = True
                                    unregistered_stakes.append({
                                        'name': hotkey_name,
                                        'address': hotkey_address,
                                        'stake': subnet_stake['stake'],
                                        'uid': -1,
                                        'is_registered': False,
                                        'tao_value': subnet_stake.get('tao_value', 0.0)
                                    })
                                    logger.info(f"Found unregistered stake for {hotkey_name} in subnet {netuid}: {subnet_stake['stake']}")
                            
                            if not found_stake and str(netuid) in stake_info[hotkey_address]:
                                subnet_stake = stake_info[hotkey_address][str(netuid)]
                                if subnet_stake.get('stake', 0) > 0 and not subnet_stake.get('is_registered', True):
                                    unregistered_stakes.append({
                                        'name': hotkey_name,
                                        'address': hotkey_address,
                                        'stake': subnet_stake['stake'],
                                        'uid': -1,
                                        'is_registered': False,
                                        'tao_value': subnet_stake.get('tao_value', 0.0)
                                    })
                                    logger.info(f"Found unregistered stake for {hotkey_name} in subnet {netuid} (string key): {subnet_stake['stake']}")
                    except Exception as e:
                        logger.error(f"Error processing unregistered stake for {hotkey_name} in subnet {netuid}: {e}")
            
            subnet_rate = self._get_subnet_rate(netuid)
            self.tao_price = self._get_tao_price() if not hasattr(self, 'tao_price') or self.tao_price is None else self.tao_price
            alpha_token_price_usd = subnet_rate * self.tao_price if self.tao_price else 0.0

            neurons = []
            total_daily_rewards_alpha = 0
            failed_emissions = []
            
            if metagraph:
                processed_hotkeys = set()
                for hotkey in hotkeys:
                    try:
                        hotkey_registered = True
                        uid = -1
                        try:
                            uid = metagraph.hotkeys.index(hotkey['ss58_address'])
                        except (ValueError, IndexError):
                            hotkey_registered = False
                        
                        if hotkey_registered:
                            emission_rao = emissions_map.get(hotkey['name'], 0)
                            
                            daily_rewards_alpha = (emission_rao / 1e9) * 7200
                            total_daily_rewards_alpha += daily_rewards_alpha
                            daily_rewards_usd = daily_rewards_alpha * alpha_token_price_usd

                            stake_value = float(metagraph.stake[uid]) if uid < len(metagraph.stake) else 0.0
                            
                            neuron_data = {
                                'uid': uid,
                                'stake': stake_value,
                                'rank': float(metagraph.ranks[uid]) if uid < len(metagraph.ranks) else 0.0,
                                'trust': float(metagraph.trust[uid]) if uid < len(metagraph.trust) else 0.0,
                                'consensus': float(metagraph.consensus[uid]) if uid < len(metagraph.consensus) else 0.0,
                                'incentive': float(metagraph.incentive[uid]) if uid < len(metagraph.incentive) else 0.0,
                                'dividends': float(metagraph.dividends[uid]) if uid < len(metagraph.dividends) else 0.0,
                                'emission': emission_rao,
                                'daily_rewards_alpha': daily_rewards_alpha,
                                'daily_rewards_usd': daily_rewards_usd,
                                'hotkey': hotkey['name'],
                                'is_registered': True
                            }
                            
                            neurons.append(neuron_data)
                            processed_hotkeys.add(hotkey['ss58_address'])
                        
                    except Exception as e:
                        logger.error(f"Error processing hotkey {hotkey['name']} in subnet {netuid}: {e}")
                        continue
            
            for stake_data in unregistered_stakes:
                if metagraph is None or stake_data['address'] not in processed_hotkeys:
                    neuron_data = {
                        'uid': -1,
                        'stake': stake_data['stake'],
                        'rank': 0.0,
                        'trust': 0.0,
                        'consensus': 0.0,
                        'incentive': 0.0,
                        'dividends': 0.0,
                        'emission': 0,
                        'daily_rewards_alpha': 0.0,
                        'daily_rewards_usd': 0.0,
                        'hotkey': stake_data['name'],
                        'is_registered': False
                    }
                    neurons.append(neuron_data)

            if not neurons:
                logger.info(f"No neurons found for subnet {netuid}")
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

            logger.info(f"Successfully generated stats for subnet {netuid} with {len(neurons)} neurons")
            return subnet_stats

        except Exception as e:
            logger.error(f"Failed to get subnet {netuid} stats: {e}")
            return None

    def _has_unregistered_stake_in_subnet(self, stake_info, hotkey_address, netuid):
        if hotkey_address in stake_info:
            if netuid in stake_info[hotkey_address]:
                return not stake_info[hotkey_address][netuid].get('is_registered', True)
            if str(netuid) in stake_info[hotkey_address]:
                return not stake_info[hotkey_address][str(netuid)].get('is_registered', True)
        return False

    def _get_unregistered_stake_amount(self, stake_info, hotkey_address, netuid):
        if not self._has_unregistered_stake_in_subnet(stake_info, hotkey_address, netuid):
            return 0.0
        
        if netuid in stake_info[hotkey_address]:
            return stake_info[hotkey_address][netuid]['stake']
        
        if str(netuid) in stake_info[hotkey_address]:
            return stake_info[hotkey_address][str(netuid)]['stake']
        
        return 0.0
            
    async def get_wallet_stats(self, coldkey_name: str, subnet_list: Optional[List[int]] = None, hide_zeros: bool = False, include_unregistered: bool = False) -> Dict:
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

            active_subnets = set()
            if subnet_list is None:
                direct_subnets = self.get_active_subnets_direct(coldkey_name)
                active_subnets.update(direct_subnets)
                logger.info(f"Found {len(direct_subnets)} active subnets via direct method: {direct_subnets}")
                
                if include_unregistered:
                    unregistered_subnets = self.get_all_unregistered_stake_subnets(coldkey_name)
                    
                    if unregistered_subnets:
                        logger.info(f"Found {len(unregistered_subnets)} subnets with unregistered stake for {coldkey_name}: {unregistered_subnets}")
                        unregistered_subnets_int = [int(netuid) for netuid in unregistered_subnets]
                        active_subnets.update(unregistered_subnets_int)
                        logger.info(f"Updated active subnets list to include unregistered stakes: {list(active_subnets)}")
            else:
                for subnet_id in subnet_list:
                    if isinstance(subnet_id, str) and subnet_id.isdigit():
                        active_subnets.add(int(subnet_id))
                    elif isinstance(subnet_id, int):
                        active_subnets.add(subnet_id)
            
            if not active_subnets:
                logger.warning(f"No active subnets found for {coldkey_name}")
                return stats
                
            subnet_list = list(active_subnets)
            logger.info(f"Final list of subnets to check: {subnet_list}")

            parallel_enabled = self.config.get('stats.parallel_requests', True)
            max_concurrent = self.config.get('stats.max_concurrent_tasks', 5)
            failed_subnets = []

            if parallel_enabled:
                tasks = []
                for subnet_id in subnet_list:
                    task = asyncio.create_task(self._get_subnet_stats(coldkey_name, subnet_id, include_unregistered))
                    tasks.append((subnet_id, task))
                
                for i in range(0, len(tasks), max_concurrent):
                    batch = tasks[i:i+max_concurrent]
                    
                    for subnet_id, task in batch:
                        try:
                            subnet_stats = await task
                            if subnet_stats:
                                if hide_zeros:
                                    subnet_stats['neurons'] = [n for n in subnet_stats['neurons'] 
                                                            if n['stake'] > 0 or n.get('emission', 0) > 0]
                                    
                                if subnet_stats['neurons']:
                                    stats['subnets'].append(subnet_stats)
                        except Exception as e:
                            logger.error(f"Error processing subnet {subnet_id}: {e}")
                            failed_subnets.append(subnet_id)
            else:
                for subnet_id in subnet_list:
                    try:
                        subnet_stats = await self._get_subnet_stats(coldkey_name, subnet_id, include_unregistered)
                        
                        if subnet_stats:
                            if hide_zeros:
                                subnet_stats['neurons'] = [n for n in subnet_stats['neurons'] 
                                                        if n['stake'] > 0 or n.get('emission', 0) > 0]
                                
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

    def _get_active_subnets_with_stats(self, wallet_name: str) -> List[int]:
        try:
            if hasattr(self, 'stats_manager') and self.stats_manager is not None:
                registered_subnets = self.stats_manager.get_active_subnets_direct(wallet_name)
                logger.info(f"Found registered subnets via StatsManager: {registered_subnets}")
                
                unregistered_subnets = self.stats_manager.get_all_unregistered_stake_subnets(wallet_name)
                logger.info(f"Found unregistered subnets via StatsManager: {unregistered_subnets}")
                
                all_subnets = list(set(registered_subnets + unregistered_subnets))
                logger.info(f"Combined subnet list from StatsManager: {all_subnets}")
                
                return all_subnets
            else:
                logger.warning("StatsManager not available, using original method")
                return self._get_active_subnets(wallet_name)
        except Exception as e:
            logger.error(f"Error getting subnets via StatsManager: {e}")
            return self._get_active_subnets(wallet_name)
