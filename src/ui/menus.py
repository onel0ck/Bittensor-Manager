import asyncio
import os
from typing import Dict, Optional, List
from rich.console import Console
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.panel import Panel
from rich.table import Table
from ..core.wallet_utils import WalletUtils
import bittensor as bt
from rich.status import Status
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text
import time
from datetime import datetime
import json

console = Console()

class RegistrationMenu:
    def __init__(self, registration_manager, config):
        self.registration_manager = registration_manager
        self.config = config
        self.wallet_utils = WalletUtils()

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

    def _get_rpc_endpoint(self) -> Optional[str]:
        default_endpoint = "wss://entrypoint-finney.opentensor.ai:443"
        rpc_endpoint = Prompt.ask(
            f"Enter RPC endpoint (press Enter for default endpoint)",
            default=default_endpoint
        ).strip()
        
        if rpc_endpoint == default_endpoint:
            rpc_endpoint = None
            
        return rpc_endpoint

    def show(self):
        console.print("\n[bold]Register Wallets[/bold]")
        console.print(Panel.fit(
           "1. Simple Registration (Immediate)\n"
           "2. Professional Registration (Next Adjustment)\n"
           "3. Auto Registration (Multiple Adjustments)\n"
           "4. Sniper Registration (DEGEN mode)\n"
           "5. Spread Registration (Multiple Hotkeys with distributed timing)\n"
           "6. Subnet Monitor Registration (Wait for open registration)\n"
           "7. Back to Main Menu"
        ))

        mode = IntPrompt.ask("Select option", default=7)

        if mode == 7:
            return

        if mode not in [1, 2, 3, 4, 5, 6]:
            console.print("[red]Invalid option![/red]")
            return

        wallets = self.wallet_utils.get_available_wallets()
        if not wallets:
            console.print("[red]No wallets found![/red]")
            return

        console.print("\nAvailable Wallets:")
        for i, wallet in enumerate(wallets, 1):
            console.print(f"{i}. {wallet}")

        console.print("\nSelect wallets (comma-separated numbers, e.g. 1,3,4)")
        selection = Prompt.ask("Selection").strip()

        try:
            indices = [int(i.strip()) - 1 for i in selection.split(',')]
            selected_wallets = [wallets[i] for i in indices if 0 <= i < len(wallets)]
        except:
            console.print("[red]Invalid selection![/red]")
            return

        rpc_endpoint = self._get_rpc_endpoint()

        if mode == 4:
            console.print("\nEnter target subnet ID to monitor")
            target_subnet = IntPrompt.ask("Target Subnet ID")

            wallet_configs = []
            for wallet in selected_wallets:
                password = self._get_wallet_password(wallet)
                if not self.registration_manager.verify_wallet_password(wallet, password):
                    console.print(f"[red]Invalid password for {wallet}[/red]")
                    continue

                hotkeys = self.wallet_utils.get_wallet_hotkeys(wallet)
                if not hotkeys:
                    console.print(f"[red]No hotkeys found for wallet {wallet}![/red]")
                    continue

                console.print(f"\nHotkeys for wallet {wallet}:")
                for i, hotkey in enumerate(hotkeys, 1):
                    console.print(f"{i}. {hotkey}")

                console.print("\nSelect hotkeys (comma-separated numbers, e.g. 1,2,3,4)")
                hotkey_selection = Prompt.ask("Selection").strip()

                try:
                    hotkey_indices = [int(i.strip()) - 1 for i in hotkey_selection.split(',')]
                    selected_hotkeys = [hotkeys[i] for i in hotkey_indices if 0 <= i < len(hotkeys)]

                    for hotkey in selected_hotkeys:
                        wallet_configs.append({
                            'coldkey': wallet,
                            'hotkey': hotkey,
                            'password': password
                        })

                except:
                    console.print(f"[red]Invalid hotkey selection for {wallet}![/red]")
                    continue

            if wallet_configs:
                try:
                    console.print("\n[bold green]Starting DEGEN registration mode...[/bold green]")
                    console.print(f"[yellow]Monitoring for subnet {target_subnet} registration...[/yellow]")
                    
                    if rpc_endpoint:
                        console.print(f"[yellow]Using custom RPC endpoint: {rpc_endpoint}[/yellow]")
                        
                    asyncio.run(self.registration_manager.start_degen_registration(
                        wallet_configs=wallet_configs,
                        target_subnet=target_subnet,
                        background_mode=False,
                        rpc_endpoint=rpc_endpoint
                    ))
                    
                except Exception as e:
                    console.print(f"[red]DEGEN registration error: {str(e)}[/red]")
            return

        subnet_id = IntPrompt.ask("Enter subnet ID for registration", default=1)

        if mode == 1:
            for wallet in selected_wallets:
                wallet_configs = []
                password = self._get_wallet_password(wallet)

                if not self.registration_manager.verify_wallet_password(wallet, password):
                    console.print(f"[red]Invalid password for {wallet}[/red]")
                    continue

                hotkeys = self.wallet_utils.get_wallet_hotkeys(wallet)
                if not hotkeys:
                    console.print(f"[red]No hotkeys found for wallet {wallet}![/red]")
                    continue

                console.print(f"\nHotkeys for wallet {wallet}:")
                for i, hotkey in enumerate(hotkeys, 1):
                    console.print(f"{i}. {hotkey}")

                console.print("\nSelect hotkeys (comma-separated numbers, e.g. 1,2,3,4)")
                hotkey_selection = Prompt.ask("Selection").strip()

                try:
                    hotkey_indices = [int(i.strip()) - 1 for i in hotkey_selection.split(',')]
                    selected_hotkeys = [hotkeys[i] for i in hotkey_indices if 0 <= i < len(hotkeys)]
                except:
                    console.print(f"[red]Invalid hotkey selection for {wallet}![/red]")
                    continue

                for hotkey in selected_hotkeys:
                    wallet_configs.append({
                        'coldkey': wallet,
                        'hotkey': hotkey,
                        'password': password,
                        'prep_time': 15
                    })

                try:
                    asyncio.run(self.registration_manager.start_registration(
                        wallet_configs=wallet_configs,
                        subnet_id=subnet_id,
                        start_block=0,
                        prep_time=15,
                        rpc_endpoint=rpc_endpoint
                    ))
                except Exception as e:
                    console.print(f"[red]Error registering {wallet}: {str(e)}[/red]")

        elif mode == 2:
            wallet_configs = []

            for wallet in selected_wallets:
                password = self._get_wallet_password(wallet)
                if not self.registration_manager.verify_wallet_password(wallet, password):
                    console.print(f"[red]Invalid password for {wallet}[/red]")
                    continue

                prep_time = IntPrompt.ask(
                    f"Enter timing adjustment for {wallet}\n"
                    f"(-19 to +19 seconds,\n"
                    f" negative: start N seconds BEFORE target block,\n"
                    f" positive: wait N seconds AFTER target block)",
                    default=0
                )
                
                if prep_time < 0:
                    prep_time = max(-19, prep_time)
                else:
                    prep_time = min(19, prep_time)

                hotkeys = self.wallet_utils.get_wallet_hotkeys(wallet)
                if not hotkeys:
                    console.print(f"[red]No hotkeys found for wallet {wallet}![/red]")
                    continue

                console.print(f"\nHotkeys for wallet {wallet}:")
                for i, hotkey in enumerate(hotkeys, 1):
                    console.print(f"{i}. {hotkey}")

                console.print("\nSelect hotkeys (comma-separated numbers, e.g. 1,2,3,4)")
                hotkey_selection = Prompt.ask("Selection").strip()

                try:
                    hotkey_indices = [int(i.strip()) - 1 for i in hotkey_selection.split(',')]
                    selected_hotkeys = [hotkeys[i] for i in hotkey_indices if 0 <= i < len(hotkeys)]

                    if len(selected_hotkeys) > 1 and False:
                        console.print(f"[red]Only one hotkey allowed per coldkey in Professional mode![/red]")
                        continue

                    for hotkey in selected_hotkeys:
                        wallet_configs.append({
                            'coldkey': wallet,
                            'hotkey': hotkey,
                            'password': password,
                            'prep_time': prep_time
                        })
                except:
                    console.print(f"[red]Invalid hotkey selection for {wallet}![/red]")
                    continue

            if wallet_configs:
                try:
                    reg_info = self.registration_manager.get_registration_info(subnet_id)
                    if reg_info:
                        self.registration_manager._display_registration_info(reg_info)
                        self.registration_manager._display_registration_config(wallet_configs, subnet_id, reg_info)
                        if Confirm.ask("Proceed with registration?"):
                            max_prep_time = max(abs(cfg['prep_time']) for cfg in wallet_configs)
                            registrations = asyncio.run(self.registration_manager.start_registration(
                                wallet_configs=wallet_configs,
                                subnet_id=subnet_id,
                                start_block=reg_info['next_adjustment_block'],
                                prep_time=max_prep_time,
                                rpc_endpoint=rpc_endpoint
                            ))
                            
                            for reg in registrations.values():
                                if reg.status == "Success":
                                    console.print(f"[green]Successfully registered {reg.coldkey}:{reg.hotkey} with UID {reg.uid}[/green]")
                                elif reg.status == "Failed":
                                    console.print(f"[red]Failed to register {reg.coldkey}:{reg.hotkey} - {reg.error}[/red]")
                except Exception as e:
                    console.print(f"[red]Registration error: {str(e)}[/red]")
                    
        elif mode == 3:
            all_wallet_info = {}
            wallet_passwords = {}
            
            for wallet in selected_wallets:
                password = self._get_wallet_password(wallet)
                if not self.registration_manager.verify_wallet_password(wallet, password):
                    console.print(f"[red]Invalid password for {wallet}[/red]")
                    continue
                    
                wallet_passwords[wallet] = password
                
                hotkeys = self.wallet_utils.get_wallet_hotkeys(wallet)
                if not hotkeys:
                    console.print(f"[red]No hotkeys found for wallet {wallet}![/red]")
                    continue

                console.print(f"\nHotkeys for wallet {wallet}:")
                for i, hotkey in enumerate(hotkeys, 1):
                    console.print(f"{i}. {hotkey}")

                console.print("\nSelect hotkeys (comma-separated numbers, e.g. 1,2,3,4)")
                hotkey_selection = Prompt.ask("Selection").strip()

                try:
                    hotkey_indices = [int(i.strip()) - 1 for i in hotkey_selection.split(',')]
                    selected_hotkeys = [hotkeys[i] for i in hotkey_indices if 0 <= i < len(hotkeys)]
                    
                    if selected_hotkeys:
                        all_wallet_info[wallet] = selected_hotkeys
                except:
                    console.print(f"[red]Invalid hotkey selection for {wallet}![/red]")
                    continue
            
            if not all_wallet_info:
                console.print("[red]No valid wallet/hotkey combinations selected![/red]")
                return
            
            attempts_per_hotkey = IntPrompt.ask(
                f"How many adjustment blocks to try for each hotkey?",
                default=3
            )
            
            console.print("\n[bold]Timing Distribution Range[/bold]")
            console.print("Enter the range of timing values to distribute across coldkeys")
            min_timing = IntPrompt.ask("Minimum timing value (e.g. -20)", default=-20)
            max_timing = IntPrompt.ask("Maximum timing value (e.g. 0)", default=0)
            
            use_coldkey_delay = Confirm.ask("Add delay between transactions from the same coldkey?", default=True)
            coldkey_delay = 6
            if use_coldkey_delay:
                coldkey_delay = IntPrompt.ask("Delay between transactions from the same coldkey (seconds)", default=6)
            else:
                coldkey_delay = 0
            
            coldkeys_count = len(all_wallet_info)
            hotkeys_per_coldkey = [len(hotkeys) for coldkey, hotkeys in all_wallet_info.items()]
            
            console.print(f"\n[cyan]Distributing timing values across {coldkeys_count} coldkeys with {sum(hotkeys_per_coldkey)} total hotkeys...[/cyan]")
            
            timing_values = self.registration_manager.spread_timing_across_hotkeys(
                coldkeys_count,
                hotkeys_per_coldkey,
                min_timing,
                max_timing,
                coldkey_delay
            )
            
            wallet_config_dict = {}
            hotkey_attempts = {}
            
            table = Table(title="Timing Distribution")
            table.add_column("Wallet")
            table.add_column("Hotkey")
            table.add_column("Timing")
            table.add_column("Transaction Order")
            
            all_transaction_timings = []
            wallet_configs = []
            
            for idx, (wallet, hotkeys) in enumerate(all_wallet_info.items()):
                coldkey_timings = timing_values[idx]
                
                wallet_transactions = []
                for hotkey_idx, hotkey in enumerate(hotkeys):
                    timing = coldkey_timings[hotkey_idx]
                    cfg = {
                        'coldkey': wallet,
                        'hotkey': hotkey,
                        'password': wallet_passwords[wallet],
                        'prep_time': timing
                    }
                    wallet_transactions.append(cfg)
                    all_transaction_timings.append((wallet, hotkey, timing))
                    
                    key = f"{wallet}:{hotkey}"
                    hotkey_attempts[key] = attempts_per_hotkey
                
                wallet_transactions.sort(key=lambda x: x['prep_time'])
                wallet_configs.extend(wallet_transactions)
                
                wallet_config_dict[wallet] = {
                    'hotkeys': hotkeys,
                    'password': wallet_passwords[wallet],
                    'prep_time': coldkey_timings[0] if coldkey_timings else 0,
                    'current_hotkey_index': 0,
                    'current_attempt': 0,
                    'max_attempts': attempts_per_hotkey
                }
            
            all_transaction_timings.sort(key=lambda x: x[2])
            
            for order, (wallet, hotkey, timing) in enumerate(all_transaction_timings, 1):
                table.add_row(
                    wallet,
                    hotkey,
                    f"{timing}s",
                    str(order)
                )
            
            console.print(table)
            
            retry_on_failure = Confirm.ask(
                "Automatically retry failed registrations with adjusted timing?",
                default=True
            )
            
            max_retry_attempts = 0
            if retry_on_failure:
                max_retry_attempts = IntPrompt.ask(
                    "Maximum retry attempts per registration",
                    default=3
                )
            
            console.print("\n[bold]Block Selection Method[/bold]")
            console.print("1. Automatic (use next adjustment block)")
            console.print("2. Manual (specify a block number)")
            block_selection_method = IntPrompt.ask("Select option", default=1)
            
            target_block = None
            if block_selection_method == 2:
                target_block = IntPrompt.ask("Enter the target block number", default=0)
                
                console.print(f"\n[yellow]You have chosen to register at block {target_block}.[/yellow]")
                if not Confirm.ask("Are you sure you want to use this block?", default=True):
                    target_block = None
                    block_selection_method = 1
            
            try:
                if block_selection_method == 1:
                    reg_info = self.registration_manager.get_registration_info(subnet_id)
                    if reg_info:
                        self.registration_manager._display_registration_info(reg_info)
                        target_block = reg_info['next_adjustment_block']
                    else:
                        console.print("[red]Failed to get registration information![/red]")
                        
                        if Confirm.ask("[yellow]Would you like to specify a target block manually instead?[/yellow]", default=True):
                            target_block = IntPrompt.ask("Enter the target block number", default=0)
                            console.print(f"\n[yellow]You have chosen to register at block {target_block}.[/yellow]")
                            if not Confirm.ask("Are you sure you want to use this block?", default=True):
                                console.print("[red]Registration cancelled![/red]")
                                return
                        else:
                            console.print("[red]Registration cancelled![/red]")
                            return
                
                if Confirm.ask("Proceed with Auto Registration?"):
                    asyncio.run(self.registration_manager.start_auto_registration(
                        wallet_config_dict,
                        hotkey_attempts,
                        subnet_id,
                        background_mode=False,
                        rpc_endpoint=rpc_endpoint,
                        target_block=target_block,
                        retry_on_failure=retry_on_failure,
                        max_retry_attempts=max_retry_attempts
                    ))
                else:
                    console.print("[yellow]Registration cancelled![/yellow]")
                    
            except Exception as e:
                console.print(f"[red]Auto registration error: {str(e)}[/red]")
                    
        elif mode == 5:
            all_wallet_info = {}
            wallet_passwords = {}
            
            for wallet in selected_wallets:
                password = self._get_wallet_password(wallet)
                if not self.registration_manager.verify_wallet_password(wallet, password):
                    console.print(f"[red]Invalid password for {wallet}[/red]")
                    continue
                    
                wallet_passwords[wallet] = password
                
                hotkeys = self.wallet_utils.get_wallet_hotkeys(wallet)
                if not hotkeys:
                    console.print(f"[red]No hotkeys found for wallet {wallet}![/red]")
                    continue

                console.print(f"\nHotkeys for wallet {wallet}:")
                for i, hotkey in enumerate(hotkeys, 1):
                    console.print(f"{i}. {hotkey}")

                console.print("\nSelect hotkeys (comma-separated numbers, e.g. 1,2,3,4)")
                hotkey_selection = Prompt.ask("Selection").strip()

                try:
                    hotkey_indices = [int(i.strip()) - 1 for i in hotkey_selection.split(',')]
                    selected_hotkeys = [hotkeys[i] for i in hotkey_indices if 0 <= i < len(hotkeys)]
                    
                    if selected_hotkeys:
                        all_wallet_info[wallet] = selected_hotkeys
                except:
                    console.print(f"[red]Invalid hotkey selection for {wallet}![/red]")
                    continue
                    
            if not all_wallet_info:
                console.print("[red]No valid wallet/hotkey combinations selected![/red]")
                return
                
            console.print("\n[bold]Timing Distribution Range[/bold]")
            console.print("Enter the range of timing values to distribute across coldkeys")
            min_timing = IntPrompt.ask("Minimum timing value (e.g. -20)", default=-20)
            max_timing = IntPrompt.ask("Maximum timing value (e.g. 0)", default=0)
            
            use_coldkey_delay = Confirm.ask("Add delay between transactions from the same coldkey?", default=True)
            coldkey_delay = 6
            if use_coldkey_delay:
                coldkey_delay = IntPrompt.ask("Delay between transactions from the same coldkey (seconds)", default=6)
            else:
                coldkey_delay = 0
            
            coldkeys_count = len(all_wallet_info)
            hotkeys_per_coldkey = [len(hotkeys) for coldkey, hotkeys in all_wallet_info.items()]
            
            console.print(f"\n[cyan]Distributing timing values across {coldkeys_count} coldkeys with {sum(hotkeys_per_coldkey)} total hotkeys...[/cyan]")
            
            timing_values = self.registration_manager.spread_timing_across_hotkeys(
                coldkeys_count,
                hotkeys_per_coldkey,
                min_timing,
                max_timing,
                coldkey_delay
            )
            
            wallet_configs = []
            
            table = Table(title="Timing Distribution")
            table.add_column("Wallet")
            table.add_column("Hotkey")
            table.add_column("Timing")
            table.add_column("Transaction Order")
            
            all_transaction_timings = []
            
            for idx, (wallet, hotkeys) in enumerate(all_wallet_info.items()):
                coldkey_timings = timing_values[idx]
                
                wallet_transactions = []
                for hotkey_idx, hotkey in enumerate(hotkeys):
                    timing = coldkey_timings[hotkey_idx]
                    cfg = {
                        'coldkey': wallet,
                        'hotkey': hotkey,
                        'password': wallet_passwords[wallet],
                        'prep_time': timing
                    }
                    wallet_transactions.append(cfg)
                    all_transaction_timings.append((wallet, hotkey, timing))
                
                wallet_transactions.sort(key=lambda x: x['prep_time'])
                wallet_configs.extend(wallet_transactions)
            
            all_transaction_timings.sort(key=lambda x: x[2])
            
            for order, (wallet, hotkey, timing) in enumerate(all_transaction_timings, 1):
                table.add_row(
                    wallet,
                    hotkey,
                    f"{timing}s",
                    str(order)
                )
                
            console.print(table)
            
            retry_on_failure = Confirm.ask(
                "Automatically retry failed registrations with adjusted timing?",
                default=True
            )
            
            max_retry_attempts = 0
            if retry_on_failure:
                max_retry_attempts = IntPrompt.ask(
                    "Maximum retry attempts per registration",
                    default=3
                )
                
            console.print("\n[bold]Block Selection Method[/bold]")
            console.print("1. Automatic (use next adjustment block)")
            console.print("2. Manual (specify a block number)")
            block_selection_method = IntPrompt.ask("Select option", default=1)
            
            target_block = None
            if block_selection_method == 2:
                target_block = IntPrompt.ask("Enter the target block number", default=0)
                
                console.print(f"\n[yellow]You have chosen to register at block {target_block}.[/yellow]")
                if not Confirm.ask("Are you sure you want to use this block?", default=True):
                    target_block = None
                    block_selection_method = 1
            
            try:
                if block_selection_method == 1:
                    reg_info = self.registration_manager.get_registration_info(subnet_id)
                    if reg_info:
                        self.registration_manager._display_registration_info(reg_info)
                        self.registration_manager._display_registration_config(wallet_configs, subnet_id, reg_info)
                        start_block = reg_info['next_adjustment_block']
                    else:
                        console.print("[red]Failed to get registration information![/red]")
                        
                        if Confirm.ask("[yellow]Would you like to specify a target block manually instead?[/yellow]", default=True):
                            target_block = IntPrompt.ask("Enter the target block number", default=0)
                            console.print(f"\n[yellow]You have chosen to register at block {target_block}.[/yellow]")
                            if not Confirm.ask("Are you sure you want to use this block?", default=True):
                                console.print("[red]Registration cancelled![/red]")
                                return
                            start_block = target_block
                        else:
                            console.print("[red]Registration cancelled![/red]")
                            return
                else:
                    manual_config_table = Table(title="Manual Block Registration Configuration")
                    manual_config_table.add_column("Subnet")
                    manual_config_table.add_column("Target Block")
                    manual_config_table.add_column("Coldkeys Count")
                    manual_config_table.add_column("Hotkeys Count")
                    manual_config_table.add_column("Timing Range")
                    
                    manual_config_table.add_row(
                        str(subnet_id),
                        str(target_block),
                        str(len(all_wallet_info)),
                        str(sum(hotkeys_per_coldkey)),
                        f"{min_timing}s to {max_timing}s"
                    )
                    
                    console.print(manual_config_table)
                    start_block = target_block
                
                if Confirm.ask("Proceed with registration?"):
                    max_prep_time = max(abs(cfg['prep_time']) for cfg in wallet_configs)
                    results = asyncio.run(
                        self.registration_manager.start_registration(
                            wallet_configs=wallet_configs,
                            subnet_id=subnet_id,
                            start_block=start_block,
                            prep_time=max_prep_time,
                            rpc_endpoint=rpc_endpoint
                        )
                    )
                    
                    if results:
                        table = Table(title="Registration Results")
                        table.add_column("Wallet")
                        table.add_column("Hotkey")
                        table.add_column("Status") 
                        table.add_column("UID")
                        table.add_column("Details")
                        
                        for key, reg in results.items():
                            coldkey, hotkey = key.split(':')
                            status_color = "green" if reg.status == "Success" else "red"
                            uid = str(reg.uid) if reg.uid is not None else "N/A"
                            details = reg.error if reg.error else ("Success" if reg.status == "Success" else "N/A")
                            
                            table.add_row(
                                coldkey,
                                hotkey,
                                f"[{status_color}]{reg.status}[/{status_color}]",
                                uid,
                                details
                            )
                        
                        console.print(table)
                else:
                    console.print("[yellow]Registration cancelled![/yellow]")
                        
            except Exception as e:
                console.print(f"[red]Registration error: {str(e)}[/red]")
                
        elif mode == 6:
            
            check_interval = IntPrompt.ask("Enter check interval in seconds", default=60)
            max_cost = IntPrompt.ask("Maximum registration cost in TAO (0 for no limit)", default=0)
            
            wallet_configs = []
            for wallet in selected_wallets:
                password = self._get_wallet_password(wallet)
                if not self.registration_manager.verify_wallet_password(wallet, password):
                    console.print(f"[red]Invalid password for {wallet}[/red]")
                    continue

                hotkeys = self.wallet_utils.get_wallet_hotkeys(wallet)
                if not hotkeys:
                    console.print(f"[red]No hotkeys found for wallet {wallet}![/red]")
                    continue

                console.print(f"\nHotkeys for wallet {wallet}:")
                for i, hotkey in enumerate(hotkeys, 1):
                    console.print(f"{i}. {hotkey}")

                console.print("\nSelect hotkeys (comma-separated numbers, e.g. 1,2,3,4)")
                hotkey_selection = Prompt.ask("Selection").strip()

                try:
                    hotkey_indices = [int(i.strip()) - 1 for i in hotkey_selection.split(',')]
                    selected_hotkeys = [hotkeys[i] for i in hotkey_indices if 0 <= i < len(hotkeys)]

                    for hotkey in selected_hotkeys:
                        wallet_configs.append({
                            'coldkey': wallet,
                            'hotkey': hotkey,
                            'password': password,
                            'prep_time': -4
                        })
                except:
                    console.print(f"[red]Invalid hotkey selection for {wallet}![/red]")
                    continue
            
            if not wallet_configs:
                console.print("[red]No valid wallet/hotkey configurations![/red]")
                return
                
            try:
                console.print(f"[cyan]Starting registration monitor for subnet {subnet_id}...[/cyan]")
                console.print(f"[cyan]Checking every {check_interval} seconds for open registration...[/cyan]")
                console.print("[yellow]Press Ctrl+C to stop monitoring at any time[/yellow]")
                
                asyncio.run(self.registration_manager.start_registration_monitor(
                    wallet_configs=wallet_configs,
                    subnet_id=subnet_id,
                    check_interval=check_interval,
                    max_cost=max_cost,
                    rpc_endpoint=rpc_endpoint
                ))
            except Exception as e:
                console.print(f"[red]Error in registration monitor: {str(e)}[/red]")

