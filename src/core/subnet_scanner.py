import requests
import json
import bittensor as bt
import numpy as np
import asyncio
from typing import Dict, List, Optional, Tuple
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.live import Live
from ..utils.logger import setup_logger
import time

logger = setup_logger('subnet_scanner', 'logs/subnet_scanner.log')
console = Console()

class SubnetScanner:
    def __init__(self, config):
        self.config = config
        self.subtensor = bt.subtensor()
        self.api_key = self.config.get('taostats.api_key')
        self.api_url = self.config.get('taostats.api_url', 'https://api.taostats.io/api')
        self.tao_price = None

    def get_tao_price(self) -> Optional[float]:
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
                        self.tao_price = price
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
                    self.tao_price = price
                    return price
            except Exception as e:
                logger.warning(f"Failed to get TAO price from Binance: {e}")
                
            try:
                api_key = self.api_key
                if api_key:
                    url = f"{self.api_url}/prices/latest/v1"
                    headers = {
                        "accept": "application/json",
                        "Authorization": api_key
                    }
                    
                    response = requests.get(url, headers=headers, timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        price = float(data['data'][0]['usd'])
                        logger.info(f"Got TAO price from TaoStats: ${price}")
                        self.tao_price = price
                        return price
            except Exception as e:
                logger.warning(f"Failed to get TAO price from TaoStats: {e}")
            
            logger.error("All price sources failed")
            return None
        except Exception as e:
            logger.error(f"Error in get_tao_price: {e}")
            return None

    def get_all_subnets_direct(self) -> List[int]:
        try:
            return self.subtensor.get_subnets()
        except Exception as e:
            logger.error(f"Error getting subnets: {e}")
            return []

    def get_all_subnet_info_api(self) -> Dict[int, Dict]:
        try:
            if not self.api_key:
                console.print("[red]TAO Stats API key not configured[/red]")
                return {}
                
            url = f"{self.api_url}/subnet/latest/v1"
            headers = {
                "accept": "application/json",
                "Authorization": self.api_key
            }
            
            console.print("[cyan]Fetching data for all subnets with a single API call...[/cyan]")
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                console.print(f"[red]API request failed: {response.status_code}[/red]")
                return {}
                
            data = response.json()
            
            subnets_info = {}
            for subnet_data in data["data"]:
                netuid = subnet_data["netuid"]
                
                stake_distribution = {
                    'mean': 0.0,
                    'std': 0.0,
                    'cv': 0.0
                }
                
                commit_reveal_weights_enabled = subnet_data.get("commit_reveal_weights_enabled", False)
                difficulty = float(subnet_data.get("difficulty", 0))
                min_difficulty = float(subnet_data.get("min_difficulty", 0))
                max_difficulty = float(subnet_data.get("max_difficulty", 1))
                
                normalized_difficulty = 0
                if max_difficulty > min_difficulty:
                    normalized_difficulty = (difficulty - min_difficulty) / (max_difficulty - min_difficulty)
                
                subnet_info = {
                    'netuid': netuid,
                    'total_neurons': subnet_data["active_keys"] + (subnet_data.get("inactive_keys", 0) or 0),
                    'active_keys': subnet_data["active_keys"],
                    'max_neurons': subnet_data["max_neurons"],
                    'validators_count': subnet_data.get("validators", 64),
                    'active_validators': subnet_data["active_validators"],
                    'miners_count': subnet_data["active_miners"],
                    'active_miners': subnet_data["active_miners"],
                    'max_validators': subnet_data.get("validators", 64),
                    'validators': [],
                    'miners': [],
                    'registration_allowed': subnet_data["registration_allowed"],
                    'registration_cost': float(subnet_data["neuron_registration_cost"]) / 1e9,
                    'emission': int(subnet_data["emission"]),
                    'stake_distribution': stake_distribution,
                    'owner': subnet_data.get("owner", {}).get("ss58") if subnet_data.get("owner") else None,
                    'blocks_until_adjustment': subnet_data.get("blocks_until_next_adjustment", 0),
                    'activity_cutoff': subnet_data.get("activity_cutoff", 5000),
                    'adjustment_interval': subnet_data.get("adjustment_interval", 360),
                    'recycled_lifetime': float(subnet_data.get("recycled_lifetime", 0)) / 1e9,
                    'recycled_24_hours': float(subnet_data.get("recycled_24_hours", 0)) / 1e9,
                    'dual_neurons': subnet_data.get("active_dual", 0),
                    'commit_reveal_weights_enabled': commit_reveal_weights_enabled,
                    'difficulty': difficulty,
                    'min_difficulty': min_difficulty,
                    'max_difficulty': max_difficulty,
                    'normalized_difficulty': normalized_difficulty
                }
                
                subnets_info[netuid] = subnet_info
            
            console.print(f"[green]Successfully retrieved data for {len(subnets_info)} subnets[/green]")
            return subnets_info
            
        except Exception as e:
            logger.error(f"Error getting subnets from API: {e}")
            return {}

    def get_subnet_info_direct(self, netuid: int, verbose: bool = False) -> Optional[Dict]:
        try:
            if verbose:
                console.print(f"[cyan]Getting direct info for subnet {netuid}...[/cyan]")
                
            metagraph = self.subtensor.metagraph(netuid)
            
            try:
                subnet_info_raw = self.subtensor.get_subnet_info(netuid=netuid)
                if verbose and subnet_info_raw:
                    console.print(f"[green]Successfully got detailed subnet info for {netuid}[/green]")
            except Exception as e:
                if verbose:
                    console.print(f"[yellow]Warning: Error getting subnet info for {netuid}: {e}[/yellow]")
                subnet_info_raw = None
                
            try:
                params = self.subtensor.get_subnet_hyperparameters(netuid=netuid)
            except Exception as e:
                if verbose:
                    console.print(f"[yellow]Warning: Error getting hyperparameters for subnet {netuid}: {e}[/yellow]")
                params = None
            
            registration_allowed = False
            registration_cost = 0
            max_neurons = 256
            max_validators = 64
            commit_reveal_weights_enabled = False
            difficulty = 0
            min_difficulty = 0
            max_difficulty = 1
            
            if subnet_info_raw:
                if hasattr(subnet_info_raw, 'commit_reveal_weights_enabled'):
                    commit_reveal_weights_enabled = subnet_info_raw.commit_reveal_weights_enabled
                
                if hasattr(subnet_info_raw, 'difficulty'):
                    difficulty = float(subnet_info_raw.difficulty)
                    
                if hasattr(subnet_info_raw, 'min_difficulty'):
                    min_difficulty = float(subnet_info_raw.min_difficulty)
                    
                if hasattr(subnet_info_raw, 'max_difficulty'):
                    max_difficulty = float(subnet_info_raw.max_difficulty)
            
            if params:
                if hasattr(params, 'burn'):
                    registration_cost = float(params.burn)
                
                if hasattr(params, 'registration_allowed'):
                    registration_allowed = params.registration_allowed
                
                if hasattr(params, 'max_n'):
                    max_neurons = int(params.max_n)
                
                if hasattr(params, 'max_allowed_validators'):
                    max_validators = int(params.max_allowed_validators)
                    
                if hasattr(params, 'commit_reveal_weights_enabled') and not commit_reveal_weights_enabled:
                    commit_reveal_weights_enabled = params.commit_reveal_weights_enabled
            
            if hasattr(metagraph, 'hparams'):
                hparams = metagraph.hparams
                
                if not registration_cost and hasattr(hparams, 'burn'):
                    registration_cost = float(hparams.burn)
                
                if registration_allowed is False and hasattr(hparams, 'registration_allowed'):
                    registration_allowed = hparams.registration_allowed
            
            if hasattr(metagraph, 'max_n') and not max_neurons:
                max_neurons = int(metagraph.max_n)
            elif hasattr(metagraph, 'max_uids') and not max_neurons:
                max_neurons = int(metagraph.max_uids)
            
            emission_value = 0
            if hasattr(metagraph, 'emission'):
                emission_value = int(sum(metagraph.emission))
            
            validators = []
            miners = []
            active_validators = 0
            active_miners = 0
            
            has_validator_permit = hasattr(metagraph, 'validator_permit') and len(metagraph.validator_permit) > 0
            
            has_axon_info = hasattr(metagraph, 'axon_info') and len(metagraph.axon_info) > 0
            
            uids_by_stake = sorted(
                range(len(metagraph.stake)), 
                key=lambda i: float(metagraph.stake[i]), 
                reverse=True
            )
            
            for index, uid in enumerate(uids_by_stake):
                if uid >= len(metagraph.uids):
                    continue
                    
                is_validator = False
                is_active = False
                
                if has_validator_permit and uid < len(metagraph.validator_permit):
                    is_validator = bool(metagraph.validator_permit[uid])
                elif index < max_validators:
                    is_validator = True
                elif has_axon_info and uid < len(metagraph.axon_info):
                    axon = metagraph.axon_info[uid]
                    if hasattr(axon, 'ip') and axon.ip and axon.ip != '0.0.0.0':
                        is_validator = True
                
                if uid < len(metagraph.stake) and float(metagraph.stake[uid]) > 0:
                    is_active = True
                
                neuron_info = {
                    'uid': int(metagraph.uids[uid]),
                    'stake': float(metagraph.stake[uid]),
                    'trust': float(metagraph.trust[uid]) if uid < len(metagraph.trust) else 0.0,
                    'consensus': float(metagraph.consensus[uid]) if uid < len(metagraph.consensus) else 0.0,
                    'incentive': float(metagraph.incentive[uid]) if uid < len(metagraph.incentive) else 0.0,
                    'dividends': float(metagraph.dividends[uid]) if uid < len(metagraph.dividends) else 0.0,
                    'is_validator': is_validator,
                    'is_active': is_active
                }
                
                if is_validator:
                    validators.append(neuron_info)
                    if is_active:
                        active_validators += 1
                else:
                    miners.append(neuron_info)
                    if is_active:
                        active_miners += 1
            
            stakes = [float(s) for s in metagraph.stake if float(s) > 0]
            stake_std = float(np.std(stakes)) if stakes else 0
            stake_mean = float(np.mean(stakes)) if stakes else 0
            stake_cv = stake_std / stake_mean if stake_mean > 0 else 0
            owner = None
            if hasattr(metagraph, 'owner') and len(metagraph.owner) > 0:
                owner = str(metagraph.owner[0])
            
            normalized_difficulty = 0
            if max_difficulty > min_difficulty:
                normalized_difficulty = (difficulty - min_difficulty) / (max_difficulty - min_difficulty)
            
            subnet_info = {
                'netuid': netuid,
                'total_neurons': len(metagraph.uids),
                'active_keys': len(stakes),
                'max_neurons': max_neurons,
                'validators_count': len(validators),
                'active_validators': active_validators,
                'miners_count': len(miners),
                'active_miners': active_miners,
                'max_validators': max_validators,
                'validators': validators,
                'miners': miners,
                'registration_allowed': registration_allowed,
                'registration_cost': registration_cost,
                'emission': emission_value,
                'stake_distribution': {
                    'mean': stake_mean,
                    'std': stake_std,
                    'cv': stake_cv
                },
                'owner': owner,
                'commit_reveal_weights_enabled': commit_reveal_weights_enabled,
                'difficulty': difficulty,
                'min_difficulty': min_difficulty,
                'max_difficulty': max_difficulty,
                'normalized_difficulty': normalized_difficulty
            }
            
            return subnet_info
            
        except Exception as e:
            logger.error(f"Error getting direct info for subnet {netuid}: {e}")
            return None

    async def analyze_subnets(self, use_api: bool = True, verbose: bool = False) -> Dict[str, List[Dict]]:
        subnet_infos = []
        
        if use_api:
            all_subnet_info = self.get_all_subnet_info_api()
            if all_subnet_info:
                subnet_infos = list(all_subnet_info.values())
            else:
                console.print("[yellow]Failed to get subnets from API, falling back to direct blockchain query[/yellow]")
                use_api = False
        
        if not use_api:
            all_subnets = self.get_all_subnets_direct()
            if not all_subnets:
                console.print("[red]No subnets found![/red]")
                return {}
            
            console.print(f"[cyan]Found {len(all_subnets)} subnets. Analyzing...[/cyan]")
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("[cyan]Analyzing subnets...", total=len(all_subnets))
                
                for subnet_id in all_subnets:
                    progress.update(task, description=f"[cyan]Analyzing subnet {subnet_id}...[/cyan]")
                    
                    subnet_info = self.get_subnet_info_direct(subnet_id, verbose=verbose)
                    if subnet_info:
                        subnet_infos.append(subnet_info)
                    
                    progress.update(task, advance=1)
        
        if not subnet_infos:
            console.print("[red]No subnet information found![/red]")
            return {}
            
        self.get_tao_price()
        
        results = {
            'closed_registration': [],
            'few_miners': [],
            'few_validators': [],
            'no_active_validators': [],
            'single_validator': [],
            'miners_only': [],
            'all_subnets': subnet_infos,
            'weights_disabled': [],
            'high_difficulty': []
        }
        
        for info in subnet_infos:
            if not info['registration_allowed']:
                results['closed_registration'].append(info)
            
            if 0 < info['active_miners'] <= 5:
                results['few_miners'].append(info)
            
            if info['validators_count'] == 0 and info['miners_count'] > 0:
                results['miners_only'].append(info)
            
            if info['active_validators'] == 0 and info['total_neurons'] > 0:
                results['no_active_validators'].append(info)
            
            if info['active_validators'] == 1:
                results['single_validator'].append(info)
            
            if 0 < info['active_validators'] <= 5:
                results['few_validators'].append(info)
                
            if 'commit_reveal_weights_enabled' in info and not info['commit_reveal_weights_enabled']:
                results['weights_disabled'].append(info)
            
            high_difficulty = False
            if 'normalized_difficulty' in info and info['normalized_difficulty'] > 0.5:
                high_difficulty = True
            elif 'difficulty' in info:
                if info['difficulty'] == 1.0 or (info['difficulty'] > 0.1 and info.get('max_difficulty', 0) > 0):
                    high_difficulty = True
            
            if high_difficulty:
                results['high_difficulty'].append(info)
        
        return results

    def display_subnet_summary(self, subnet_info: Dict):
        netuid = subnet_info['netuid']
        total = subnet_info['total_neurons']
        active_total = subnet_info.get('active_keys', 0)
        max_neurons = subnet_info.get('max_neurons', 'Unknown')
        validators_total = subnet_info['validators_count']
        active_validators = subnet_info.get('active_validators', 0)
        max_validators = subnet_info.get('max_validators', 'Unknown')
        miners_total = subnet_info['miners_count']
        active_miners = subnet_info.get('active_miners', 0)
        dual = subnet_info.get('dual_neurons', 0)
        reg_status = "Open" if subnet_info['registration_allowed'] else "Closed"
        reg_cost = subnet_info['registration_cost']
        emission = subnet_info['emission']
        
        if self.tao_price:
            cost_usd = reg_cost * self.tao_price
            cost_display = f"{reg_cost:.9f} ? (${cost_usd:.2f})"
        else:
            cost_display = f"{reg_cost:.9f} ?"
            
        adjustment_info = ""
        if 'blocks_until_adjustment' in subnet_info:
            blocks = subnet_info['blocks_until_adjustment']
            if blocks > 0:
                minutes = (blocks * 12) // 60
                adjustment_info = f" (Next adjustment: ~{minutes} minutes)"
        
        distribution_info = ""
        if 'stake_distribution' in subnet_info and 'cv' in subnet_info['stake_distribution']:
            cv = subnet_info['stake_distribution']['cv']
            if cv > 0:
                if cv < 0.5:
                    dist_text = "Uniform"
                elif cv < 1.0:
                    dist_text = "Variable"
                else:
                    dist_text = "Concentrated"
                distribution_info = f"\nStake distribution: {dist_text} (CV: {cv:.2f})"
        
        recycled_info = ""
        if 'recycled_lifetime' in subnet_info:
            recycled = subnet_info['recycled_lifetime']
            if recycled > 0:
                recycled_info = f"\nRecycled TAO (lifetime): {recycled:.2f} ?"
                
            if 'recycled_24_hours' in subnet_info:
                recycled_24h = subnet_info['recycled_24_hours']
                if recycled_24h > 0:
                    recycled_info += f"\nRecycled TAO (24h): {recycled_24h:.2f} ?"
        
        weights_info = ""
        if 'commit_reveal_weights_enabled' in subnet_info:
            weights_status = "Enabled" if subnet_info['commit_reveal_weights_enabled'] else "Disabled"
            weights_color = "green" if subnet_info['commit_reveal_weights_enabled'] else "red"
            weights_info = f"\nCommit-Reveal Weights: [{weights_color}]{weights_status}[/{weights_color}]"
        
        difficulty_info = ""
        if 'difficulty' in subnet_info:
            difficulty = subnet_info['difficulty']
            norm_difficulty = subnet_info.get('normalized_difficulty', 0)
            
            difficulty_text = f"Raw: {difficulty:.12f}"
            if norm_difficulty > 0:
                difficulty_level = "Low"
                difficulty_color = "green"
                
                if norm_difficulty > 0.9:
                    difficulty_level = "Very High"
                    difficulty_color = "red"
                elif norm_difficulty > 0.7:
                    difficulty_level = "High"
                    difficulty_color = "yellow"
                elif norm_difficulty > 0.3:
                    difficulty_level = "Medium"
                    difficulty_color = "cyan"
                
                difficulty_text += f", Normalized: {norm_difficulty:.2f} ([{difficulty_color}]{difficulty_level}[/{difficulty_color}])"
            elif difficulty == 1.0:
                difficulty_text += " ([red]Maximum[/red])"
            elif difficulty > 0.5:
                difficulty_text += " ([yellow]High[/yellow])"
            elif difficulty > 0.0001:
                difficulty_text += " ([cyan]Medium[/cyan])"
            
            difficulty_info = f"\nDifficulty: {difficulty_text}"
        
        console.print(f"\n[bold cyan]Subnet {netuid}[/bold cyan]")
        console.print(f"Total neurons: {active_total}/{max_neurons}")
        console.print(f"Validators: {active_validators}")
        console.print(f"Miners: {active_miners}")
        
        if dual > 0:
            console.print(f"Dual-role neurons: {dual}")
            
        console.print(f"Registration: {reg_status} (Cost: {cost_display}){adjustment_info}")
        console.print(f"Emission: {emission}{distribution_info}{recycled_info}{weights_info}{difficulty_info}")
        
        if subnet_info.get('owner'):
            console.print(f"Owner: {subnet_info['owner']}")
    
    def display_results(self, results: Dict[str, List[Dict]]):
        console.print("\n[bold]===== SUBNET ANALYSIS SUMMARY =====[/bold]")
        console.print(f"Total subnets analyzed: {len(results['all_subnets'])}")
        console.print(f"Subnets with closed registration: {len(results.get('closed_registration', []))}")
        console.print(f"Subnets with ?5 miners: {len(results.get('few_miners', []))}")
        console.print(f"Subnets with ?5 validators: {len(results.get('few_validators', []))}")
        console.print(f"Subnets with no active validators: {len(results.get('no_active_validators', []))}")
        console.print(f"Subnets with only one active validator: {len(results.get('single_validator', []))}")
        console.print(f"Subnets with only miners (no validators): {len(results.get('miners_only', []))}")
        
        console.print(f"Subnets with disabled commit-reveal weights: {len(results.get('weights_disabled', []))}")
        console.print(f"Subnets with high registration difficulty: {len(results.get('high_difficulty', []))}")

        if len(results['all_subnets']) > 0:
            all_table = Table(title="All Analyzed Subnets")
            all_table.add_column("Subnet")
            all_table.add_column("Active/Total")
            all_table.add_column("Validators")
            all_table.add_column("Miners")
            all_table.add_column("Registration")
            all_table.add_column("Cost (?)")
            all_table.add_column("Emission")
            all_table.add_column("Weights")
            all_table.add_column("Difficulty")
            
            for info in sorted(results['all_subnets'], key=lambda x: x['netuid']):
                max_neurons = info.get('max_neurons', 'Unknown')
                active_keys = info.get('active_keys', 0)
                
                active_validators = info.get('active_validators', 0)
                active_miners = info.get('active_miners', 0)
                
                cost_text = f"{info['registration_cost']:.9f}"
                if self.tao_price:
                    cost_usd = info['registration_cost'] * self.tao_price
                    cost_text += f"\n(${cost_usd:.2f})"
                
                reg_status = "Open" if info['registration_allowed'] else "Closed"
                reg_color = "green" if info['registration_allowed'] else "red"
                
                weights_status = "Unknown"
                weights_color = "yellow"
                if 'commit_reveal_weights_enabled' in info:
                    weights_status = "Enabled" if info['commit_reveal_weights_enabled'] else "Disabled"
                    weights_color = "green" if info['commit_reveal_weights_enabled'] else "red"
                
                difficulty_text = "Unknown"
                difficulty_color = "yellow"
                
                if 'difficulty' in info:
                    difficulty = info['difficulty']
                    norm_difficulty = info.get('normalized_difficulty', 0)
                    
                    if norm_difficulty > 0.5:
                        difficulty_text = f"{norm_difficulty:.2f}"
                        difficulty_color = "red"
                    elif norm_difficulty > 0:
                        difficulty_text = f"{norm_difficulty:.2f}"
                        difficulty_color = "green"
                    elif difficulty == 1.0:
                        difficulty_text = "1.0 (MAX)"
                        difficulty_color = "red"
                    elif difficulty > 0.0001:
                        difficulty_text = f"{difficulty:.2e}"
                        difficulty_color = "cyan"
                    else:
                        difficulty_text = "Very Low"
                        difficulty_color = "green"
                
                all_table.add_row(
                    str(info['netuid']),
                    f"{active_keys}/{max_neurons}",
                    str(active_validators),
                    str(active_miners),
                    f"[{reg_color}]{reg_status}[/{reg_color}]",
                    cost_text,
                    str(info['emission']),
                    f"[{weights_color}]{weights_status}[/{weights_color}]",
                    f"[{difficulty_color}]{difficulty_text}[/{difficulty_color}]"
                )
            
            console.print("\n")
            console.print(all_table)
        
        categories = [
            ('no_active_validators', "Subnets with No Active Validators"),
            ('single_validator', "Subnets with Only One Active Validator"),
            ('few_validators', "Subnets with Few Validators (?5)"),
            ('few_miners', "Subnets with Few Miners (?5)"),
            ('closed_registration', "Subnets with Closed Registration"),
            ('miners_only', "Subnets with Only Miners (No Validators)"),
            ('weights_disabled', "Subnets with Disabled Commit-Reveal Weights"),
            ('high_difficulty', "Subnets with High Registration Difficulty")
        ]
        
        for key, title in categories:
            if key not in results or not results[key]:
                continue
                
            table = Table(title=title)
            table.add_column("Subnet")
            table.add_column("Neurons")
            table.add_column("Validators")
            table.add_column("Miners")
            table.add_column("Registration")
            table.add_column("Cost (?)")
            table.add_column("Emission")
            
            if key == 'weights_disabled':
                table.add_column("Weights Enabled")
            elif key == 'high_difficulty':
                table.add_column("Difficulty")
            
            for info in sorted(results[key], key=lambda x: x['netuid']):
                max_neurons = info.get('max_neurons', 'Unknown')
                active_validators = info.get('active_validators', 0)
                active_miners = info.get('active_miners', 0)
                
                cost_text = f"{info['registration_cost']:.9f}"
                if self.tao_price:
                    cost_usd = info['registration_cost'] * self.tao_price
                    cost_text += f"\n(${cost_usd:.2f})"
                
                reg_status = "Open" if info['registration_allowed'] else "Closed"
                reg_color = "green" if info['registration_allowed'] else "red"
                
                row_data = [
                    str(info['netuid']),
                    f"{info.get('active_keys', 0)}/{max_neurons}",
                    str(active_validators),
                    str(active_miners),
                    f"[{reg_color}]{reg_status}[/{reg_color}]",
                    cost_text,
                    str(info['emission'])
                ]
                
                if key == 'weights_disabled':
                    weights_status = "No"
                    if 'commit_reveal_weights_enabled' in info:
                        weights_status = "Yes" if info['commit_reveal_weights_enabled'] else "No"
                    row_data.append(weights_status)
                elif key == 'high_difficulty':
                    difficulty_text = "Unknown"
                    if 'normalized_difficulty' in info and info['normalized_difficulty'] > 0:
                        difficulty_text = f"{info['normalized_difficulty']:.2f}"
                    elif 'difficulty' in info:
                        difficulty = info['difficulty']
                        if difficulty == 1.0:
                            difficulty_text = "1.0 (MAX)"
                        elif difficulty > 0.0001:
                            difficulty_text = f"{difficulty:.2e}"
                        else:
                            difficulty_text = "Very Low"
                    row_data.append(difficulty_text)
                
                table.add_row(*row_data)
            
            console.print("\n")
            console.print(table)

    def check_registration_activity(self, disabled_weights_subnets):
        if not self.api_key:
            console.print("[red]API key is not configured. Cannot check registration activity.[/red]")
            return {}
        
        current_time = time.strftime("%H:%M:%S", time.localtime())
        console.print(f"[cyan][{current_time}] Starting registration activity check[/cyan]")
        
        sorted_subnets = sorted(
            disabled_weights_subnets, 
            key=lambda x: (x.get('active_keys', 0), x.get('active_miners', 0)), 
            reverse=True
        )
        
        interesting_subnets = [
            subnet for subnet in sorted_subnets 
            if subnet.get('registration_allowed', False)
        ]
        
        console.print(f"[yellow]Found {len(interesting_subnets)} subnets with open registration[/yellow]")
        
        max_subnets_to_check = len(interesting_subnets)
        check_all = False
        
        if max_subnets_to_check > 5:
            check_all = Confirm.ask(f"Check all {max_subnets_to_check} subnets? (This will take approximately {max_subnets_to_check*12} seconds)", default=False)
            if not check_all:
                console.print("[yellow]Checking only top 5 most active subnets[/yellow]")
                interesting_subnets = interesting_subnets[:5]
        
        subnets_to_check = interesting_subnets
        
        results = {}
        headers = {
            "accept": "application/json",
            "Authorization": self.api_key
        }
        
        if not subnets_to_check:
            console.print("[yellow]No suitable subnets found for registration activity check.[/yellow]")
            return {}
        
        subnet_ids = [s['netuid'] for s in subnets_to_check]
        console.print(f"[cyan]Checking {len(subnets_to_check)} subnets: {subnet_ids}[/cyan]")
        console.print(f"[cyan]This will take approximately {len(subnets_to_check) * 12} seconds due to API rate limits[/cyan]")
        
        for i, subnet in enumerate(subnets_to_check):
            netuid = subnet['netuid']
            current_time = time.strftime("%H:%M:%S", time.localtime())
            console.print(f"[cyan][{current_time}] Checking subnet {netuid} ({i+1}/{len(subnets_to_check)})...[/cyan]")
            
            try:
                url = f"{self.api_url}/subnet/neuron/registration/v1?netuid={netuid}"
                console.print(f"[dim]Making API request to: {url}[/dim]")
                
                start_time = time.time()
                response = requests.get(url, headers=headers, timeout=30)
                end_time = time.time()
                request_time = end_time - start_time
                
                console.print(f"[dim]API request took {request_time:.2f} seconds[/dim]")
                
                if response.status_code == 200:
                    data = response.json()
                    registrations = data.get('data', [])
                    
                    console.print(f"[dim]Received {len(registrations)} registrations for subnet {netuid}[/dim]")
                    
                    if registrations:
                        consecutive_blocks = 0
                        last_block = None
                        block_list = []
                        
                        for reg in registrations[:10]:
                            block = reg.get('block_number')
                            block_list.append(block)
                            if last_block is None:
                                last_block = block
                            elif last_block - block <= 2:
                                consecutive_blocks += 1
                            last_block = block
                        
                        console.print(f"[dim]Block sequence: {block_list[:5]}...[/dim]")
                        console.print(f"[dim]Consecutive blocks detected: {consecutive_blocks}[/dim]")
                        
                        if consecutive_blocks >= 3:
                            competition_status = "High"
                            status_color = "red"
                        elif consecutive_blocks >= 1:
                            competition_status = "Medium"
                            status_color = "yellow"
                        else:
                            competition_status = "Low"
                            status_color = "green"
                        
                        console.print(f"[{status_color}]Competition level: {competition_status}[/{status_color}]")
                        
                        total_registrations = data.get('pagination', {}).get('total_items', 0)
                        
                        results[netuid] = {
                            'consecutive_blocks': consecutive_blocks,
                            'competition_status': competition_status,
                            'total_registrations': total_registrations,
                            'latest_registrations': [
                                {
                                    'block': reg.get('block_number'),
                                    'timestamp': reg.get('timestamp'),
                                    'uid': reg.get('uid'),
                                    'cost': float(reg.get('registration_cost', 0)) / 1e9
                                }
                                for reg in registrations[:3]
                            ]
                        }
                    else:
                        console.print(f"[yellow]No registration data found for subnet {netuid}[/yellow]")
                else:
                    console.print(f"[red]Failed to get registration data for subnet {netuid}: {response.status_code} - {response.text}[/red]")
            
            except requests.exceptions.Timeout:
                console.print(f"[red]Timeout when querying subnet {netuid}. API request took too long.[/red]")
                continue
            except Exception as e:
                console.print(f"[red]Error checking registration activity for subnet {netuid}: {str(e)}[/red]")
                continue
            
            if i < len(subnets_to_check) - 1:
                wait_seconds = 12
                console.print(f"[yellow]Waiting {wait_seconds} seconds before next API request (API rate limit: 5 requests/minute)...[/yellow]")
                
                for remaining in range(wait_seconds, 0, -1):
                    console.print(f"[dim]Waiting: {remaining} seconds remaining...[/dim]")
                    time.sleep(1)
                console.print("[dim]Wait complete, proceeding to next subnet...[/dim]")
        
        current_time = time.strftime("%H:%M:%S", time.localtime())
        console.print(f"[green][{current_time}] Completed registration activity check. Found data for {len(results)} subnets.[/green]")
        return results

    def display_registration_activity(self, activity_results):
        if not activity_results:
            console.print("[yellow]No registration activity data to display.[/yellow]")
            return
        
        table = Table(title="Registration Activity in Subnets with Disabled Weights")
        table.add_column("Subnet")
        table.add_column("Competition")
        table.add_column("Total Regs")
        table.add_column("Last 3 Blocks")
        table.add_column("Latest Cost (?)")
        
        for netuid, data in sorted(activity_results.items(), key=lambda x: x[0]):
            competition = data['competition_status']
            competition_color = "green"
            if competition == "Medium":
                competition_color = "yellow"
            elif competition == "High":
                competition_color = "red"
            
            total_regs = data['total_registrations']
            
            last_blocks = []
            for reg in data['latest_registrations']:
                last_blocks.append(str(reg['block']))
            blocks_str = ", ".join(last_blocks)
            
            latest_cost = data['latest_registrations'][0]['cost'] if data['latest_registrations'] else 0
            cost_text = f"{latest_cost:.6f}"
            
            if self.tao_price:
                cost_usd = latest_cost * self.tao_price
                cost_text += f"\n(${cost_usd:.2f})"
            
            table.add_row(
                str(netuid),
                f"[{competition_color}]{competition}[/{competition_color}]",
                str(total_regs),
                blocks_str,
                cost_text
            )
        
        console.print("\n")
        console.print(table)
        
        console.print("\n[bold]Competition Levels Explanation:[/bold]")
        console.print("[green]Low[/green]: Few consecutive registrations, likely easy to register")
        console.print("[yellow]Medium[/yellow]: Some consecutive registrations, moderate competition")
        console.print("[red]High[/red]: Many consecutive registrations, high competition for slots")
