import bittensor as bt
import asyncio
import threading
import time
import re
import subprocess
from typing import Dict, List, Optional, Any
from rich.console import Console
from rich.prompt import Confirm
from ..utils.logger import setup_logger

logger = setup_logger('auto_buyer', 'logs/auto_buyer.log')
console = Console()

class TokenBuyerThread(threading.Thread):
    def __init__(self, auto_buyer, coldkey, hotkey, subnet_id, amount, password, tolerance, rpc_endpoint=None):
        super().__init__()
        self.auto_buyer = auto_buyer
        self.coldkey = coldkey
        self.hotkey = hotkey
        self.subnet_id = subnet_id
        self.amount = amount
        self.password = password
        self.tolerance = tolerance
        self.rpc_endpoint = rpc_endpoint
        self.result = False
        self.error = None

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            self.result = loop.run_until_complete(
                self.auto_buyer.buy_subnet_token(
                    wallet_name=self.coldkey,
                    hotkey_name=self.hotkey,
                    subnet_id=self.subnet_id,
                    amount=self.amount,
                    password=self.password,
                    tolerance=self.tolerance,
                    rpc_endpoint=self.rpc_endpoint
                )
            )
            
            loop.close()
        except Exception as e:
            self.error = str(e)
            self.result = False

class AutoBuyerManager:
    def __init__(self, config):
        self.config = config
        self.subtensor = bt.subtensor()
        self.monitoring = False
        
    def verify_wallet_password(self, coldkey: str, password: str) -> bool:
        try:
            wallet = bt.wallet(name=coldkey)
            wallet.coldkey_file.decrypt(password)
            return True
        except Exception as e:
            logger.error(f"Failed to verify password for wallet {coldkey}: {e}")
            return False

    def _set_subtensor_network(self, rpc_endpoint: str = None):
        try:
            if rpc_endpoint:
                try:
                    if rpc_endpoint.startswith('ws://'):
                        self.subtensor = bt.subtensor(network=rpc_endpoint)
                    elif rpc_endpoint.startswith('wss://'):
                        self.subtensor = bt.subtensor(network=rpc_endpoint)
                    else:
                        modified_endpoint = f"ws://{rpc_endpoint}"
                        self.subtensor = bt.subtensor(network=modified_endpoint)

                    current_block = self.subtensor.get_current_block()
                    console.print(f"[green]Connected to custom RPC: {rpc_endpoint} (Block: {current_block})[/green]")
                    return True
                except Exception as e:
                    console.print(f"[red]Failed to connect to {rpc_endpoint}: {e}[/red]")
                    try:
                        self.subtensor = bt.subtensor()
                        console.print("[yellow]Falling back to default endpoint[/yellow]")
                        return True
                    except Exception as e2:
                        console.print(f"[red]Failed to connect to default endpoint: {e2}[/red]")
                        return False
            else:
                self.subtensor = bt.subtensor()
                console.print("[green]Connected to default endpoint[/green]")
                return True
        except Exception as e:
            console.print(f"[red]Error setting up subtensor network: {e}[/red]")
            return False
            
    async def check_registration_status_direct(self, subnet_id):
        try:
            current_block = self.subtensor.get_current_block()
            
            subnets = self.subtensor.get_subnets()
            if subnet_id not in subnets:
                logger.error(f"Subnet {subnet_id} not found")
                return None
            
            metagraph = self.subtensor.metagraph(netuid=subnet_id)
            
            try:
                params = self.subtensor.get_subnet_hyperparameters(netuid=subnet_id)
            except Exception as e:
                logger.error(f"Error getting hyperparameters: {e}")
                params = None
            
            registration_allowed = False
            
            if params and hasattr(params, 'registration_allowed'):
                registration_allowed = params.registration_allowed
            elif hasattr(metagraph, 'hparams') and hasattr(metagraph.hparams, 'registration_allowed'):
                registration_allowed = metagraph.hparams.registration_allowed
            
            return {
                'current_block': current_block,
                'registration_allowed': registration_allowed,
                'subnet_exists': True
            }
                
        except Exception as e:
            logger.error(f"Error getting direct registration info for subnet {subnet_id}: {e}")
            return None
    
    async def buy_subnet_token(self, wallet_name, hotkey_name, subnet_id, amount, password, tolerance=0.45, rpc_endpoint=None, skip_confirmation=False):
        try:
            try:
                original_subtensor = None
                if rpc_endpoint:
                    original_subtensor = self.subtensor
                    if not self._set_subtensor_network(rpc_endpoint):
                        console.print(f"[yellow]Failed to set custom RPC endpoint. Using default for balance check.[/yellow]")
                
                wallet = bt.wallet(name=wallet_name)
                initial_balance = float(self.subtensor.get_balance(wallet.coldkeypub.ss58_address))
                
                required_amount = float(amount) * 1.01
                
                if initial_balance < required_amount:
                    console.print(f"[red]Insufficient balance! Required {required_amount:.6f} TAO (with fee), available {initial_balance:.6f} TAO[/red]")
                    if original_subtensor:
                        self.subtensor = original_subtensor
                    return False
                
                console.print(f"[green]Balance verified: {initial_balance:.6f} TAO[/green]")
                
                if original_subtensor:
                    self.subtensor = original_subtensor
            except Exception as e:
                console.print(f"[yellow]Failed to check balance: {str(e)}[/yellow]")
                initial_balance = 0
                
                if original_subtensor:
                    self.subtensor = original_subtensor
            
            cmd = [
                "btcli", "stake", "add",
                "--wallet.name", wallet_name,
                "--wallet.hotkey", hotkey_name,
                "--netuid", str(subnet_id),
                "--amount", str(amount),
                "--allow-partial-stake",
                "--tolerance", str(tolerance),
                "--no_prompt"
            ]
            
            if rpc_endpoint:
                cmd.extend(["--subtensor.chain_endpoint", rpc_endpoint])
            
            console.print(f"[green]Executing command:[/green] {' '.join(cmd)}")
                
            subnet_status = await self.check_registration_status_direct(subnet_id)
            
            if not subnet_status:
                console.print(f"[red]Failed to get subnet {subnet_id} information[/red]")
                return False
                    
            if subnet_status['registration_allowed'] and not skip_confirmation:
                console.print(f"[yellow]Warning: Registration in subnet {subnet_id} is open, tokens may be more expensive.[/yellow]")
                if not Confirm.ask("Continue with purchase?"):
                    return False
            elif subnet_status['registration_allowed']:
                console.print(f"[yellow]Warning: Registration in subnet {subnet_id} is open, tokens may be more expensive. Proceeding automatically.[/yellow]")
            
            console.print("[yellow]Buying tokens...[/yellow]")
            
            import os
            env = os.environ.copy()
            env['COLUMNS'] = '1000'
            
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env
            )
            
            stdout, stderr = process.communicate(input=f"{password}\ny\n")
            
            console.print("[cyan]Command output:[/cyan]")
            console.print(stdout)
            
            if stderr:
                console.print(f"[yellow]Standard error output:[/yellow]")
                console.print(stderr)
            
            
            finalized_success = "? Finalized. Stake added to netuid:" in stdout or "Finalized. Stake added to netuid" in stdout
            
            balance_changed = False
            try:
                balance_pattern = r"Balance:.*??\s+(\d+\.\d+)\s+?\s+?\s+(\d+\.\d+)"
                balance_match = re.search(balance_pattern, stdout)
                if balance_match:
                    balance_before = float(balance_match.group(1))
                    balance_after = float(balance_match.group(2))
                    balance_changed = abs(balance_before - balance_after) > 0.00001
            except Exception as e:
                logger.error(f"Error parsing balance change: {e}")
            
            stake_changed = False
            try:
                stake_pattern = r"Subnet:.*?Stake:.*?(\d+\.\d+).*??.*?(\d+\.\d+)"
                stake_match = re.search(stake_pattern, stdout)
                if stake_match:
                    stake_before = float(stake_match.group(1))
                    stake_after = float(stake_match.group(2))
                    stake_changed = abs(stake_before - stake_after) > 0.00001
            except Exception as e:
                logger.error(f"Error parsing stake change: {e}")
                try:
                    if "Subnet: " in stdout and "Stake:" in stdout and "?" in stdout:
                        stake_lines = [line for line in stdout.split('\n') if "Subnet: " in line and "Stake:" in line]
                        if stake_lines:
                            stake_changed = True
                except Exception:
                    pass
            
            error_in_transaction = (
                "InsufficientBalance" in stdout or 
                "Extrinsic failed" in stdout or
                "Failed to send transaction" in stdout
            )
            
            simple_balance_check = "Balance:" in stdout and "?" in stdout
            
            simple_stake_check = "Subnet:" in stdout and "Stake:" in stdout and "?" in stdout
            
            success = (finalized_success or balance_changed or stake_changed or 
                      (simple_balance_check and simple_stake_check)) and not error_in_transaction
            
            if "multiple repeat" in stdout or "multiple repeat" in stderr:
                if balance_changed or stake_changed or finalized_success or (simple_balance_check and simple_stake_check):
                    console.print("[yellow]Warning: 'Multiple repeat' error detected but transaction appears successful.[/yellow]")
                    success = True
            
            if success:
                console.print(f"[green]Successfully bought {amount} TAO in subnet {subnet_id}[/green]")
                return True
                
            if "Custom error: 4" in stdout or "Custom error: 4" in stderr:
                console.print(f"[red]Error: Custom error 4 - Hotkey {hotkey_name} may not be registered in subnet {subnet_id}[/red]")
                console.print("[yellow]Try registering the hotkey first using 'btcli subnet register'[/yellow]")
            elif "priority is too low" in stdout or "Priority is too low" in stdout:
                console.print(f"[red]Error: Transaction priority too low[/red]")
                console.print(f"[yellow]Try increasing tolerance above {tolerance} or using a larger amount[/yellow]")
            else:
                console.print("[red]Failed to buy subnet tokens. Check command output above.[/red]")
            
            return False
        
        except Exception as e:
            error_msg = str(e)
            if "multiple repeat" in error_msg:
                try:
                    wallet = bt.wallet(name=wallet_name, hotkey=hotkey_name)
                    metagraph = self.subtensor.metagraph(netuid=subnet_id)
                    
                    try:
                        hotkey_index = metagraph.hotkeys.index(wallet.hotkey.ss58_address)
                        stake = float(metagraph.stake[hotkey_index])
                        
                        console.print(f"[green]Detected successful transaction despite errors. Current stake: {stake}[/green]")
                        return True
                    except ValueError:
                        pass
                    except Exception as check_e:
                        logger.error(f"Error checking stake: {check_e}")
                except Exception as api_e:
                    logger.error(f"Error checking via API: {api_e}")
                    
            console.print(f"[red]Error buying tokens: {error_msg}[/red]")
            return False
            
    async def monitor_subnet_and_buy(self, wallet_name, hotkey_name, subnet_id, amount, password, tolerance=0.45, check_interval=60, max_attempts=3, auto_skip_confirmation=True):
        self.monitoring = True
        start_time = time.time()
        checks_count = 0
        
        original_subtensor = self.subtensor
        
        console.print(f"[bold cyan]Starting monitoring subnet {subnet_id} for automatic purchase[/bold cyan]")
        console.print(f"[cyan]Checking every {check_interval} seconds...[/cyan]")
        console.print(f"[cyan]Maximum purchase attempts: {max_attempts}[/cyan]")
        console.print(f"[cyan]Initial parameters: amount={amount} TAO, tolerance={tolerance}[/cyan]")
        console.print("[yellow]Press Ctrl+C to stop monitoring[/yellow]\n")
        
        
        if not self.verify_wallet_password(wallet_name, password):
            console.print("[red]Invalid password! Monitoring stopped.[/red]")
            self.monitoring = False
            return False
            
        try:
            wallet = bt.wallet(name=wallet_name, hotkey=hotkey_name)
            console.print(f"[green]Hotkey {hotkey_name} found: {wallet.hotkey.ss58_address}[/green]")
        except Exception as e:
            console.print(f"[red]Error checking hotkey {hotkey_name}: {str(e)}[/red]")
            self.monitoring = False
            return False
        
        try:
            while self.monitoring:
                checks_count += 1
                now = time.time()
                elapsed_time = now - start_time
                hours, remainder = divmod(elapsed_time, 3600)
                minutes, seconds = divmod(remainder, 60)
                elapsed_str = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
                
                console.print(f"\n[bold]Check #{checks_count}[/bold] | Time: {elapsed_str} | Subnet: {subnet_id}")
                
                try:
                    subnets = self.subtensor.get_subnets()
                    subnet_exists = subnet_id in subnets
                    
                    if not subnet_exists:
                        console.print(f"[yellow]Subnet {subnet_id} not found. Waiting for appearance...[/yellow]")
                        await asyncio.sleep(check_interval)
                        continue
                    
                    try:
                        metagraph = self.subtensor.metagraph(netuid=subnet_id)
                        try:
                            uid = metagraph.hotkeys.index(wallet.hotkey.ss58_address)
                            current_stake = float(metagraph.stake[uid])
                            if current_stake > 0:
                                console.print(f"[green]Hotkey {hotkey_name} already has stake {current_stake} in subnet {subnet_id}[/green]")
                                self.monitoring = False
                                return True
                        except ValueError:
                            pass
                    except Exception as e:
                        console.print(f"[yellow]Failed to check current stake: {str(e)}[/yellow]")
                    
                    subnet_info = await self.check_registration_status_direct(subnet_id)
                    
                    if subnet_info is None:
                        console.print(f"[yellow]Failed to get subnet {subnet_id} information[/yellow]")
                        await asyncio.sleep(check_interval)
                        continue
                    
                    reg_status = "Open" if subnet_info['registration_allowed'] else "Closed"
                    status_color = "green" if not subnet_info['registration_allowed'] else "red"
                    
                    console.print(f"Block: {subnet_info['current_block']} | Registration: [{status_color}]{reg_status}[/{status_color}]")
                    
                    if not subnet_info['registration_allowed']:
                        console.print(f"[bold green]Registration in subnet {subnet_id} is CLOSED! Starting purchase...[/bold green]")
                        
                        attempt = 0
                        success = False
                        
                        current_amount = float(amount)
                        current_tolerance = float(tolerance)
                        
                        while attempt < max_attempts and not success:
                            attempt += 1
                            console.print(f"[cyan]Purchase attempt {attempt}/{max_attempts}[/cyan]")
                            console.print(f"[cyan]Parameters: amount={current_amount} TAO, tolerance={current_tolerance}[/cyan]")
                            
                            success = await self.buy_subnet_token(
                                wallet_name=wallet_name,
                                hotkey_name=hotkey_name,
                                subnet_id=subnet_id,
                                amount=current_amount,
                                password=password,
                                tolerance=current_tolerance,
                                skip_confirmation=auto_skip_confirmation
                            )
                            
                            if success:
                                console.print(f"[green]Successfully bought tokens in subnet {subnet_id}[/green]")
                                self.monitoring = False
                                break
                            elif attempt < max_attempts:
                                console.print(f"[yellow]Attempt {attempt} failed. Adapting parameters...[/yellow]")
                                
                                current_tolerance = min(0.95, current_tolerance * 1.1)
                                current_amount = max(0.001, current_amount * 0.9)
                                
                                console.print(f"[yellow]New parameters: amount={current_amount} TAO, tolerance={current_tolerance}[/yellow]")
                                await asyncio.sleep(10 * attempt)
                            else:
                                console.print(f"[red]Failed to buy tokens after {max_attempts} attempts. Continuing monitoring...[/red]")
                    else:
                        console.print(f"[yellow]Registration in subnet {subnet_id} is still open. Continuing monitoring...[/yellow]")
                    
                except Exception as e:
                    console.print(f"[red]Error during check: {str(e)}[/red]")
                
                await asyncio.sleep(check_interval)
                
        except KeyboardInterrupt:
            console.print("\n[yellow]Monitoring stopped by user.[/yellow]")
        finally:
            self.monitoring = False
            return False
            
    async def monitor_new_subnet_and_buy(self, wallet_configs, target_id, amount, tolerance=0.45, check_interval=60, max_attempts=3, auto_increase_tolerance=True, buy_immediately=False, rpc_endpoint=None):
        self.monitoring = True
        start_time = time.time()
        checks_count = 0
        bought_wallets = set()
        
        attempts_info = {}
        
        original_subtensor = self.subtensor
        
        if rpc_endpoint:
            console.print(f"[cyan]Connecting to custom RPC endpoint: {rpc_endpoint}[/cyan]")
            if not self._set_subtensor_network(rpc_endpoint):
                console.print(f"[yellow]Falling back to default endpoint[/yellow]")
                self.subtensor = original_subtensor
        
        console.print(f"[bold cyan]Starting monitoring for new subnet {target_id} detection[/bold cyan]")
        console.print(f"[cyan]Checking every {check_interval} seconds...[/cyan]")
        console.print(f"[cyan]Maximum purchase attempts: {max_attempts}[/cyan]")
        if auto_increase_tolerance:
            console.print(f"[cyan]Auto-increasing tolerance on failures enabled (starting from {tolerance})[/cyan]")
        if buy_immediately:
            console.print(f"[cyan]Buy immediately mode: Will purchase tokens as soon as subnet appears[/cyan]")
        else:
            console.print(f"[cyan]Will purchase tokens only when registration is closed[/cyan]")
        console.print("[yellow]Press Ctrl+C to stop monitoring[/yellow]\n")
        
        invalid_configs = []
        for config in wallet_configs:
            if not self.verify_wallet_password(config['coldkey'], config['password']):
                console.print(f"[red]Invalid password for wallet {config['coldkey']}![/red]")
                invalid_configs.append(config)
                
        for invalid in invalid_configs:
            wallet_configs.remove(invalid)
            
        if not wallet_configs:
            console.print("[red]No valid wallet configurations! Monitoring stopped.[/red]")
            self.monitoring = False
            return False
        
        for config in list(wallet_configs):
            try:
                wallet = bt.wallet(name=config['coldkey'], hotkey=config['hotkey'])
                console.print(f"[green]Hotkey {config['hotkey']} found for wallet {config['coldkey']}: {wallet.hotkey.ss58_address}[/green]")
                
                attempts_info[f"{config['coldkey']}:{config['hotkey']}"] = {
                    'attempts': 0,
                    'current_tolerance': tolerance
                }
            except Exception as e:
                console.print(f"[red]Error checking hotkey {config['hotkey']} for wallet {config['coldkey']}: {str(e)}[/red]")
                wallet_configs.remove(config)
                
        if not wallet_configs:
            console.print("[red]No valid hotkeys! Monitoring stopped.[/red]")
            self.monitoring = False
            return False
            
        console.print(f"[green]Successfully verified {len(wallet_configs)} hotkeys. Starting monitoring.[/green]")
            
        try:
            while self.monitoring:
                checks_count += 1
                now = time.time()
                elapsed_time = now - start_time
                hours, remainder = divmod(elapsed_time, 3600)
                minutes, seconds = divmod(remainder, 60)
                elapsed_str = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
                
                console.print(f"\n[bold]Check #{checks_count}[/bold] | Time: {elapsed_str} | Expected subnet: {target_id}")
                
                try:
                    subnets = self.subtensor.get_subnets()
                    subnet_exists = target_id in subnets
                    
                    if not subnet_exists:
                        console.print(f"[yellow]Subnet {target_id} not found. Continuing to wait...[/yellow]")
                        await asyncio.sleep(check_interval)
                        continue
                    
                    console.print(f"[green]Subnet {target_id} found! Checking registration status...[/green]")
                    
                    subnet_info = await self.check_registration_status_direct(target_id)
                    
                    if subnet_info is None:
                        console.print(f"[yellow]Failed to get subnet {target_id} information[/yellow]")
                        await asyncio.sleep(check_interval)
                        continue
                        
                    reg_status = "Open" if subnet_info['registration_allowed'] else "Closed"
                    status_color = "green" if not subnet_info['registration_allowed'] else "red"
                    
                    console.print(f"Block: {subnet_info['current_block']} | Registration: [{status_color}]{reg_status}[/{status_color}]")
                    
                    proceed_with_purchase = False
                    if buy_immediately:
                        proceed_with_purchase = True
                        console.print(f"[bold green]Subnet {target_id} detected! Starting immediate purchase...[/bold green]")
                    elif not subnet_info['registration_allowed']:
                        proceed_with_purchase = True
                        console.print(f"[bold green]Registration in subnet {target_id} is CLOSED! Starting purchase...[/bold green]")
                    else:
                        console.print(f"[yellow]Registration in subnet {target_id} is open. Waiting for registration to close...[/yellow]")
                    
                    try:
                        metagraph = self.subtensor.metagraph(netuid=target_id)
                    except Exception as e:
                        console.print(f"[yellow]Failed to get metagraph: {str(e)}[/yellow]")
                        metagraph = None
                        
                    remaining_configs = []
                    for config in wallet_configs:
                        key = f"{config['coldkey']}:{config['hotkey']}"
                        
                        if key in bought_wallets:
                            continue
                            
                        if attempts_info[key]['attempts'] >= max_attempts:
                            console.print(f"[yellow]Maximum attempts ({max_attempts}) reached for {key}. Skipping.[/yellow]")
                            continue
                        
                        try:
                            if metagraph:
                                wallet = bt.wallet(name=config['coldkey'], hotkey=config['hotkey'])
                                try:
                                    uid = metagraph.hotkeys.index(wallet.hotkey.ss58_address)
                                    current_stake = float(metagraph.stake[uid])
                                    if current_stake > 0:
                                        console.print(f"[yellow]Hotkey {config['hotkey']} in wallet {config['coldkey']} already has some stake {current_stake} in subnet {target_id}, but will add more[/yellow]")
                                    else:
                                        console.print(f"[green]Hotkey {config['hotkey']} in wallet {config['coldkey']} has no stake yet in subnet {target_id}[/green]")
                                except ValueError:
                                    pass
                        except Exception as e:
                            console.print(f"[yellow]Failed to check stake for {key}: {str(e)}[/yellow]")
                            
                        remaining_configs.append(config)
                    
                    if not remaining_configs:
                        if len(bought_wallets) == len(wallet_configs):
                            console.print(f"[green]All hotkeys already have stake in subnet {target_id}. Monitoring complete.[/green]")
                            self.monitoring = False
                            return True
                        else:
                            console.print(f"[yellow]All remaining hotkeys have reached maximum attempts. Monitoring complete.[/yellow]")
                            self.monitoring = False
                            return len(bought_wallets) > 0
                        
                    if proceed_with_purchase:
                        console.print(f"[bold green]Starting purchase for {len(remaining_configs)} hotkeys...[/bold green]")
                        
                        successful_buys = 0
                        
                        for config in remaining_configs:
                            coldkey = config['coldkey']
                            hotkey = config['hotkey']
                            password = config['password']
                            key = f"{coldkey}:{hotkey}"
                            
                            attempts_info[key]['attempts'] += 1
                            attempt_num = attempts_info[key]['attempts']
                            
                            current_tolerance = attempts_info[key]['current_tolerance']
                            
                            console.print(f"[cyan]Purchasing for {coldkey}:{hotkey} (Attempt {attempt_num}/{max_attempts}, Tolerance: {current_tolerance:.2f})...[/cyan]")
                            
                            try:
                                success = await self.buy_subnet_token(
                                    wallet_name=coldkey,
                                    hotkey_name=hotkey,
                                    subnet_id=target_id,
                                    amount=float(amount),
                                    password=password,
                                    tolerance=current_tolerance,
                                    rpc_endpoint=rpc_endpoint,
                                    skip_confirmation=True
                                )
                                
                                if success:
                                    console.print(f"[green]Successfully bought tokens in subnet {target_id} for {key}[/green]")
                                    bought_wallets.add(key)
                                    successful_buys += 1
                                else:
                                    console.print(f"[red]Failed to buy tokens for {key} (Attempt {attempts_info[key]['attempts']}/{max_attempts})[/red]")
                                    
                                    if auto_increase_tolerance and attempts_info[key]['attempts'] < max_attempts:
                                        new_tolerance = min(0.95, attempts_info[key]['current_tolerance'] + 0.1)
                                        attempts_info[key]['current_tolerance'] = new_tolerance
                                        console.print(f"[yellow]Increased tolerance for {key} to {new_tolerance:.2f} for next attempt[/yellow]")
                            except Exception as e:
                                console.print(f"[red]Error processing {key}: {str(e)}[/red]")
                                
                                if auto_increase_tolerance and attempts_info[key]['attempts'] < max_attempts:
                                    new_tolerance = min(0.95, attempts_info[key]['current_tolerance'] + 0.1)
                                    attempts_info[key]['current_tolerance'] = new_tolerance
                                    console.print(f"[yellow]Increased tolerance for {key} to {new_tolerance:.2f} for next attempt[/yellow]")
                        
                        console.print(f"[green]Successfully bought tokens in subnet {target_id} for {successful_buys} out of {len(remaining_configs)} hotkeys[/green]")
                        
                        if successful_buys == len(remaining_configs) or len(bought_wallets) == len(wallet_configs):
                            console.print("[green]All hotkeys processed. Monitoring complete.[/green]")
                            self.monitoring = False
                            return True
                    
                except Exception as e:
                    console.print(f"[red]Error during check: {str(e)}[/red]")
                    
                await asyncio.sleep(check_interval)
                
        except KeyboardInterrupt:
            console.print("\n[yellow]Monitoring stopped by user.[/yellow]")
        finally:
            self.monitoring = False
            return len(bought_wallets) > 0