class WalletCreationMenu:
    def __init__(self, wallet_manager, config):
        self.wallet_manager = wallet_manager
        self.config = config

    def show(self):
        while True:
            console.print("\n[bold]Create Wallet Menu[/bold]")
            console.print(Panel.fit(
                "1. Create new coldkey with hotkeys\n"
                "2. Add hotkeys to existing coldkey\n"
                "3. Back to Main Menu"
            ))

            choice = IntPrompt.ask("Select option", default=3)

            if choice == 3:
                return

            if choice == 1:
                coldkey = Prompt.ask("Enter coldkey name")
                num_hotkeys = IntPrompt.ask("Enter number of hotkeys", default=1)
                password = Prompt.ask("Enter password", password=True)

                with Status("[bold green]Creating wallet...", spinner="dots") as status:
                    try:
                        wallet_info = self.wallet_manager.create_wallet(coldkey, num_hotkeys, password)
                        if wallet_info:
                            console.print("\n[green]Wallet created successfully![/green]")
                            console.print("\n[bold]Coldkey Information:[/bold]")
                            console.print(Panel(
                                f"[yellow]Mnemonic:[/yellow] {wallet_info['coldkey']['mnemonic']}\n"
                                f"[cyan]Address:[/cyan] {wallet_info['coldkey']['address']}",
                                expand=True
                            ))

                            console.print("\n[bold]Hotkey Information:[/bold]")
                            for hotkey in wallet_info['hotkeys']:
                                console.print(Panel(
                                    f"[bold]Hotkey {hotkey['name']}[/bold]\n"
                                    f"[cyan]Address:[/cyan] {hotkey['address']}",
                                    expand=True
                                ))
                    except Exception as e:
                        console.print(f"\n[red]Error creating wallet: {str(e)}[/red]")

            elif choice == 2:
                coldkey = Prompt.ask("Enter existing coldkey name")
                num_hotkeys = IntPrompt.ask("Enter number of new hotkeys", default=1)

                with Status("[bold green]Creating hotkeys...", spinner="dots") as status:
                    try:
                        result = self.wallet_manager.add_hotkeys(coldkey, num_hotkeys)
                        if result:
                            console.print("\n[green]Hotkeys added successfully![/green]")
                            console.print("\n[bold]Hotkey Information:[/bold]")
                            for hotkey in result['hotkeys'][-num_hotkeys:]:
                                console.print(Panel(
                                    f"[bold]Hotkey {hotkey['name']}[/bold]\n"
                                    f"[cyan]Address:[/cyan] {hotkey['address']}",
                                    expand=True
                                ))
                    except Exception as e:
                        console.print(f"\n[red]Error adding hotkeys: {str(e)}[/red]")

