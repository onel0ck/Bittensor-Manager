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
                    'dual_neurons': subnet_data.get("active_dual", 0)
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
                params = self.subtensor.get_subnet_hyperparameters(netuid=netuid)
            except Exception as e:
                if verbose:
                    console.print(f"[yellow]Warning: Error getting hyperparameters for subnet {netuid}: {e}[/yellow]")
                params = None
            
            registration_allowed = False
            registration_cost = 0
            max_neurons = 256
            max_validators = 64
            
            if params:
                if hasattr(params, 'burn'):
                    registration_cost = float(params.burn)
                
                if hasattr(params, 'registration_allowed'):
                    registration_allowed = params.registration_allowed
                
                if hasattr(params, 'max_n'):
                    max_neurons = int(params.max_n)
                
                if hasattr(params, 'max_allowed_validators'):
                    max_validators = int(params.max_allowed_validators)
            
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
                'owner': owner
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
            'all_subnets': subnet_infos
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
        
        console.print(f"\n[bold cyan]Subnet {netuid}[/bold cyan]")
        console.print(f"Total neurons: {active_total}/{max_neurons}")
        console.print(f"Validators: {active_validators}")
        console.print(f"Miners: {active_miners}")
        
        if dual > 0:
            console.print(f"Dual-role neurons: {dual}")
            
        console.print(f"Registration: {reg_status} (Cost: {cost_display}){adjustment_info}")
        console.print(f"Emission: {emission}{distribution_info}{recycled_info}")
        
        if subnet_info.get('owner'):
            console.print(f"Owner: {subnet_info['owner']}")
    
    def display_results(self, results: Dict[str, List[Dict]]):
        console.print("\n[bold]===== SUBNET ANALYSIS SUMMARY =====[/bold]")
        console.print(f"Total subnets analyzed: {len(results['all_subnets'])}")
        console.print(f"Subnets with closed registration: {len(results['closed_registration'])}")
        console.print(f"Subnets with ?5 miners: {len(results['few_miners'])}")
        console.print(f"Subnets with ?5 validators: {len(results['few_validators'])}")
        console.print(f"Subnets with no active validators: {len(results['no_active_validators'])}")
        console.print(f"Subnets with only one active validator: {len(results['single_validator'])}")
        console.print(f"Subnets with only miners (no validators): {len(results['miners_only'])}")

        if len(results['all_subnets']) > 0:
            all_table = Table(title="All Analyzed Subnets")
            all_table.add_column("Subnet")
            all_table.add_column("Active/Total")
            all_table.add_column("Validators")
            all_table.add_column("Miners")
            all_table.add_column("Registration")
            all_table.add_column("Cost (?)")
            all_table.add_column("Emission")
            
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
                
                all_table.add_row(
                    str(info['netuid']),
                    f"{active_keys}/{max_neurons}",
                    str(active_validators),
                    str(active_miners),
                    f"[{reg_color}]{reg_status}[/{reg_color}]",
                    cost_text,
                    str(info['emission'])
                )
            
            console.print("\n")
            console.print(all_table)
        
        categories = [
            ('no_active_validators', "Subnets with No Active Validators"),
            ('single_validator', "Subnets with Only One Active Validator"),
            ('few_validators', "Subnets with Few Validators (?5)"),
            ('few_miners', "Subnets with Few Miners (?5)"),
            ('closed_registration', "Subnets with Closed Registration"),
            ('miners_only', "Subnets with Only Miners (No Validators)")
        ]
        
        for key, title in categories:
            if not results[key]:
                continue
                
            table = Table(title=title)
            table.add_column("Subnet")
            table.add_column("Neurons")
            table.add_column("Validators")
            table.add_column("Miners")
            table.add_column("Registration")
            table.add_column("Cost (?)")
            table.add_column("Emission")
            
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
                
                table.add_row(
                    str(info['netuid']),
                    f"{info.get('active_keys', 0)}/{max_neurons}",
                    str(active_validators),
                    str(active_miners),
                    f"[{reg_color}]{reg_status}[/{reg_color}]",
                    cost_text,
                    str(info['emission'])
                )
            
            console.print("\n")
            console.print(table)
            
