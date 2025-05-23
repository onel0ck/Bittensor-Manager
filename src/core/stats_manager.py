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
            cmd = f'btcli wallet overview --wallet.name {wallet_name} --json-output'
            process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if process.returncode != 0:
                logger.error(f"Error executing command: {process.stderr}")
                return []
                
            try:
                data = json.loads(process.stdout)
                active_subnets = []
                
                if 'subnets' in data:
                    for subnet in data['subnets']:
                        netuid = subnet.get('netuid')
                        if netuid is not None:
                            active_subnets.append(int(netuid))
                
                if active_subnets:
                    self.data_cache.set(cache_key, active_subnets)
                    logger.info(f"Found {len(active_subnets)} active subnets for {wallet_name}: {active_subnets}")
                
                return active_subnets
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON output from 'btcli wallet overview'")
                return []
                
        except Exception as e:
            logger.error(f"Error getting active subnets: {e}")
            return []

    def get_unregistered_stakes(self, wallet_name: str) -> Dict[str, Dict]:
        cache_key = f"stake_info_{wallet_name}"
        cached_info = self.data_cache.get(cache_key)
        if cached_info is not None:
            return cached_info
            
        try:
            logger.info(f"Getting stake info for {wallet_name}")
            
            cmd = f'btcli stake list --wallet.name {wallet_name} --json-output'
            process = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            
            if process.returncode != 0:
                logger.warning(f"btcli stake list failed for {wallet_name}: {process.stderr}")
                return self._fallback_stake_parsing(wallet_name)
                
            output = process.stdout.strip()
            if not output:
                logger.warning(f"Empty output from btcli stake list for {wallet_name}")
                return self._fallback_stake_parsing(wallet_name)
                
            try:
                output = re.sub(r'\\u[0-9a-fA-F]{4}', 'X', output)
                output = re.sub(r'[\x00-\x1F\x7F]', '', output)
                
                data = json.loads(output)
                stake_info = {}
                
                if 'stake_info' in data and data['stake_info']:
                    for hotkey_address, subnets in data['stake_info'].items():
                        stake_info[hotkey_address] = {}
                        
                        for subnet_data in subnets:
                            netuid = subnet_data.get('netuid')
                            if netuid is not None:
                                stake_info[hotkey_address][netuid] = {
                                    'stake': float(subnet_data.get('stake_value', 0.0)),
                                    'token_name': subnet_data.get('subnet_name', f"Subnet {netuid}"),
                                    'token_symbol': '',
                                    'token_price': float(subnet_data.get('rate', 0.0)),
                                    'tao_value': float(subnet_data.get('value', 0.0)),
                                    'is_registered': bool(subnet_data.get('registered', True))
                                }
                
                if stake_info:
                    self.data_cache.set(cache_key, stake_info)
                    logger.info(f"Successfully parsed JSON stake info for {wallet_name}")
                    return stake_info
                else:
                    logger.warning(f"No stake info found in JSON for {wallet_name}")
                    return self._fallback_stake_parsing(wallet_name)
                    
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse failed for {wallet_name}: {e}")
                return self._fallback_stake_parsing(wallet_name)
                
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout getting stake info for {wallet_name}")
            return {}
        except Exception as e:
            logger.error(f"Error getting stake info for {wallet_name}: {e}")
            return {}

    def _fallback_stake_parsing(self, wallet_name: str) -> Dict[str, Dict]:
        try:
            logger.info(f"Using fallback parsing for {wallet_name}")
            
            temp_file = f"/tmp/stake_list_{wallet_name}_{int(time.time())}.txt"
            cmd = f'btcli stake list --wallet.name {wallet_name} > {temp_file} 2>/dev/null'
            
            result = subprocess.run(cmd, shell=True, timeout=30)
            
            if not os.path.exists(temp_file):
                logger.warning(f"Temp file not created for {wallet_name}")
                return {}
                
            stake_info = {}
            
            with open(temp_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            os.remove(temp_file)
            
            if not content.strip():
                logger.warning(f"Empty content from fallback for {wallet_name}")
                return {}
                
            hotkey_sections = content.split('Hotkey:')
            
            for section in hotkey_sections[1:]:
                lines = section.strip().split('\n')
                if not lines:
                    continue
                    
                hotkey_line = lines[0].strip()
                hotkey_parts = hotkey_line.split()
                if not hotkey_parts:
                    continue
                    
                hotkey_address = hotkey_parts[0]
                if not hotkey_address.startswith('5'):
                    continue
                    
                stake_info[hotkey_address] = {}
                
                in_table = False
                for line in lines[1:]:
                    line = line.strip()
                    
                    if not line:
                        continue
                        
                    if '─' in line or '━' in line:
                        in_table = True
                        continue
                        
                    if not in_table:
                        continue
                        
                    if 'Total' in line or line.startswith('─') or line.startswith('━'):
                        continue
                        
                    parts = re.split(r'[│|]', line)
                    if len(parts) < 4:
                        continue
                        
                    try:
                        netuid_text = parts[0].strip()
                        netuid_match = re.search(r'(\d+)', netuid_text)
                        if not netuid_match:
                            continue
                            
                        netuid = int(netuid_match.group(1))
                        
                        name_text = parts[1].strip() if len(parts) > 1 else f"Subnet {netuid}"
                        stake_text = parts[3].strip() if len(parts) > 3 else "0"
                        registered_text = parts[6].strip() if len(parts) > 6 else "NO"
                        
                        stake_match = re.search(r'([\d.]+)', stake_text)
                        stake_value = float(stake_match.group(1)) if stake_match else 0.0
                        
                        is_registered = any(word in registered_text.upper() for word in ['YES', 'TRUE', '✓'])
                        
                        if stake_value > 0:
                            stake_info[hotkey_address][netuid] = {
                                'stake': stake_value,
                                'token_name': name_text,
                                'token_symbol': '',
                                'token_price': 0.0,
                                'tao_value': 0.0,
                                'is_registered': is_registered
                            }
                            
                    except (ValueError, IndexError) as e:
                        continue
            
            if stake_info:
                self.data_cache.set(f"stake_info_{wallet_name}", stake_info)
                logger.info(f"Fallback parsing successful for {wallet_name}")
            else:
                logger.warning(f"No stake info found via fallback for {wallet_name}")
                
            return stake_info
            
        except Exception as e:
            logger.error(f"Fallback parsing failed for {wallet_name}: {e}")
            return {}

    def get_all_unregistered_stake_subnets(self, wallet_name: str) -> List[int]:
        subnets = set()
        
        try:
            stake_info = self.get_unregistered_stakes(wallet_name)
            
            for hotkey_address, hotkey_stakes in stake_info.items():
                for netuid_key, subnet_stake in hotkey_stakes.items():
                    if subnet_stake.get('stake', 0) > 0 and not subnet_stake.get('is_registered', True):
                        subnets.add(netuid_key)
                        logger.info(f"Found unregistered stake in subnet {netuid_key} for hotkey {hotkey_address}: {subnet_stake.get('stake', 0)}")
            
            result = list(subnets)
            logger.info(f"All subnets with unregistered stakes for {wallet_name}: {result}")
            return result
        except Exception as e:
            logger.error(f"Error getting unregistered stake subnets: {e}")
            return []

    def _get_subnet_rate(self, netuid: int) -> float:
        try:
            cache_key = f"subnet_rate_{netuid}"
            cached_rate = self.data_cache.get(cache_key)
            if cached_rate is not None:
                return cached_rate
                
            cmd = f'btcli subnets show --netuid {netuid} --json-output'
            process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if process.returncode != 0:
                logger.error(f"Error executing command: {process.stderr}")
                return 0.0
                
            try:
                data = json.loads(process.stdout)
                rate = float(data.get('rate', 0.0))
                
                self.data_cache.set(cache_key, rate)
                logger.info(f"Got rate for subnet {netuid}: {rate}")
                
                return rate
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON output from 'btcli subnets show'")
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

    def _get_wallet_overview_json(self, coldkey_name: str, netuid: Optional[int] = None) -> Optional[Dict]:
        try:
            netuid_param = f"--netuid {netuid}" if netuid is not None else ""
            cmd = f'btcli wallet overview --wallet.name {coldkey_name} {netuid_param} --json-output'
            process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if process.returncode != 0:
                logger.error(f"Error executing command: {process.stderr}")
                return None
                
            try:
                data = json.loads(process.stdout)
                return data
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON output from 'btcli wallet overview': {e}")
                
                output = process.stdout
                output = ''.join(char for char in output if ord(char) >= 32 or char in '\n\r\t')
                output = output.replace('\\u0', '\\\\u0')
                
                try:
                    data = json.loads(output)
                    return data
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse JSON output from 'btcli wallet overview' after cleaning")
                    return None
                    
        except Exception as e:
            logger.error(f"Error getting wallet overview: {e}")
            return None

    async def _get_subnet_stats(self, coldkey_name: str, netuid: int, include_unregistered: bool = False) -> Optional[Dict]:
        try:
            logger.info(f"Getting stats for subnet {netuid} with include_unregistered={include_unregistered}")
            
            subnet_name = ""
            subnet_symbol = ""
            subnet_rate = 0.0
            
            wallet_overview = self._get_wallet_overview_json(coldkey_name, netuid)
            if not wallet_overview:
                logger.warning(f"Failed to get wallet overview for {coldkey_name}")
                return None
                
            subnet_info = None
            for subnet in wallet_overview.get('subnets', []):
                if subnet.get('netuid') == netuid:
                    subnet_info = subnet
                    subnet_name = subnet.get('name', '')
                    subnet_symbol = subnet.get('symbol', '')
                    break
            
            if not subnet_info and not include_unregistered:
                logger.info(f"No subnet {netuid} found in wallet overview for {coldkey_name}")
                return None
            
            stake_info = self.get_unregistered_stakes(coldkey_name)
            
            for hotkey_address, hotkey_data in stake_info.items():
                if netuid in hotkey_data:
                    subnet_rate = float(hotkey_data[netuid].get('rate', 0.0))
                    if subnet_rate > 0:
                        logger.info(f"Got rate {subnet_rate} for subnet {netuid} from stake list")
                        break
                elif str(netuid) in hotkey_data:
                    subnet_rate = float(hotkey_data[str(netuid)].get('rate', 0.0))
                    if subnet_rate > 0:
                        logger.info(f"Got rate {subnet_rate} for subnet {netuid} from stake list (string key)")
                        break
            
            if subnet_rate == 0.0:
                try:
                    cmd = f'btcli subnets show --netuid {netuid} --json-output'
                    process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    
                    if process.returncode == 0:
                        output = process.stdout
                        output = ''.join(char for char in output if ord(char) >= 32 or char in '\n\r\t')
                        
                        rate_match = re.search(r'"rate":\s*([\d.]+)', output)
                        if rate_match:
                            try:
                                subnet_rate = float(rate_match.group(1))
                                logger.info(f"Got rate {subnet_rate} for subnet {netuid} from subnets show")
                            except (ValueError, IndexError):
                                pass
                        
                        if not subnet_name:
                            name_match = re.search(r'"name":\s*"([^"]+)"', output)
                            if name_match:
                                subnet_name = name_match.group(1)
                                logger.info(f"Got name '{subnet_name}' for subnet {netuid} from subnets show")
                        
                        if not subnet_symbol:
                            symbol_match = re.search(r'"symbol":\s*"([^"]+)"', output)
                            if symbol_match:
                                subnet_symbol = symbol_match.group(1)
                                logger.info(f"Got symbol '{subnet_symbol}' for subnet {netuid} from subnets show")
                except Exception as e:
                    logger.error(f"Error getting subnet info from subnets show: {e}")
            
            self.tao_price = self._get_tao_price() if not hasattr(self, 'tao_price') or self.tao_price is None else self.tao_price
            alpha_token_price_usd = subnet_rate * self.tao_price if self.tao_price else 0.0
            
            neurons = []
            total_daily_rewards_alpha = 0
            
            if subnet_info and 'neurons' in subnet_info:
                for neuron in subnet_info['neurons']:
                    hotkey_name = neuron.get('hotkey')
                    uid = neuron.get('uid', -1)
                    
                    stake_value = float(neuron.get('stake', 0.0))
                    
                    emission_rao = int(neuron.get('emission', 0))
                    daily_rewards_alpha = (emission_rao / 1e9) * 7200
                    total_daily_rewards_alpha += daily_rewards_alpha
                    daily_rewards_usd = daily_rewards_alpha * alpha_token_price_usd
                    
                    neuron_data = {
                        'uid': uid,
                        'stake': stake_value,
                        'rank': float(neuron.get('rank', 0.0)),
                        'trust': float(neuron.get('trust', 0.0)),
                        'consensus': float(neuron.get('consensus', 0.0)),
                        'incentive': float(neuron.get('incentive', 0.0)),
                        'dividends': float(neuron.get('dividends', 0.0)),
                        'emission': emission_rao,
                        'daily_rewards_alpha': daily_rewards_alpha,
                        'daily_rewards_usd': daily_rewards_usd,
                        'hotkey': hotkey_name,
                        'is_registered': True
                    }
                    
                    neurons.append(neuron_data)
            
            if include_unregistered:
                hotkeys = self._get_wallet_hotkeys(coldkey_name)
                for hotkey_data in hotkeys:
                    hotkey_name = hotkey_data['name']
                    hotkey_address = hotkey_data['ss58_address']
                    
                    if hotkey_address in stake_info:
                        subnet_key = netuid if netuid in stake_info[hotkey_address] else str(netuid)
                        
                        if subnet_key in stake_info[hotkey_address]:
                            subnet_stake = stake_info[hotkey_address][subnet_key]
                            is_registered = subnet_stake.get('is_registered', True)
                            stake_value = subnet_stake.get('stake', 0.0)
                            
                            if not is_registered and stake_value > 0:
                                if not any(n['hotkey'] == hotkey_name for n in neurons):
                                    neuron_data = {
                                        'uid': -1,
                                        'stake': stake_value,
                                        'rank': 0.0,
                                        'trust': 0.0,
                                        'consensus': 0.0,
                                        'incentive': 0.0,
                                        'dividends': 0.0,
                                        'emission': 0,
                                        'daily_rewards_alpha': 0.0,
                                        'daily_rewards_usd': 0.0,
                                        'hotkey': hotkey_name,
                                        'is_registered': False
                                    }
                                    neurons.append(neuron_data)
                                    logger.info(f"Added unregistered neuron {hotkey_name} with stake {stake_value}")
            
            if not neurons:
                logger.info(f"No neurons found for subnet {netuid}")
                return None
            
            subnet_stats = {
                'netuid': netuid,
                'neurons': neurons,
                'stake': sum(n['stake'] for n in neurons),
                'daily_rewards_alpha': total_daily_rewards_alpha,
                'rate_usd': alpha_token_price_usd,
                'timestamp': datetime.now().isoformat(),
                'name': subnet_name,
                'symbol': subnet_symbol
            }
            
            logger.info(f"Successfully generated stats for subnet {netuid} with {len(neurons)} neurons")
            return subnet_stats
            
        except Exception as e:
            logger.error(f"Failed to get subnet {netuid} stats: {e}")
            return None

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

    def safe_get_wallet_stats(self, coldkey_name: str) -> Dict:
        try:
            logger.info(f"Safe stats check for {coldkey_name}")
            
            wallet = bt.wallet(name=coldkey_name)
            balance = self.subtensor.get_balance(wallet.coldkeypub.ss58_address)
            
            basic_stats = {
                'coldkey': coldkey_name,
                'wallet_address': wallet.coldkeypub.ss58_address,
                'balance': float(balance),
                'subnets': [],
                'timestamp': datetime.now().isoformat()
            }
            
            try:
                active_subnets = self.get_active_subnets_direct(coldkey_name)
                logger.info(f"Found active subnets for {coldkey_name}: {active_subnets}")
                
                if active_subnets:
                    basic_stats['active_subnets'] = active_subnets
                
            except Exception as e:
                logger.error(f"Error getting active subnets for {coldkey_name}: {e}")
                basic_stats['error'] = f"Could not get subnet info: {str(e)}"
            
            return basic_stats
            
        except Exception as e:
            logger.error(f"Safe stats failed for {coldkey_name}: {e}")
            return {
                'coldkey': coldkey_name,
                'error': str(e),
                'balance': 0.0,
                'subnets': []
            }