class StatsMenu:
    def __init__(self, stats_manager, wallet_utils):
        self.stats_manager = stats_manager
        self.wallet_utils = wallet_utils

    def _display_wallet_stats(self, stats: Dict):
        if not stats:
            return

        total_alpha_usd = 0.0
        for subnet in stats['subnets']:
            subnet_rate_usd = subnet['rate_usd']
            for neuron in subnet['neurons']:
                total_alpha_usd += neuron['stake'] * subnet_rate_usd

        console.print(f"\n[bold]{stats['coldkey']} ({stats['wallet_address']})[/bold]")
        console.print(f"Balance: {stats['balance']:.9f} τ")
        console.print(f"Total daily reward: ${sum(sum(n['daily_rewards_usd'] for n in subnet['neurons']) for subnet in stats['subnets']):.2f}")
        console.print(f"Total Alpha in $: ${total_alpha_usd:.2f}")

        for subnet in stats['subnets']:
            subnet['neurons'].sort(key=lambda x: x['stake'], reverse=True)
            
            table = Table(title=f"Subnet {subnet['netuid']} (Rate: ${subnet['rate_usd']:.4f})")
            table.add_column("Hotkey")
            table.add_column("UID")
            table.add_column("Alpha Stake", justify="right")
            table.add_column("Rank", justify="right")
            table.add_column("Trust", justify="right")
            table.add_column("Consensus", justify="right")
            table.add_column("Incentive", justify="right")
            table.add_column("Dividends", justify="right")
            table.add_column("Emission(ρ)", justify="right")
            table.add_column("Daily Alpha τ", justify="right")
            table.add_column("Daily USD", justify="right")

            for neuron in subnet['neurons']:
                table.add_row(
                    neuron['hotkey'],
                    str(neuron['uid']),
                    f"{neuron['stake']:.9f}",
                    f"{neuron['rank']:.4f}",
                    f"{neuron['trust']:.4f}",
                    f"{neuron['consensus']:.4f}",
                    f"{neuron['incentive']:.4f}",
                    f"{neuron['dividends']:.4f}",
                    f"{neuron['emission']}",
                    f"{neuron['daily_rewards_alpha']:.9f}",
                    f"${neuron['daily_rewards_usd']:.2f}"
                )

            console.print(table)
            
        if 'timestamp' in stats:
            try:
                timestamp = datetime.fromisoformat(stats['timestamp'])
                formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                console.print(f"\n[dim]Last updated: {formatted_time}[/dim]")
            except Exception:
                pass

    def _parse_wallet_selection(self, selection: str, wallets: List[str]) -> List[str]:
        if selection.strip().lower() == 'all':
            return wallets
            
        try:
            indices = [int(i.strip()) - 1 for i in selection.split(',')]
            return [wallets[i] for i in indices if 0 <= i < len(wallets)]
        except:
            console.print("[red]Invalid selection![/red]")
            return []

    async def show(self):
        while True:
            console.print("\n[bold]Wallet Statistics Menu[/bold]")
            console.print(Panel.fit(
                "1. Check Wallet Stats\n"
                "2. Back to Main Menu"
            ))

            choice = IntPrompt.ask("Select option", default=2)

            if choice == 2:
                return

            if choice != 1:
                console.print("[red]Invalid option![/red]")
                continue

            console.print("\n[bold]Wallet Statistics[/bold]")
            wallets = self.wallet_utils.get_available_wallets()
            if not wallets:
                console.print("[red]No wallets found![/red]")
                return

            console.print("\nAvailable Wallets:")
            for i, wallet in enumerate(wallets, 1):
                console.print(f"{i}. {wallet}")

            console.print("\nSelect wallets (comma-separated numbers, e.g. 1,3,4 or 'all')")
            selection = Prompt.ask("Selection").strip()

            selected_wallets = self._parse_wallet_selection(selection, wallets)
            if not selected_wallets:
                continue

            console.print("\n1. Check all subnets")
            console.print("2. Check specific subnets")
            console.print("3. Hide zero balances")
            subnet_choice = IntPrompt.ask("Select option", default=1)

            subnet_list = None
            hide_zeros = False

            if subnet_choice == 2:
                subnet_input = Prompt.ask("\nEnter subnet numbers (comma-separated)")
                try:
                    subnet_list = [int(s.strip()) for s in subnet_input.split(',')]
                except:
                    console.print("[red]Invalid subnet input![/red]")
                    continue
            elif subnet_choice == 3:
                hide_zeros = True
                
            total_balance = 0.0
            total_daily_reward_usd = 0.0
            total_alpha_usd_value = 0.0
            active_wallets = set()
            active_subnets = set()
            active_neurons = 0
            all_wallet_stats = []

            for wallet_index, wallet in enumerate(selected_wallets):
                console.print(f"\nProcessing wallet {wallet} ({wallet_index+1}/{len(selected_wallets)})...")
                
                try:
                    console.print(f"Finding active subnets for {wallet}...")
                    
                    if subnet_list is None:
                        active_subnets_list = self.stats_manager.get_active_subnets_direct(wallet)
                    else:
                        active_subnets_list = subnet_list
                    
                    console.print(f"Getting data for {wallet} ({len(active_subnets_list)} subnets)...")
                    
                    stats = await self.stats_manager.get_wallet_stats(wallet, active_subnets_list, hide_zeros)
                    
                    if stats:
                        console.print(f"[green]Completed data collection for {wallet}[/green]")
                        self._display_wallet_stats(stats)
                        
                        total_balance += stats['balance']
                        
                        wallet_daily_reward = sum(sum(n['daily_rewards_usd'] for n in subnet['neurons']) 
                                               for subnet in stats['subnets'])
                        total_daily_reward_usd += wallet_daily_reward
                        
                        wallet_alpha_usd = 0.0
                        
                        if stats['subnets']:
                            active_wallets.add(wallet)
                            
                            for subnet in stats['subnets']:
                                subnet_rate_usd = subnet['rate_usd']
                                active_subnets.add(subnet['netuid'])
                                
                                for neuron in subnet['neurons']:
                                    wallet_alpha_usd += neuron['stake'] * subnet_rate_usd
                                    if neuron['stake'] > 0:
                                        active_neurons += 1
                        
                        total_alpha_usd_value += wallet_alpha_usd
                        all_wallet_stats.append(stats)
                    else:
                        console.print(f"[yellow]No stats found for wallet {wallet}[/yellow]")
                except Exception as e:
                    console.print(f"[red]Error getting stats for {wallet}: {str(e)}[/red]")
            
            if all_wallet_stats:
                self.display_wallets_summary(
                    total_balance, 
                    total_daily_reward_usd, 
                    total_alpha_usd_value,
                    len(active_wallets),
                    len(selected_wallets),
                    len(active_subnets),
                    active_neurons
                )

    def display_wallets_summary(self, total_balance: float, total_daily_reward_usd: float, 
                             total_alpha_usd_value: float, active_wallets_count: int = 0, 
                             total_wallets_count: int = 0, active_subnets_count: int = 0,
                             active_neurons_count: int = 0):
        console.print("\n" + "="*80)
        console.print("[bold cyan]OVERALL SUMMARY FOR ALL WALLETS[/bold cyan]")
        console.print("="*80)
        
        table = Table(title="Total Statistics", show_header=True, header_style="bold")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        
        table.add_row("Total TAO Balance", f"{total_balance:.9f} τ")
        table.add_row("Total Daily Rewards", f"${total_daily_reward_usd:.2f}")
        table.add_row("Total Alpha TAO Value", f"${total_alpha_usd_value:.2f}")
        
        if total_wallets_count > 0:
            table.add_row("Active Wallets", f"{active_wallets_count}/{total_wallets_count}")
        
        if active_subnets_count > 0:
            table.add_row("Active Subnets", str(active_subnets_count))
            
        if active_neurons_count > 0:
            table.add_row("Active Neurons (Hotkeys)", str(active_neurons_count))
        
        weekly_rewards = total_daily_reward_usd * 7
        table.add_row("Weekly Rewards Projection", f"${weekly_rewards:.2f}")
        
        console.print(table)
        console.print("="*80)

    def _add_export_option(self, stats: Dict):
        if not stats:
            return
            
        if Confirm.ask("\nExport data?"):
            console.print("\n1. Export to JSON")
            console.print("2. Export to CSV")
            export_option = IntPrompt.ask("Select format", default=1)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            coldkey = stats['coldkey']
            
            if export_option == 1:
                filename = f"export_{coldkey}_{timestamp}.json"
                with open(filename, 'w') as f:
                    json.dump(stats, f, indent=2)
                console.print(f"[green]Data exported to {filename}[/green]")
                
            elif export_option == 2:
                filename = f"export_{coldkey}_{timestamp}.csv"
                
                with open(filename, 'w', newline='') as f:
                    import csv
                    writer = csv.writer(f)
                    writer.writerow([
                        'Coldkey', 'Subnet', 'Hotkey', 'UID', 'Stake', 'Rank',
                        'Trust', 'Consensus', 'Incentive', 'Dividends', 'Emission',
                        'Daily Alpha', 'Daily USD', 'Rate USD'
                    ])
                    
                    for subnet in stats['subnets']:
                        subnet_id = subnet['netuid']
                        rate_usd = subnet['rate_usd']
                        
                        for neuron in subnet['neurons']:
                            writer.writerow([
                                stats['coldkey'],
                                subnet_id,
                                neuron['hotkey'],
                                neuron['uid'],
                                neuron['stake'],
                                neuron['rank'],
                                neuron['trust'],
                                neuron['consensus'],
                                neuron['incentive'],
                                neuron['dividends'],
                                neuron['emission'],
                                neuron['daily_rewards_alpha'],
                                neuron['daily_rewards_usd'],
                                rate_usd
                            ])
                
                console.print(f"[green]Data exported to {filename}[/green]")

