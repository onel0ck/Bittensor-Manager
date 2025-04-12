# -*- coding: utf-8 -*-

import os
import bittensor as bt
import re
from typing import Dict, List, Optional, Tuple
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt, Confirm
from rich.status import Status
from ..utils.logger import setup_logger
import time
import subprocess

logger = setup_logger('transfer_manager', 'logs/transfer_manager.log')
console = Console()

class TransferManager:
    def __init__(self, config):
        self.config = config
        self.subtensor = bt.subtensor()
        
        self.logs_dir = os.path.expanduser('~/.bittensor/logs')
        os.makedirs(self.logs_dir, exist_ok=True)
        
        try:
            from ..core.stats_manager import StatsManager
            self.stats_manager = StatsManager(config)
            logger.info("StatsManager successfully loaded")
        except Exception as e:
            logger.warning(f"Could not load StatsManager: {e}")
            self.stats_manager = None

    def _get_wallet_password(self, wallet: str) -> str:
        default_password = self.config.get('wallet.default_password')
        if default_password:
            password = Prompt.ask(
                f"Enter password for {wallet} (press Enter to use default: {default_password})", 
                password=True,
                show_default=False
            )
            return password if password else default_password
        else:
            return Prompt.ask(f"Enter password for {wallet}", password=True)

    def verify_wallet_password(self, coldkey: str, password: str) -> bool:
        try:
            wallet = bt.wallet(name=coldkey)
            wallet.coldkey_file.decrypt(password)
            return True
        except Exception as e:
            logger.error(f"Failed to verify password for wallet {coldkey}: {e}")
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

    def _handle_transfer(self):
        wallets = self.wallet_utils.get_available_wallets()
        if not wallets:
            console.print("[red]No wallets found![/red]")
            return

        console.print("\nAvailable Source Wallets:")
        for i, wallet in enumerate(wallets, 1):
            console.print(f"{i}. {wallet}")

        selection = Prompt.ask("Select source wallet (number)").strip()
        try:
            index = int(selection) - 1
            if not (0 <= index < len(wallets)):
                console.print("[red]Invalid wallet selection![/red]")
                return
            source_wallet = wallets[index]
        except ValueError:
            console.print("[red]Invalid input![/red]")
            return

        dest_address = Prompt.ask("Enter destination wallet address (SS58 format)")
        if not dest_address.startswith('5'):
            console.print("[red]Invalid destination address format![/red]")
            return

        try:
            amount = float(Prompt.ask("Enter amount of TAO to transfer"))
            if amount <= 0:
                console.print("[red]Amount must be greater than 0![/red]")
                return
        except ValueError:
            console.print("[red]Invalid amount![/red]")
            return

        if Confirm.ask(f"Transfer {amount} TAO from {source_wallet} to {dest_address}?"):
            password = self._get_wallet_password(source_wallet)

            with Status("[bold green]Processing transfer...", spinner="dots"):
                try:
                    if not self.verify_wallet_password(source_wallet, password):
                        console.print("[red]Invalid password![/red]")
                        return

                    if self.transfer_tao(source_wallet, dest_address, amount, password):
                        console.print("[green]Transfer completed successfully![/green]")
                    else:
                        console.print("[red]Transfer failed![/red]")
                except Exception as e:
                    console.print(f"[red]Error: {str(e)}[/red]")

    def _get_hotkey_name_from_address(self, coldkey_name: str, ss58_address: str) -> Optional[str]:
        try:
            hotkeys_path = os.path.expanduser(f"~/.bittensor/wallets/{coldkey_name}/hotkeys")
            
            if not os.path.exists(hotkeys_path):
                return None
                
            for hotkey_name in os.listdir(hotkeys_path):
                try:
                    wallet = bt.wallet(name=coldkey_name, hotkey=hotkey_name)
                    if wallet.hotkey.ss58_address == ss58_address:
                        return hotkey_name
                except Exception:
                    continue
                    
            return None
        except Exception as e:
            logger.error(f"Error getting hotkey name for address {ss58_address}: {e}")
            return None

    def get_unregistered_stake_info(self, coldkey_name: str, subnet_id: int) -> Dict:
        try:
            logger.info(f"Getting unregistered stake info for {coldkey_name} in subnet {subnet_id}")
            temp_file = "stake_list_output.txt"
            cmd = f'COLUMNS=2000 btcli stake list --wallet.name {coldkey_name} --no_prompt > {temp_file}'
            
            subprocess.run(cmd, shell=True)
            
            with open(temp_file, 'r') as f:
                output = f.read()
            
            debug_file = f"stake_list_debug_{coldkey_name}.txt"
            with open(debug_file, 'w') as f:
                f.write(output)
            logger.info(f"Saved stake list output to {debug_file}")
            
            subprocess.run(f'rm {temp_file}', shell=True)
            
            stake_info = {
                'netuid': subnet_id,
                'hotkeys': []
            }
            
            hotkey_sections = output.split('Hotkey:')
            logger.info(f"Found {len(hotkey_sections)-1} hotkey sections for {coldkey_name}")
            
            for idx, section in enumerate(hotkey_sections[1:], 1):
                lines = section.strip().split('\n')
                
                hotkey_line = lines[0]
                hotkey_parts = hotkey_line.strip().split()
                if not hotkey_parts:
                    logger.warning(f"Could not extract hotkey from line: '{hotkey_line}'")
                    continue
                    
                ss58_address = hotkey_parts[0].strip()
                
                hotkey_name = self._get_hotkey_name_from_address(coldkey_name, ss58_address)
                
                if not hotkey_name:
                    logger.warning(f"Could not determine hotkey name for address {ss58_address}")
                    continue
                    
                logger.info(f"Processing hotkey {idx}: {hotkey_name} ({ss58_address})")
                
                table_start = False
                subnet_data = []
                
                for line in lines:
                    if '????' in line or '----' in line:
                        table_start = True
                        continue
                        
                    if table_start and '|' in line and not line.strip().startswith('-') and not 'Total' in line:
                        subnet_data.append(line)
                
                logger.info(f"Found {len(subnet_data)} subnet entries for hotkey {hotkey_name}")
                
                for subnet_idx, subnet_line in enumerate(subnet_data, 1):
                    parts = subnet_line.split('|')
                    if len(parts) < 7:
                        logger.warning(f"Not enough columns in subnet line {subnet_idx} for hotkey {hotkey_name}")
                        continue
                        
                    try:
                        netuid_part = parts[0].strip()
                        name_part = parts[1].strip()
                        value_part = parts[2].strip()
                        stake_part = parts[3].strip()
                        price_part = parts[4].strip()
                        registered_part = parts[6].strip() if len(parts) > 6 else ''
                        
                        logger.info(f"Processing subnet {subnet_idx} for hotkey {hotkey_name}: netuid_part='{netuid_part}', stake='{stake_part}', registered='{registered_part}'")
                        
                        curr_subnet_id = None
                        digits_only = ''.join(c for c in netuid_part if c.isdigit())
                        if digits_only:
                            curr_subnet_id = int(digits_only)
                            logger.info(f"Extracted netuid {curr_subnet_id} from '{netuid_part}'")
                        else:
                            logger.warning(f"Could not extract netuid from '{netuid_part}'")
                            continue
                        
                        if curr_subnet_id != subnet_id:
                            continue
                                
                        alpha_stake = 0.0
                        stake_match = re.search(r'([0-9.]+)', stake_part)
                        if stake_match:
                            try:
                                alpha_stake = float(stake_match.group(1))
                            except ValueError:
                                logger.warning(f"Could not convert '{stake_match.group(1)}' to float")
                        
                        is_registered = 'YES' in registered_part
                        logger.info(f"Registration status for subnet {curr_subnet_id} hotkey {hotkey_name}: '{registered_part}' -> {is_registered}")
                        
                        if alpha_stake > 0:
                            stake_info['hotkeys'].append({
                                'name': hotkey_name,
                                'address': ss58_address,
                                'stake': alpha_stake,
                                'uid': -1 if not is_registered else 0,
                                'is_registered': is_registered
                            })
                            logger.info(f"Added {'registered' if is_registered else 'unregistered'} stake for hotkey {hotkey_name} in subnet {curr_subnet_id}: {alpha_stake}")
                                    
                    except Exception as e:
                        logger.error(f"Error parsing stake line for hotkey {hotkey_name}, subnet {subnet_idx}: {e}")
                        continue
            
            return stake_info
                
        except Exception as e:
            logger.error(f"Error in get_unregistered_stake_info: {e}")
            return {'netuid': subnet_id, 'hotkeys': []}

    def get_alpha_stake_info(self, coldkey_name: str, subnet_list: Optional[List[int]] = None) -> List[Dict]:
        try:
            if hasattr(self, 'stats_manager') and self.stats_manager is not None:
                try:
                    if subnet_list is None:
                        active_subnets = self._get_active_subnets_with_stats(coldkey_name)
                    else:
                        active_subnets = subnet_list
                    
                    if not active_subnets:
                        logger.warning(f"No active subnets found for {coldkey_name}")
                        return []
                    
                    stake_info = []
                    unregistered_stakes = self.stats_manager.get_unregistered_stakes(coldkey_name)
                    
                    for netuid in active_subnets:
                        traditional_info_found = False
                        
                        try:
                            metagraph = self.subtensor.metagraph(netuid)
                            subnet_info = {
                                'netuid': netuid,
                                'hotkeys': []
                            }

                            hotkeys_path = os.path.expanduser(f"~/.bittensor/wallets/{coldkey_name}/hotkeys")
                            if os.path.exists(hotkeys_path):
                                for hotkey_name in os.listdir(hotkeys_path):
                                    try:
                                        hotkey_wallet = bt.wallet(name=coldkey_name, hotkey=hotkey_name)
                                        hotkey_address = hotkey_wallet.hotkey.ss58_address

                                        try:
                                            uid = metagraph.hotkeys.index(hotkey_address)
                                            stake = float(metagraph.stake[uid])
                                            
                                            traditional_info_found = True
                                            
                                            if stake > 0:
                                                subnet_info['hotkeys'].append({
                                                    'name': hotkey_name,
                                                    'address': hotkey_address,
                                                    'stake': stake,
                                                    'uid': uid,
                                                    'is_registered': True
                                                })
                                        except ValueError:
                                            pass

                                    except Exception as e:
                                        logger.error(f"Error processing hotkey {hotkey_name}: {e}")
                                        continue

                                if subnet_info['hotkeys']:
                                    stake_info.append(subnet_info)
                                    logger.info(f"Found {len(subnet_info['hotkeys'])} registered hotkeys for subnet {netuid}")
                        except Exception as e:
                            logger.error(f"Error getting registered stake info for subnet {netuid}: {e}")
                        
                        if not traditional_info_found:
                            subnet_info = {
                                'netuid': netuid,
                                'hotkeys': []
                            }
                            
                            for hotkey_address, hotkey_stakes in unregistered_stakes.items():
                                if str(netuid) in hotkey_stakes or netuid in hotkey_stakes:
                                    subnet_key = str(netuid) if str(netuid) in hotkey_stakes else netuid
                                    stake_data = hotkey_stakes[subnet_key]
                                    
                                    if stake_data.get('stake', 0) > 0 and not stake_data.get('is_registered', True):
                                        hotkey_name = self._get_hotkey_name_from_address(coldkey_name, hotkey_address)
                                        
                                        if hotkey_name:
                                            subnet_info['hotkeys'].append({
                                                'name': hotkey_name,
                                                'address': hotkey_address,
                                                'stake': stake_data['stake'],
                                                'uid': -1,
                                                'is_registered': False
                                            })
                                            logger.info(f"Added unregistered stake for hotkey {hotkey_name} in subnet {netuid}: {stake_data['stake']}")
                            
                            if subnet_info['hotkeys']:
                                stake_info.append(subnet_info)
                    
                    return stake_info
                except Exception as e:
                    logger.error(f"Error using StatsManager: {e}")
            
            wallet = bt.wallet(name=coldkey_name)
            stake_info = []

            if subnet_list is None:
                active_subnets = self._get_active_subnets(coldkey_name)
            else:
                active_subnets = subnet_list

            for netuid in active_subnets:
                traditional_info_found = False
                
                try:
                    metagraph = self.subtensor.metagraph(netuid)
                    subnet_info = {
                        'netuid': netuid,
                        'hotkeys': []
                    }

                    hotkeys_path = os.path.expanduser(f"~/.bittensor/wallets/{coldkey_name}/hotkeys")
                    if os.path.exists(hotkeys_path):
                        for hotkey_name in os.listdir(hotkeys_path):
                            try:
                                hotkey_wallet = bt.wallet(name=coldkey_name, hotkey=hotkey_name)
                                hotkey_address = hotkey_wallet.hotkey.ss58_address

                                try:
                                    uid = metagraph.hotkeys.index(hotkey_address)
                                    stake = float(metagraph.stake[uid])
                                    
                                    traditional_info_found = True
                                    
                                    if stake > 0:
                                        subnet_info['hotkeys'].append({
                                            'name': hotkey_name,
                                            'address': hotkey_address,
                                            'stake': stake,
                                            'uid': uid,
                                            'is_registered': True
                                        })
                                except ValueError:
                                    continue

                            except Exception as e:
                                logger.error(f"Error processing hotkey {hotkey_name}: {e}")
                                continue

                        if subnet_info['hotkeys']:
                            stake_info.append(subnet_info)
                            logger.info(f"Found {len(subnet_info['hotkeys'])} registered hotkeys for subnet {netuid}")

                except Exception as e:
                    logger.error(f"Error processing subnet {netuid} via metagraph: {e}")
                
                if not traditional_info_found:
                    logger.info(f"No traditional stake info found for subnet {netuid}, checking unregistered stakes")
                    unregistered_info = self.get_unregistered_stake_info(coldkey_name, netuid)
                    
                    if unregistered_info and unregistered_info['hotkeys']:
                        unregistered_hotkeys = [h for h in unregistered_info['hotkeys'] if not h.get('is_registered', True)]
                        
                        if unregistered_hotkeys:
                            logger.info(f"Found {len(unregistered_hotkeys)} unregistered hotkeys with stakes for subnet {netuid}")
                            found = False
                            for info in stake_info:
                                if info['netuid'] == netuid:
                                    info['hotkeys'].extend(unregistered_hotkeys)
                                    found = True
                                    break
                                    
                            if not found:
                                unregistered_info['hotkeys'] = unregistered_hotkeys
                                stake_info.append(unregistered_info)

            return stake_info

        except Exception as e:
            logger.error(f"Error getting alpha stake info for {coldkey_name}: {e}")
            raise

    def display_alpha_stake_summary(self, stake_info: List[Dict]):
        for subnet in stake_info:
            table = Table(title=f"Subnet {subnet['netuid']} Alpha Stakes")
            table.add_column("Hotkey")
            table.add_column("UID")
            table.add_column("Alpha Stake")
            table.add_column("Status")
            table.add_column("Address")

            total_stake = 0
            for hotkey in subnet['hotkeys']:
                if hotkey['stake'] > 0:
                    total_stake += hotkey['stake']
                    
                    status = "[green]Registered[/green]" if hotkey.get('is_registered', True) else "[yellow]Unregistered[/yellow]"
                    
                    table.add_row(
                        hotkey['name'],
                        str(hotkey['uid']),
                        f"{hotkey['stake']:.9f}",
                        status,
                        hotkey['address']
                    )

            table.add_row(
                "[bold]Total[/bold]",
                "",
                f"[bold]{total_stake:.9f}[/bold]",
                "",
                "",
                style="bold green"
            )

            console.print(table)

    def _get_exact_stake_amount(self, coldkey: str, hotkey: str, netuid: int) -> float:
        try:
            cmd = f'COLUMNS=2000 btcli stake list --wallet.name {coldkey} --wallet.hotkey {hotkey} --no_prompt'
            process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            output = process.stdout
            logger.debug(f"Got output from btcli for {coldkey}:{hotkey} in subnet {netuid}")
            
            subnet_found = False
            stake_value = 0.0
            
            for line in output.split('\n'):
                line = line.strip()
                
                if re.match(rf'^\s*{netuid}\s+', line):
                    subnet_found = True
                    logger.debug(f"Found subnet line: {line}")
                    
                    parts = re.split(r'[|\u2502]', line)
                    
                    if len(parts) >= 4:
                        stake_part = parts[3].strip()
                        logger.debug(f"Stake part: '{stake_part}'")
                        
                        stake_match = re.search(r'([0-9.]+)', stake_part)
                        if stake_match:
                            try:
                                stake_value = float(stake_match.group(1))
                                logger.info(f"Found stake for {coldkey}:{hotkey} in subnet {netuid}: {stake_value}")
                                return stake_value
                            except ValueError:
                                logger.warning(f"Could not convert stake value: {stake_match.group(1)}")
                    
                    break
            
            if not subnet_found:
                logger.warning(f"Subnet {netuid} not found in direct output, trying alternative approach")
                
                cmd = f'COLUMNS=2000 btcli stake list --wallet.name {coldkey} --no_prompt'
                process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                
                output = process.stdout
                
                hotkey_section = None
                current_hotkey = None
                sections = output.split("Hotkey:")
                
                for section in sections:
                    if not section.strip():
                        continue
                    
                    lines = section.strip().split('\n')
                    if not lines:
                        continue
                        
                    first_line = lines[0].strip()
                    hotkey_address = first_line.split()[0] if first_line.split() else ""
                    
                    wallet_hotkey = None
                    try:
                        wallet = bt.wallet(name=coldkey, hotkey=hotkey)
                        if wallet.hotkey.ss58_address == hotkey_address:
                            wallet_hotkey = hotkey
                            hotkey_section = section
                            break
                    except Exception:
                        pass
                
                if hotkey_section:
                    logger.debug(f"Found hotkey section for {hotkey}")
                    
                    for line in hotkey_section.split('\n'):
                        line = line.strip()
                        
                        if re.match(rf'^\s*{netuid}\s+', line):
                            logger.debug(f"Found subnet line in section: {line}")
                            
                            parts = re.split(r'[|\u2502]', line)
                            
                            if len(parts) >= 4:
                                stake_part = parts[3].strip()
                                logger.debug(f"Stake part from section: '{stake_part}'")
                                
                                stake_match = re.search(r'([0-9.]+)', stake_part)
                                if stake_match:
                                    try:
                                        stake_value = float(stake_match.group(1))
                                        logger.info(f"Found stake in section for {coldkey}:{hotkey} in subnet {netuid}: {stake_value}")
                                        return stake_value
                                    except ValueError:
                                        logger.warning(f"Could not convert section stake value: {stake_match.group(1)}")
            
            logger.warning(f"Could not find stake information for {coldkey}:{hotkey} in subnet {netuid}")
            return 0.0
            
        except Exception as e:
            logger.error(f"Error getting exact stake amount: {e}")
            return 0.0

    def unstake_alpha(self, coldkey: str, hotkey: str, netuid: int, amount: float, password: str, tolerance: float = 0.45) -> bool:
        try:
            logger.info(f"Unstaking {amount} Alpha TAO from {coldkey}:{hotkey} in subnet {netuid}")
            
            real_stake = self._get_exact_stake_amount(coldkey, hotkey, netuid)
            logger.info(f"Real stake detected for {coldkey}:{hotkey} in subnet {netuid}: {real_stake}")
            
            if real_stake <= 0:
                console.print(f"[yellow]No stake found for {coldkey}:{hotkey} in subnet {netuid}[/yellow]")
                return False
            
            if amount > real_stake:
                console.print(f"[yellow]Requested unstake amount ({amount:.9f}) exceeds available stake ({real_stake:.9f}) for {coldkey}:{hotkey} in subnet {netuid}[/yellow]")
                

                amount = real_stake * 0.99
                console.print(f"[cyan]Adjusting unstake amount to {amount:.9f} (99% of available stake)[/cyan]")
            
            unstake_amount = amount
            logger.info(f"Will unstake {unstake_amount} for {coldkey}:{hotkey} in subnet {netuid}")
            
            cmd = [
                "btcli", "stake", "remove",
                "--wallet.name", coldkey,
                "--wallet.hotkey", hotkey,
                "--netuid", str(netuid),
                "--amount", f"{unstake_amount:.9f}",
                "--allow-partial-stake",
                "--tolerance", str(tolerance),
                "--no_prompt"
            ]
            
            logger.debug(f"Running command: {' '.join(cmd)}")

            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            stdout, stderr = process.communicate(input=f"{password}\n")
            logger.info(f"Command output: {stdout}")
            
            unstaked_amount = None
            
            if "Not enough stake to remove" in stdout or "Not enough stake to remove" in stderr:
                error_message = stdout if "Not enough stake to remove" in stdout else stderr
                logger.warning(f"Stake amount error detected: {error_message}")
                
                balance_match = re.search(r'Stake balance:.*?(\d+\.\d+)', error_message.replace('‎', '').replace('‎', ''))
                available_stake = None
                
                if balance_match:
                    try:
                        available_stake = float(balance_match.group(1))
                        logger.info(f"Extracted available stake: {available_stake}")
                    except (ValueError, IndexError):
                        logger.error(f"Failed to convert extracted balance: {balance_match.group(1) if balance_match else 'None'}")
                
                if not available_stake:
                    try:
                        balance_line = ""
                        for line in error_message.split('\n'):
                            if "Stake balance:" in line:
                                balance_line = line
                                break
                        
                        if balance_line:
                            clean_line = ''.join(c for c in balance_line if c.isdigit() or c == '.' or c.isspace())
                            numbers = re.findall(r'\d+\.\d+', clean_line)
                            if numbers:
                                available_stake = float(numbers[0])
                                logger.info(f"Extracted available stake (method 2): {available_stake}")
                    except Exception as e:
                        logger.error(f"Error in backup extraction method: {e}")
                
                if not available_stake and ('‎0.0' in error_message or '‎0.0' in error_message):
                    try:
                        special_match = re.search(r'(?:\u200E)?(\d+\.\d+)(?:\s*[\u0600-\u06FF\u200E\u200F])?', error_message)
                        if special_match:
                            available_stake = float(special_match.group(1))
                            logger.info(f"Extracted available stake (special case): {available_stake}")
                    except Exception as e:
                        logger.error(f"Error in special case extraction: {e}")
                
                if available_stake and available_stake > 0:
                    logger.info(f"Found available stake: {available_stake}")
                    retry_amount = available_stake * 0.95
                    
                    console.print(f"[yellow]Available stake ({available_stake:.9f}) is less than requested unstake amount. Retrying with adjusted amount...[/yellow]")
                    
                    retry_cmd = [
                        "btcli", "stake", "remove",
                        "--wallet.name", coldkey,
                        "--wallet.hotkey", hotkey,
                        "--netuid", str(netuid),
                        "--amount", f"{retry_amount:.9f}",
                        "--allow-partial-stake",
                        "--tolerance", str(tolerance),
                        "--no_prompt"
                    ]
                    
                    logger.debug(f"Retrying with command: {' '.join(retry_cmd)}")
                    
                    retry_process = subprocess.Popen(
                        retry_cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    
                    retry_stdout, retry_stderr = retry_process.communicate(input=f"{password}\n")
                    logger.info(f"Retry command output: {retry_stdout}")
                    
                    if retry_process.returncode == 0 and "Error" not in retry_stdout and "No unstake operations to perform" not in retry_stdout:
                        logger.info(f"Successfully unstaked {retry_amount:.9f} Alpha TAO from {coldkey}:{hotkey} in subnet {netuid}")
                        console.print(f"[green]Successfully unstaked {retry_amount:.9f} from {hotkey}![/green]")
                        unstaked_amount = retry_amount
                        return {"success": True, "unstaked_amount": unstaked_amount}
                    else:
                        error_msg = retry_stderr if retry_stderr else retry_stdout
                        logger.error(f"Retry unstake failed. Error: {error_msg}")
                        console.print(f"[red]Retry unstake failed: {error_msg}[/red]")
                        return {"success": False, "error": error_msg}
                else:
                    logger.error(f"Could not extract available stake from error message: {error_message}")
            
            if process.returncode == 0 and "Error" not in stdout and "No unstake operations to perform" not in stdout:
                logger.info(f"Successfully unstaked {unstake_amount:.9f} Alpha TAO from {coldkey}:{hotkey} in subnet {netuid}")
                console.print(f"[green]Successfully unstaked from {hotkey}![/green]")
                unstaked_amount = unstake_amount
                return {"success": True, "unstaked_amount": unstaked_amount}
            else:
                error_msg = stderr if stderr else stdout
                if "No neuron found with hotkey" in error_msg:
                    console.print(f"[yellow]Neuron not found for {coldkey}:{hotkey} in subnet {netuid}[/yellow]")
                elif "No stakes found" in error_msg:
                    console.print(f"[yellow]No stakes found for {coldkey}:{hotkey} in subnet {netuid}[/yellow]")
                else:
                    logger.error(f"Unstake failed. Error: {error_msg}")
                    console.print(f"[red]Unstake failed: {error_msg}[/red]")
                return {"success": False, "error": error_msg}

        except Exception as e:
            logger.error(f"Error unstaking Alpha from {coldkey}:{hotkey}: {e}")
            console.print(f"[red]Error unstaking: {str(e)}[/red]")
            return {"success": False, "error": str(e)}

    def _get_active_subnets(self, wallet_name: str) -> List[int]:
        try:
            temp_file = "overview_output.txt"
            cmd = f'COLUMNS=1000 btcli wallet overview --wallet.name {wallet_name} > {temp_file}'

            process = subprocess.run(cmd, shell=True)

            with open(temp_file, 'r') as f:
                output = f.read()

            subprocess.run(f'rm {temp_file}', shell=True)

            registered_subnets = []
            current_subnet = None

            for line in output.split('\n'):
                subnet_match = re.search(r'Subnet:\s*(\d+):', line)
                if subnet_match:
                    current_subnet = int(subnet_match.group(1))

                if current_subnet is not None and ('STAKE' in line or 'EMISSION' in line):
                    numbers = re.findall(r'\d+\.\d+|\d+', line)
                    if numbers and any(float(n) > 0 for n in numbers):
                        registered_subnets.append(current_subnet)
                        current_subnet = None
            
            logger.info(f"Found registered subnets: {registered_subnets}")
            
            unregistered_subnets = []
            try:
                logger.info("Looking for unregistered stakes")
                temp_file = "stake_list_output.txt"
                cmd = f'COLUMNS=2000 btcli stake list --wallet.name {wallet_name} --no_prompt > {temp_file}'
                
                subprocess.run(cmd, shell=True)
                
                with open(temp_file, 'r') as f:
                    stake_output = f.read()
                
                hotkey_sections = stake_output.split('Hotkey:')
                
                for section in hotkey_sections[1:]:
                    lines = section.strip().split('\n')
                    
                    table_start = False
                    subnet_data = []
                    
                    for line in lines:
                        if '????' in line or '----' in line:
                            table_start = True
                            continue
                            
                        if table_start and '|' in line and not line.strip().startswith('-') and not 'Total' in line:
                            subnet_data.append(line)
                    
                    for subnet_line in subnet_data:
                        parts = subnet_line.split('|')
                        if len(parts) < 7:
                            continue
                            
                        try:
                            netuid_part = parts[0].strip()
                            stake_part = parts[3].strip()
                            registered_part = parts[6].strip() if len(parts) > 6 else ''
                            
                            digits_only = ''.join(c for c in netuid_part if c.isdigit())
                            if not digits_only:
                                continue
                                
                            netuid = int(digits_only)
                            
                            stake_match = re.search(r'([0-9.]+)', stake_part)
                            if not stake_match:
                                continue
                                
                            try:
                                stake = float(stake_match.group(1))
                            except ValueError:
                                continue
                            
                            is_registered = 'YES' in registered_part
                            
                            if stake > 0 and not is_registered and netuid not in registered_subnets and netuid not in unregistered_subnets:
                                unregistered_subnets.append(netuid)
                                logger.info(f"Found unregistered stake in subnet {netuid}")
                        
                        except Exception as e:
                            logger.error(f"Error processing subnet line: {e}")
                            continue
                
                subprocess.run(f'rm {temp_file}', shell=True)
                
            except Exception as e:
                logger.error(f"Error finding unregistered stakes: {e}")
            
            logger.info(f"Found unregistered subnets: {unregistered_subnets}")
            
            all_subnets = list(set(registered_subnets + unregistered_subnets))
            logger.info(f"Combined subnet list: {all_subnets}")
            
            return all_subnets

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
            