class BalanceMenu:
    def __init__(self, stats_manager, wallet_utils):
        self.stats_manager = stats_manager
        self.wallet_utils = wallet_utils

    def show(self):
        while True:
            console.print("\n[bold]Balance Menu[/bold]")
            console.print(Panel.fit(
                "1. Check TAO Balance/Addresses\n"
                "2. Back to Main Menu"
            ))

            choice = IntPrompt.ask("Select option", default=2)

            if choice == 2:
                return

            if choice != 1:
                console.print("[red]Invalid option![/red]")
                continue

            wallets = self.wallet_utils.get_available_wallets()
            if not wallets:
                console.print("[red]No wallets found![/red]")
                return

            console.print("\nAvailable Wallets:")
            for i, wallet in enumerate(wallets, 1):
                console.print(f"{i}. {wallet}")

            console.print("\nSelect wallets (comma-separated numbers, e.g. 1,3,4 or 'all')")
            selection = Prompt.ask("Selection").strip().lower()

            if selection == 'all':
                selected_wallets = wallets
            else:
                try:
                    indices = [int(i.strip()) - 1 for i in selection.split(',')]
                    selected_wallets = [wallets[i] for i in indices if 0 <= i < len(wallets)]
                except:
                    console.print("[red]Invalid selection![/red]")
                    continue

            table = Table(title="TAO Balances", show_header=True, header_style="bold")
            table.add_column("Wallet")
            table.add_column("Address", width=50)
            table.add_column("Balance (τ)")

            total_balance = 0.0

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True
            ) as progress:
                task = progress.add_task("[cyan]Checking balances...", total=len(selected_wallets))

                for wallet_name in selected_wallets:
                    try:
                        wallet = bt.wallet(name=wallet_name)
                        balance = self.stats_manager.subtensor.get_balance(
                            wallet.coldkeypub.ss58_address
                        )
                        balance_float = float(balance)
                        total_balance += balance_float
                        table.add_row(
                            wallet_name,
                            wallet.coldkeypub.ss58_address,
                            f"{balance_float:.2f}"
                        )
                    except Exception as e:
                        table.add_row(
                            wallet_name,
                            "[red]Error getting address[/red]",
                            f"[red]Error: {str(e)}[/red]"
                        )
                    progress.update(task, advance=1)


            table.add_row(
                "[bold]Total[/bold]",
                "",
                f"[bold]{total_balance:.2f}[/bold]",
                style="bold green"
            )

            console.print("\n")
            console.print(table)

            if not Confirm.ask("Check another balance?"):
                return

class TransferMenu:
    def __init__(self, transfer_manager, wallet_utils, config):
        self.transfer_manager = transfer_manager
        self.wallet_utils = wallet_utils
        self.config = config

    def show(self):
        console.print("\n[bold]TAO Transfer and Unstake Alpha TAO Menu[/bold]")
        console.print(Panel.fit(
            "1. Transfer TAO\n"
            "2. Batch Transfer TAO\n"
            "3. Collect TAO\n"
            "4. Unstake Alpha TAO\n"
            "5. Back to Main Menu"
        ))

        choice = IntPrompt.ask("Select option", default=5)

        if choice == 5:
            return

        if choice == 1:
            self._handle_transfer()
        elif choice == 2:
            self._handle_batch_transfer()
        elif choice == 3:
            self._handle_collect_tao()
        elif choice == 4:
            self._handle_unstake_alpha()

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
            password = Prompt.ask("Enter wallet password", password=True)

            with Status("[bold green]Processing transfer...", spinner="dots"):
                try:
                    if not self.transfer_manager.verify_wallet_password(source_wallet, password):
                        console.print("[red]Invalid password![/red]")
                        return

                    if self.transfer_manager.transfer_tao(source_wallet, dest_address, amount, password):
                        console.print("[green]Transfer completed successfully![/green]")
                    else:
                        console.print("[red]Transfer failed![/red]")
                except Exception as e:
                    console.print(f"[red]Error: {str(e)}[/red]")

    def _handle_unstake_alpha(self):
        wallets = self.wallet_utils.get_available_wallets()
        if not wallets:
            console.print("[red]No wallets found![/red]")
            return

        console.print("\n1. Unstake from specific subnet")
        console.print("2. Unstake from all subnets")
        subnet_choice = IntPrompt.ask("Select option", default=1)

        subnet_list = None
        if subnet_choice == 1:
            subnet_input = Prompt.ask("\nEnter subnet number")
            try:
                subnet_list = [int(subnet_input.strip())]
            except:
                console.print("[red]Invalid subnet input![/red]")
                return

        console.print("\nAvailable Wallets:")
        for i, wallet in enumerate(wallets, 1):
            console.print(f"{i}. {wallet}")

        console.print("\nSelect wallets (comma-separated numbers, e.g. 1,3,4 or 'all')")
        selection = Prompt.ask("Selection").strip().lower()

        if selection == 'all':
            selected_wallets = wallets
        else:
            try:
                indices = [int(i.strip()) - 1 for i in selection.split(',')]
                selected_wallets = [wallets[i] for i in indices if 0 <= i < len(wallets)]
            except:
                console.print("[red]Invalid selection![/red]")
                return

        console.print("\nHow would you like to process unstaking?")
        console.print("1. Use same password for all wallets (automatic unstaking)")
        console.print("2. Enter password for each wallet separately")
        process_choice = IntPrompt.ask("Select option", default=1)

        shared_password = None
        auto_unstake = False

        if process_choice == 1:
            default_password = self.config.get('wallet.default_password')
            if default_password:
                shared_password = Prompt.ask(
                    f"Enter password for all wallets (press Enter to use default)",
                    password=True,
                    show_default=False
                )
                shared_password = shared_password if shared_password else default_password
            else:
                shared_password = Prompt.ask("Enter password for all wallets", password=True)

            invalid_wallets = []
            for wallet in selected_wallets:
                if not self.transfer_manager.verify_wallet_password(wallet, shared_password):
                    invalid_wallets.append(wallet)

            if invalid_wallets:
                console.print(f"[red]Password is invalid for wallets: {', '.join(invalid_wallets)}[/red]")
                return

            default_tolerance = 0.45
            tolerance = Prompt.ask(
                f"Enter tolerance value (default: {default_tolerance})",
                default=str(default_tolerance)
            )
            tolerance = float(tolerance)

            auto_unstake = True

        stake_summary = {}

        for wallet in selected_wallets:
            try:
                with Status("[bold green]Getting stake information...", spinner="dots"):
                    stake_info = self.transfer_manager.get_alpha_stake_info(wallet, subnet_list)

                if not stake_info:
                    console.print(f"[yellow]No active Alpha stakes found for wallet {wallet}![/yellow]")
                    continue

                self.transfer_manager.display_alpha_stake_summary(stake_info)

                wallet_summary = {}
                for subnet_info in stake_info:
                    netuid = subnet_info['netuid']
                    wallet_summary[netuid] = {
                        'before': {},
                        'after': {}
                    }
                    
                    for hotkey_info in subnet_info['hotkeys']:
                        if hotkey_info['stake'] > 0:
                            wallet_summary[netuid]['before'][hotkey_info['name']] = {
                                'stake': hotkey_info['stake'],
                                'address': hotkey_info['address'],
                                'uid': hotkey_info['uid']
                            }

                stake_summary[wallet] = wallet_summary

                password = shared_password
                if not password:
                    default_password = self.config.get('wallet.default_password')
                    if default_password:
                        password = Prompt.ask(
                            f"Enter password for {wallet} (press Enter to use default)",
                            password=True,
                            show_default=False
                        )
                        password = password if password else default_password
                    else:
                        password = Prompt.ask(f"Enter wallet password", password=True)

                    if not self.transfer_manager.verify_wallet_password(wallet, password):
                        console.print(f"[red]Invalid password for {wallet}![/red]")
                        continue

                for subnet_info in stake_info:
                    netuid = subnet_info['netuid']
                    console.print(f"\n[bold]Processing subnet {netuid}[/bold]")
                    
                    hotkeys_with_stake = [h for h in subnet_info['hotkeys'] if h['stake'] > 0]
                    
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    ) as progress:
                        unstake_task = progress.add_task(f"[cyan]Unstaking from subnet {netuid}...", total=len(hotkeys_with_stake))
                        
                        for hotkey_info in subnet_info['hotkeys']:
                            if hotkey_info['stake'] > 0:
                                hotkey = hotkey_info['name']
                                stake_amount = hotkey_info['stake']
                                safe_amount = stake_amount * 0.99

                                if auto_unstake:
                                    try:
                                        success = self.transfer_manager.unstake_alpha(
                                            wallet,
                                            hotkey,
                                            netuid,
                                            safe_amount,
                                            password,
                                            tolerance=tolerance
                                        )
                                        if success:
                                            console.print(f"[green]Successfully unstaked from {hotkey}![/green]")
                                            stake_summary[wallet][netuid]['after'][hotkey] = {
                                                'success': True
                                            }
                                        else:
                                            console.print(f"[red]Failed to unstake from {hotkey}[/red]")
                                            stake_summary[wallet][netuid]['after'][hotkey] = {
                                                'success': False
                                            }
                                    except Exception as e:
                                        console.print(f"[red]Error unstaking from {hotkey}: {str(e)}[/red]")
                                        stake_summary[wallet][netuid]['after'][hotkey] = {
                                            'success': False,
                                            'error': str(e)
                                        }

                                    progress.update(unstake_task, advance=1)
                                    time.sleep(1)
                                else:
                                    if Confirm.ask(
                                        f"Unstake {safe_amount:.6f} Alpha TAO from hotkey {hotkey} in subnet {netuid}?"
                                    ):
                                        default_tolerance = 0.45
                                        tolerance = Prompt.ask(
                                            f"Enter tolerance value (default: {default_tolerance})",
                                            default=str(default_tolerance)
                                        )
                                        tolerance = float(tolerance)

                                        try:
                                            success = self.transfer_manager.unstake_alpha(
                                                wallet,
                                                hotkey,
                                                netuid,
                                                safe_amount,
                                                password,
                                                tolerance=tolerance
                                            )
                                            if success:
                                                console.print(f"[green]Successfully unstaked from {hotkey}![/green]")
                                                stake_summary[wallet][netuid]['after'][hotkey] = {
                                                    'success': True
                                                }
                                            else:
                                                console.print(f"[red]Failed to unstake from {hotkey}[/red]")
                                                stake_summary[wallet][netuid]['after'][hotkey] = {
                                                    'success': False
                                                }
                                        except Exception as e:
                                            console.print(f"[red]Error unstaking from {hotkey}: {str(e)}[/red]")
                                            stake_summary[wallet][netuid]['after'][hotkey] = {
                                                'success': False,
                                                'error': str(e)
                                            }

                                        progress.update(unstake_task, advance=1)
                                        time.sleep(1)
                                    else:
                                        stake_summary[wallet][netuid]['after'][hotkey] = {
                                            'success': None,
                                        }
                                        progress.update(unstake_task, advance=1)

            except Exception as e:
                console.print(f"[red]Error processing wallet {wallet}: {str(e)}[/red]")
        
        with Status("[bold cyan]Checking current balances after unstaking...", spinner="dots"):
            for wallet_name, wallet_data in stake_summary.items():
                try:
                    current_stake_info = self.transfer_manager.get_alpha_stake_info(wallet_name, list(wallet_data.keys()))
                    
                    current_stakes = {}
                    for subnet_info in current_stake_info:
                        netuid = subnet_info['netuid']
                        if netuid not in current_stakes:
                            current_stakes[netuid] = {}
                            
                        for hotkey_info in subnet_info['hotkeys']:
                            current_stakes[netuid][hotkey_info['name']] = hotkey_info['stake']
                    
                    for netuid, subnet_data in wallet_data.items():
                        for hotkey, hotkey_data in subnet_data['after'].items():
                            if netuid in current_stakes and hotkey in current_stakes[netuid]:
                                hotkey_data['stake'] = current_stakes[netuid][hotkey]
                            elif hotkey_data.get('success', False):
                                hotkey_data['stake'] = 0
                            else:
                                hotkey_data['stake'] = subnet_data['before'][hotkey]['stake']
                        
                        for hotkey in subnet_data['before']:
                            if hotkey not in subnet_data['after']:
                                subnet_data['after'][hotkey] = {
                                    'stake': current_stakes.get(netuid, {}).get(hotkey, 0),
                                    'success': False,
                                    'error': 'Not processed'
                                }
                
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not get updated balance data for {wallet_name}: {str(e)}[/yellow]")
                    for netuid, subnet_data in wallet_data.items():
                        for hotkey, hotkey_data in subnet_data['after'].items():
                            if 'stake' not in hotkey_data:
                                if hotkey_data.get('success', False):
                                    hotkey_data['stake'] = 0
                                else:
                                    hotkey_data['stake'] = subnet_data['before'][hotkey]['stake']
        
        self._display_unstaking_summary(stake_summary)

    def _display_unstaking_summary(self, stake_summary):
        console.print("\n[bold cyan]===== Unstaking Summary =====[/bold cyan]")
        
        total_before_all_wallets = 0
        total_after_all_wallets = 0
        total_difference_all_wallets = 0
        
        for wallet, wallet_data in stake_summary.items():
            console.print(f"\n[bold]Wallet: {wallet}[/bold]")
            
            wallet_total_before = 0
            wallet_total_after = 0
            
            for netuid, subnet_data in wallet_data.items():
                table = Table(title=f"Subnet {netuid} Results")
                table.add_column("Hotkey", style="cyan")
                table.add_column("UID", justify="right")
                table.add_column("Before Stake", justify="right")
                table.add_column("After Stake", justify="right")
                table.add_column("Difference", justify="right")
                table.add_column("Status", justify="center")
                
                total_before = 0
                total_after = 0
                
                for hotkey, before_data in subnet_data['before'].items():
                    before_stake = before_data['stake']
                    total_before += before_stake
                    
                    after_data = subnet_data['after'].get(hotkey, {'stake': before_stake, 'success': False})
                    after_stake = after_data.get('stake', before_stake)
                    total_after += after_stake
                    
                    difference = before_stake - after_stake
                    
                    status = "❓ Unknown"
                    status_style = "yellow"
                    
                    if 'success' in after_data:
                        if after_data['success'] is True:
                            if after_stake > 0:
                                status = "⚠️ Partial"
                                status_style = "yellow"
                            else:
                                status = "✅ Successful"
                                status_style = "green"
                        elif after_data['success'] is False:
                            status = "❌ Failed"
                            status_style = "red"
                        elif after_data['success'] is None:
                            status = "⏭️ Skipped"
                            status_style = "yellow"
                    
                    table.add_row(
                        hotkey,
                        str(before_data['uid']),
                        f"{before_stake:.9f}",
                        f"{after_stake:.9f}",
                        f"{difference:.9f}",
                        f"[{status_style}]{status}[/{status_style}]"
                    )
                
                total_difference = total_before - total_after
                table.add_row(
                    "[bold]Total[/bold]",
                    "",
                    f"[bold]{total_before:.9f}[/bold]",
                    f"[bold]{total_after:.9f}[/bold]",
                    f"[bold]{total_difference:.9f}[/bold]",
                    "",
                    style="bold"
                )
                
                console.print(table)
                
                wallet_total_before += total_before
                wallet_total_after += total_after
            
            wallet_total_difference = wallet_total_before - wallet_total_after
            
            console.print(f"[bold]Wallet Total:[/bold] Unstaked {wallet_total_difference:.9f} Alpha TAO " +
                         f"({wallet_total_before:.9f} → {wallet_total_after:.9f})")
            
            total_before_all_wallets += wallet_total_before
            total_after_all_wallets += wallet_total_after
            total_difference_all_wallets += wallet_total_difference
        
        if len(stake_summary) > 1:
            console.print("\n[bold cyan]===== Grand Total =====[/bold cyan]")
            console.print(f"[bold]Total Unstaked:[/bold] {total_difference_all_wallets:.9f} Alpha TAO " +
                         f"({total_before_all_wallets:.9f} → {total_after_all_wallets:.9f})")
            
            tao_price = self._get_tao_price()
            if tao_price:
                usd_value = total_difference_all_wallets * tao_price
                console.print(f"[bold]USD Value:[/bold] ${usd_value:.2f} (at ${tao_price:.2f} per TAO)")
        
    def _get_tao_price(self):
        try:
            if hasattr(self.transfer_manager, 'stats_manager') and hasattr(self.transfer_manager.stats_manager, '_get_tao_price'):
                return self.transfer_manager.stats_manager._get_tao_price()
            return None
        except:
            return None
                
    def _handle_batch_transfer(self):
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

        addresses_input = Prompt.ask("Enter destination wallet addresses (comma-separated SS58 format(5DygFNT..,5FUQnL..))").strip()
        addresses = [addr.strip() for addr in addresses_input.split(',') if addr.strip()]
        
        invalid_addresses = []
        for addr in addresses:
            if not addr.startswith('5'):
                invalid_addresses.append(addr)
        
        if invalid_addresses:
            console.print(f"[red]Invalid destination address format for: {', '.join(invalid_addresses)}[/red]")
            return
        
        try:
            amount_per_address = float(Prompt.ask("Enter amount of TAO to transfer to each address"))
            if amount_per_address <= 0:
                console.print("[red]Amount must be greater than 0![/red]")
                return
        except ValueError:
            console.print("[red]Invalid amount![/red]")
            return
        
        total_amount = amount_per_address * len(addresses)
        
        console.print("\n[bold]Batch Transfer Summary:[/bold]")
        console.print(f"Source wallet: {source_wallet}")
        console.print(f"Number of destination addresses: {len(addresses)}")
        console.print(f"Amount per address: {amount_per_address} TAO")
        console.print(f"Total amount to transfer: {total_amount} TAO")
        
        try:
            wallet = bt.wallet(name=source_wallet)
            balance = self.transfer_manager.subtensor.get_balance(wallet.coldkeypub.ss58_address)
            console.print(f"Current wallet balance: {float(balance)} TAO")
            
            if float(balance) < total_amount:
                console.print(f"[red]Insufficient balance! Required: {total_amount} TAO, Available: {float(balance)} TAO[/red]")
                return
        except Exception as e:
            console.print(f"[red]Error checking wallet balance: {str(e)}[/red]")
            return

        if Confirm.ask(f"Transfer {amount_per_address} TAO to each of {len(addresses)} addresses for a total of {total_amount} TAO?"):
            password = Prompt.ask("Enter wallet password", password=True)

            if not self.transfer_manager.verify_wallet_password(source_wallet, password):
                console.print("[red]Invalid password![/red]")
                return
            
            successful_transfers = 0
            failed_transfers = 0
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task(f"[cyan]Processing batch transfer...", total=len(addresses))
                
                for i, dest_address in enumerate(addresses, 1):
                    progress.update(task, description=f"[cyan]Processing transfer {i}/{len(addresses)} to {dest_address[:10]}...[/cyan]")
                    
                    try:
                        success = self.transfer_manager.transfer_tao(source_wallet, dest_address, amount_per_address, password)
                        if success:
                            successful_transfers += 1
                        else:
                            failed_transfers += 1
                            console.print(f"[red]Transfer to {dest_address} failed![/red]")
                    except Exception as e:
                        failed_transfers += 1
                        console.print(f"[red]Error transferring to {dest_address}: {str(e)}[/red]")
                    
                    progress.update(task, advance=1)
            
            console.print("\n[bold]Batch Transfer Results:[/bold]")
            console.print(f"[green]Successful transfers: {successful_transfers}[/green]")
            if failed_transfers > 0:
                console.print(f"[red]Failed transfers: {failed_transfers}[/red]")
            console.print(f"Total TAO transferred: {successful_transfers * amount_per_address}")

    def _handle_collect_tao(self):

        wallets = self.wallet_utils.get_available_wallets()
        if not wallets:
            console.print("[red]No wallets found![/red]")
            return

        console.print("\nAvailable Source Wallets:")
        for i, wallet in enumerate(wallets, 1):
            console.print(f"{i}. {wallet}")

        console.print("\nSelect wallets to collect from (comma-separated numbers, e.g., 1,3,4 or 'all')")
        selection = Prompt.ask("Selection").strip().lower()

        if selection == 'all':
            selected_wallets = wallets
        else:
            try:
                indices = [int(i.strip()) - 1 for i in selection.split(',')]
                selected_wallets = [wallets[i] for i in indices if 0 <= i < len(wallets)]
            except:
                console.print("[red]Invalid selection![/red]")
                return

        if not selected_wallets:
            console.print("[red]No wallets selected![/red]")
            return

        dest_address = Prompt.ask("Enter destination wallet address (SS58 format)")
        if not dest_address.startswith('5'):
            console.print("[red]Invalid destination address format![/red]")
            return

        dest_is_selected = False
        for wallet_name in selected_wallets:
            try:
                wallet = bt.wallet(name=wallet_name)
                if wallet.coldkeypub.ss58_address == dest_address:
                    dest_is_selected = True
                    console.print(f"[yellow]Note: Destination address belongs to wallet '{wallet_name}'[/yellow]")
                    break
            except Exception as e:
                console.print(f"[yellow]Warning: Could not check if {wallet_name} matches destination: {str(e)}[/yellow]")

        reserve_amount = 0.0005
        reserve_amount_display = 0.0005

        use_same_password = Confirm.ask("Use the same password for all wallets?", default=True)
        
        common_password = None
        if use_same_password:
            common_password = Prompt.ask("Enter common wallet password", password=True)
            console.print("Decrypting...")
            
            invalid_wallets = []
            for wallet_name in selected_wallets:
                if not self.transfer_manager.verify_wallet_password(wallet_name, common_password):
                    invalid_wallets.append(wallet_name)
            
            if invalid_wallets:
                console.print(f"[red]Password is invalid for wallets: {', '.join(invalid_wallets)}[/red]")
                return
            console.print("Decrypting...")

        wallet_balances = {}
        total_to_transfer = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Checking wallet balances...", total=len(selected_wallets))
            
            for wallet_name in selected_wallets:
                try:
                    progress.update(task, description=f"[cyan]Checking {wallet_name} balance...[/cyan]")
                    
                    wallet = bt.wallet(name=wallet_name)
                    balance = float(self.transfer_manager.subtensor.get_balance(wallet.coldkeypub.ss58_address))
                    
                    if wallet.coldkeypub.ss58_address == dest_address:
                        progress.update(task, advance=1)
                        continue
                    
                    transferable = balance - reserve_amount
                    
                    if transferable <= 0:
                        progress.update(task, advance=1)
                        continue
                    
                    wallet_balances[wallet_name] = {
                        'balance': balance,
                        'to_transfer': transferable,
                        'address': wallet.coldkeypub.ss58_address
                    }
                    
                    total_to_transfer += transferable
                except Exception as e:
                    console.print(f"[red]Error checking {wallet_name} balance: {str(e)}[/red]")
                
                progress.update(task, advance=1)
        
        if not wallet_balances:
            console.print("[yellow]No wallets with transferable balance found![/yellow]")
            return
        
        table = Table(title="Collection Summary")
        table.add_column("Wallet")
        table.add_column("Address")
        table.add_column("Balance (τ)")
        table.add_column("To Transfer (τ)")
        table.add_column("Reserve (τ)")
        
        for wallet_name, data in wallet_balances.items():
            balance = data['balance']
            to_transfer = data['to_transfer']
            reserve = balance - to_transfer
            
            table.add_row(
                wallet_name,
                data['address'][:15] + "..." + data['address'][-10:],
                f"{balance:.9f}",
                f"{to_transfer:.9f}",
                f"{reserve:.9f}"
            )
        
        table.add_row(
            "[bold]Total[/bold]",
            "",
            "",
            f"[bold]{total_to_transfer:.9f}[/bold]",
            "",
            style="bold green"
        )
        
        console.print(table)
        console.print(f"\nDestination address: {dest_address}")
        console.print(f"Reserve for fees: {reserve_amount_display} TAO per wallet")
        
        if not Confirm.ask(f"Collect a total of {total_to_transfer:.9f} TAO into the destination address?"):
            return
        
        successful_transfers = 0
        failed_transfers = 0
        total_transferred = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Processing transfers...", total=len(wallet_balances))
            
            for wallet_name, data in wallet_balances.items():
                progress.update(task, description=f"[cyan]Transferring from {wallet_name}...[/cyan]")
                
                try:
                    password = common_password
                    if not use_same_password:
                        password = Prompt.ask(f"Enter password for {wallet_name}", password=True)
                        if not self.transfer_manager.verify_wallet_password(wallet_name, password):
                            console.print(f"[red]Invalid password for {wallet_name}![/red]")
                            failed_transfers += 1
                            progress.update(task, advance=1)
                            continue
                    
                    success = self.transfer_manager.transfer_tao(
                        wallet_name, 
                        dest_address, 
                        data['to_transfer'], 
                        password
                    )
                    
                    if success:
                        successful_transfers += 1
                        total_transferred += data['to_transfer']
                        console.print(f"[green]Successfully transferred {data['to_transfer']:.9f} TAO from {wallet_name}[/green]")
                    else:
                        failed_transfers += 1
                        console.print(f"[red]Failed to transfer from {wallet_name}[/red]")
                except Exception as e:
                    failed_transfers += 1
                    console.print(f"[red]Error transferring from {wallet_name}: {str(e)}[/red]")
                
                progress.update(task, advance=1)
        
        console.print("\n[bold]Collection Results:[/bold]")
        console.print(f"[green]Successful transfers: {successful_transfers}[/green]")
        if failed_transfers > 0:
            console.print(f"[red]Failed transfers: {failed_transfers}[/red]")
        console.print(f"Total TAO collected: {total_transferred:.9f}")
        
class AutoBuyerMenu:
    def __init__(self, transfer_manager, wallet_utils, config):
        self.transfer_manager = transfer_manager
        self.wallet_utils = wallet_utils
        self.config = config
        from ..core.auto_buyer import AutoBuyerManager
        self.buyer_manager = AutoBuyerManager(config)
        
    def _get_wallet_password(self, wallet: str) -> str:
        """Получение пароля с учетом дефолтного пароля из конфига"""
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

    def _get_rpc_endpoint(self) -> Optional[str]:
        default_endpoint = "wss://entrypoint-finney.opentensor.ai:443"
        rpc_endpoint = Prompt.ask(
            f"Enter RPC endpoint (press Enter for default endpoint)",
            default=default_endpoint
        ).strip()
        
        if rpc_endpoint == default_endpoint:
            rpc_endpoint = None
            
        return rpc_endpoint
            
    async def show(self):
        while True:
            console.print("\n[bold]Auto Token Buyer Menu[/bold]")
            console.print(Panel.fit(
                "1. Buy Subnet Tokens (One-time operation)\n"
                "2. Monitor Subnet and Buy when Registration Closes\n"
                "3. Monitor New Subnet (Wait for appearance) and Buy\n"
                "4. Back to Main Menu"
            ))

            choice = IntPrompt.ask("Select option", default=4)

            if choice == 4:
                return

            wallets = self.wallet_utils.get_available_wallets()
            if not wallets:
                console.print("[red]No wallets found![/red]")
                return

            if choice == 1:
                await self._handle_single_purchase(wallets)
            elif choice == 2:
                await self._handle_subnet_monitoring(wallets)
            elif choice == 3:
                await self._handle_new_subnet_monitoring(wallets)
            else:
                console.print("[red]Invalid option![/red]")
    
    async def _handle_single_purchase(self, wallets):
        console.print("\nAvailable wallets:")
        for i, wallet in enumerate(wallets, 1):
            console.print(f"{i}. {wallet}")

        selection = Prompt.ask("Select wallet (number)").strip()
        try:
            index = int(selection) - 1
            if not (0 <= index < len(wallets)):
                console.print("[red]Invalid wallet selection![/red]")
                return
            wallet_name = wallets[index]
        except ValueError:
            console.print("[red]Invalid input![/red]")
            return
            
        hotkeys = self.wallet_utils.get_wallet_hotkeys(wallet_name)
        if not hotkeys:
            console.print(f"[red]No hotkeys found for wallet {wallet_name}![/red]")
            return
            
        console.print(f"\nHotkeys for wallet {wallet_name}:")
        for i, hotkey in enumerate(hotkeys, 1):
            console.print(f"{i}. {hotkey}")
            
        hotkey_selection = Prompt.ask("Select hotkey (number)").strip()
        try:
            hotkey_index = int(hotkey_selection) - 1
            if not (0 <= hotkey_index < len(hotkeys)):
                console.print("[red]Invalid hotkey selection![/red]")
                return
            hotkey_name = hotkeys[hotkey_index]
        except ValueError:
            console.print("[red]Invalid input![/red]")
            return
            
        subnet_id = IntPrompt.ask("Enter subnet ID to buy tokens for")
        amount = Prompt.ask("Enter amount of TAO to buy", default="0.05")
        tolerance = Prompt.ask("Enter tolerance (acceptable slippage)", default="0.45")
        
        password = self._get_wallet_password(wallet_name)
        
        if not self.transfer_manager.verify_wallet_password(wallet_name, password):
            console.print("[red]Invalid password![/red]")
            return
            
        await self.buyer_manager.buy_subnet_token(
            wallet_name=wallet_name,
            hotkey_name=hotkey_name,
            subnet_id=subnet_id,
            amount=float(amount),
            password=password,
            tolerance=float(tolerance)
        )
        
    async def _handle_subnet_monitoring(self, wallets):
        console.print("\nAvailable wallets:")
        for i, wallet in enumerate(wallets, 1):
            console.print(f"{i}. {wallet}")

        selection = Prompt.ask("Select wallet (number)").strip()
        try:
            index = int(selection) - 1
            if not (0 <= index < len(wallets)):
                console.print("[red]Invalid wallet selection![/red]")
                return
            wallet_name = wallets[index]
        except ValueError:
            console.print("[red]Invalid input![/red]")
            return
            
        hotkeys = self.wallet_utils.get_wallet_hotkeys(wallet_name)
        if not hotkeys:
            console.print(f"[red]No hotkeys found for wallet {wallet_name}![/red]")
            return
            
        console.print(f"\nHotkeys for wallet {wallet_name}:")
        for i, hotkey in enumerate(hotkeys, 1):
            console.print(f"{i}. {hotkey}")
            
        hotkey_selection = Prompt.ask("Select hotkey (number)").strip()
        try:
            hotkey_index = int(hotkey_selection) - 1
            if not (0 <= hotkey_index < len(hotkeys)):
                console.print("[red]Invalid hotkey selection![/red]")
                return
            hotkey_name = hotkeys[hotkey_index]
        except ValueError:
            console.print("[red]Invalid input![/red]")
            return
            
        subnet_id = IntPrompt.ask("Enter subnet ID to monitor")
        amount = Prompt.ask("Enter amount of TAO to buy", default="0.05")
        tolerance = Prompt.ask("Enter tolerance (acceptable slippage)", default="0.45")
        check_interval = IntPrompt.ask("Check interval (seconds)", default=60)
        max_attempts = IntPrompt.ask("Maximum purchase attempts per check", default=3)
        
        password = self._get_wallet_password(wallet_name)
        
        if not self.transfer_manager.verify_wallet_password(wallet_name, password):
            console.print("[red]Invalid password![/red]")
            return
        
        console.print(f"\n[cyan]Starting monitoring for subnet {subnet_id}...[/cyan]")
        console.print(f"[yellow]Press Ctrl+C to stop monitoring at any time[/yellow]")
        
        await self.buyer_manager.monitor_subnet_and_buy(
            wallet_name=wallet_name,
            hotkey_name=hotkey_name,
            subnet_id=subnet_id,
            amount=float(amount),
            password=password,
            tolerance=float(tolerance),
            check_interval=check_interval,
            max_attempts=max_attempts
        )
        
    async def _handle_new_subnet_monitoring(self, wallets):
        console.print("\nThis mode will monitor for a new subnet and buy tokens when it appears and registration closes")
        
        console.print("\nAvailable wallets:")
        for i, wallet in enumerate(wallets, 1):
            console.print(f"{i}. {wallet}")
        
        wallet_configs = []
        
        wallet_selection = Prompt.ask("Select wallets (comma-separated numbers, e.g. 1,3,4 or 'all')").strip().lower()
        
        if wallet_selection == 'all':
            selected_wallets = wallets
        else:
            try:
                indices = [int(i.strip()) - 1 for i in wallet_selection.split(',')]
                selected_wallets = [wallets[i] for i in indices if 0 <= i < len(wallets)]
            except:
                console.print("[red]Invalid selection![/red]")
                return
        
        if not selected_wallets:
            console.print("[red]No wallets selected![/red]")
            return
        
        for wallet_name in selected_wallets:
            hotkeys = self.wallet_utils.get_wallet_hotkeys(wallet_name)
            if not hotkeys:
                console.print(f"[red]No hotkeys found for wallet {wallet_name}![/red]")
                continue
                
            console.print(f"\nHotkeys for wallet {wallet_name}:")
            for i, hotkey in enumerate(hotkeys, 1):
                console.print(f"{i}. {hotkey}")
                
            hotkey_selection = Prompt.ask("Select hotkeys (comma-separated numbers, e.g. 1,3,4 or 'all')").strip().lower()
            
            if hotkey_selection == 'all':
                selected_hotkeys = hotkeys
            else:
                try:
                    indices = [int(i.strip()) - 1 for i in hotkey_selection.split(',')]
                    selected_hotkeys = [hotkeys[i] for i in indices if 0 <= i < len(hotkeys)]
                except:
                    console.print(f"[red]Invalid hotkey selection for {wallet_name}![/red]")
                    continue
            
            if not selected_hotkeys:
                console.print(f"[red]No hotkeys selected for wallet {wallet_name}![/red]")
                continue
                
            password = self._get_wallet_password(wallet_name)
            
            if not self.transfer_manager.verify_wallet_password(wallet_name, password):
                console.print(f"[red]Invalid password for wallet {wallet_name}![/red]")
                continue
                
            for hotkey_name in selected_hotkeys:
                wallet_configs.append({
                    'coldkey': wallet_name,
                    'hotkey': hotkey_name,
                    'password': password
                })
        
        if not wallet_configs:
            console.print("[red]No valid wallet/hotkey configurations![/red]")
            return
            
        console.print(f"\n[green]Successfully configured {len(wallet_configs)} hotkeys for monitoring[/green]")
        
        rpc_endpoint = self._get_rpc_endpoint()
        
        target_subnet_id = IntPrompt.ask("Enter target subnet ID to monitor")
        amount = Prompt.ask("Enter amount of TAO to buy per hotkey", default="0.05")
        tolerance = Prompt.ask("Enter tolerance (acceptable slippage)", default="0.45")
        check_interval = IntPrompt.ask("Check interval (seconds)", default=60)
        max_attempts = IntPrompt.ask("Maximum purchase attempts per hotkey", default=3)
        auto_increase = Confirm.ask("Automatically increase tolerance on failures?", default=True)
        buy_immediately = Confirm.ask("Buy tokens immediately when subnet appears (even if registration is open)?", default=False)
        
        console.print(f"\n[cyan]Starting monitoring for new subnet {target_subnet_id}...[/cyan]")
        console.print(f"[cyan]Total wallets: {len(set(cfg['coldkey'] for cfg in wallet_configs))}, Total hotkeys: {len(wallet_configs)}[/cyan]")
        if rpc_endpoint:
            console.print(f"[cyan]Using custom RPC endpoint: {rpc_endpoint}[/cyan]")
        console.print(f"[yellow]Press Ctrl+C to stop monitoring at any time[/yellow]")
        
        await self.buyer_manager.monitor_new_subnet_and_buy(
            wallet_configs=wallet_configs,
            target_id=target_subnet_id,
            amount=float(amount),
            tolerance=float(tolerance),
            check_interval=check_interval,
            max_attempts=max_attempts,
            auto_increase_tolerance=auto_increase,
            buy_immediately=buy_immediately,
            rpc_endpoint=rpc_endpoint
        )
