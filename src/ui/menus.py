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
           "2. Auto Registration (Multiple Adjustments)\n"
           "3. Sniper Registration (DEGEN mode)\n"
           "4. Spread Registration (Multiple Hotkeys with distributed timing)\n"
           "5. Subnet Monitor Registration (Wait for open registration)\n"
           "6. Price Monitor Registration (Register when price is below target)\n"
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
        for wallet in wallets:
            console.print(f"  • {wallet}")

        console.print("\nSelect wallets (comma-separated names, e.g. bot_1,bot_2,bot_3)")
        selection = Prompt.ask("Selection").strip()

        selected_wallets = self.wallet_utils.parse_wallet_selection_by_names(selection, wallets)
        if not selected_wallets:
            console.print("[red]No valid wallets selected![/red]")
            return

        rpc_endpoint = self._get_rpc_endpoint()

        if mode == 3:
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
                for hotkey in hotkeys:
                    console.print(f"  • {hotkey}")

                console.print("\nSelect hotkeys (comma-separated names or 'all')")
                hotkey_selection = Prompt.ask("Selection").strip()

                if hotkey_selection.lower() == 'all':
                    selected_hotkeys = hotkeys
                else:
                    selected_hotkeys = [h.strip() for h in hotkey_selection.split(',') if h.strip() in hotkeys]

                if not selected_hotkeys:
                    console.print(f"[red]No valid hotkeys selected for {wallet}![/red]")
                    continue

                console.print("\n[bold]Transaction Validity Parameters[/bold]")
                use_period = Confirm.ask("Use period parameter?", default=True)
                period_value = None
                if use_period:
                    period_value = IntPrompt.ask("Enter period value (blocks transaction remains valid)", default=16)
                
                use_era = Confirm.ask("Use era parameter?", default=False)
                era_value = None
                if use_era:
                    era_value = IntPrompt.ask("Enter era value (legacy parameter)", default=1)

                for hotkey in selected_hotkeys:
                    config = {
                        'coldkey': wallet,
                        'hotkey': hotkey,
                        'password': password
                    }
                    
                    if period_value is not None:
                        config['period'] = period_value
                    if era_value is not None:
                        config['era'] = era_value
                        
                    wallet_configs.append(config)

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
                for hotkey in hotkeys:
                    console.print(f"  • {hotkey}")

                console.print("\nSelect hotkeys (comma-separated names or 'all')")
                hotkey_selection = Prompt.ask("Selection").strip()

                if hotkey_selection.lower() == 'all':
                    selected_hotkeys = hotkeys
                else:
                    selected_hotkeys = [h.strip() for h in hotkey_selection.split(',') if h.strip() in hotkeys]

                if not selected_hotkeys:
                    console.print(f"[red]No valid hotkeys selected for {wallet}![/red]")
                    continue

                console.print("\n[bold]Transaction Validity Parameters[/bold]")
                use_period = Confirm.ask("Use period parameter?", default=True)
                period_value = None
                if use_period:
                    period_value = IntPrompt.ask("Enter period value (blocks transaction remains valid)", default=16)
                
                use_era = Confirm.ask("Use era parameter?", default=False)
                era_value = None
                if use_era:
                    era_value = IntPrompt.ask("Enter era value (legacy parameter)", default=1)

                for hotkey in selected_hotkeys:
                    config = {
                        'coldkey': wallet,
                        'hotkey': hotkey,
                        'password': password,
                        'prep_time': 15
                    }
                    
                    if period_value is not None:
                        config['period'] = period_value
                    if era_value is not None:
                        config['era'] = era_value
                        
                    wallet_configs.append(config)

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
                for hotkey in hotkeys:
                    console.print(f"  • {hotkey}")

                console.print("\nSelect hotkeys (comma-separated names or 'all')")
                hotkey_selection = Prompt.ask("Selection").strip()

                if hotkey_selection.lower() == 'all':
                    selected_hotkeys = hotkeys
                else:
                    selected_hotkeys = [h.strip() for h in hotkey_selection.split(',') if h.strip() in hotkeys]
                
                if selected_hotkeys:
                    all_wallet_info[wallet] = selected_hotkeys
                else:
                    console.print(f"[red]No valid hotkeys selected for {wallet}![/red]")
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
            
            console.print("\n[bold]Transaction Validity Configuration[/bold]")
            console.print("Select options for transaction validity:")
            console.print("1. Use period only (recommended, new parameter)")
            console.print("2. Use era only (legacy parameter)")
            console.print("3. Use both period and era")
            console.print("4. Don't use any")
            tx_param_choice = IntPrompt.ask("Select option", default=1)
            
            use_period = False
            use_era = False
            min_period = None
            max_period = None
            min_era = None
            max_era = None
            
            if tx_param_choice == 1 or tx_param_choice == 3:
                use_period = True
                console.print("\n[bold]Period Distribution Range[/bold]")
                console.print("Enter the range of period values to distribute across coldkeys (number of blocks transaction is valid for)")
                min_period = IntPrompt.ask("Minimum period value (e.g. 1)", default=1)
                max_period = IntPrompt.ask("Maximum period value (e.g. 3)", default=3)
            
            if tx_param_choice == 2 or tx_param_choice == 3:
                use_era = True
                console.print("\n[bold]ERA Distribution Range[/bold]")
                console.print("Enter the range of era values to distribute across coldkeys (number of blocks transaction is valid for)")
                min_era = IntPrompt.ask("Minimum era value (e.g. 1)", default=1)
                max_era = IntPrompt.ask("Maximum era value (e.g. 3)", default=3)
            
            use_coldkey_delay = Confirm.ask("Add delay between transactions from the same coldkey?", default=True)
            coldkey_delay = 6
            if use_coldkey_delay:
                coldkey_delay = IntPrompt.ask("Delay between transactions from the same coldkey (seconds)", default=6)
            else:
                coldkey_delay = 0
            
            coldkeys_count = len(all_wallet_info)
            hotkeys_per_coldkey = [len(hotkeys) for coldkey, hotkeys in all_wallet_info.items()]
            
            console.print(f"\n[cyan]Distributing timing values across {coldkeys_count} coldkeys with {sum(hotkeys_per_coldkey)} total hotkeys...[/cyan]")
            
            timing_values, period_values, era_values = self.registration_manager.spread_timing_across_hotkeys(
                coldkeys_count,
                hotkeys_per_coldkey,
                min_timing,
                max_timing,
                coldkey_delay,
                min_period if use_period else None,
                max_period if use_period else None,
                min_era if use_era else None,
                max_era if use_era else None
            )
            
            wallet_config_dict = {}
            hotkey_attempts = {}
            
            title_parts = ["Timing"]
            if use_period:
                title_parts.append("Period")
            if use_era:
                title_parts.append("ERA")
            table_title = " and ".join(title_parts) + " Distribution"
            
            table = Table(title=table_title)
            table.add_column("Wallet")
            table.add_column("Hotkey")
            table.add_column("Timing")
            if use_period:
                table.add_column("Period")
            if use_era:
                table.add_column("ERA")
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
                    
                    transaction_data = [wallet, hotkey, timing]
                    
                    if use_period:
                        period_val = period_values[idx][hotkey_idx]
                        cfg['period'] = period_val
                        transaction_data.append(period_val)
                    
                    if use_era:
                        era_val = era_values[idx][hotkey_idx]
                        cfg['era'] = era_val
                        transaction_data.append(era_val)
                    
                    wallet_transactions.append(cfg)
                    all_transaction_timings.append(tuple(transaction_data))
                    
                    key = f"{wallet}:{hotkey}"
                    hotkey_attempts[key] = attempts_per_hotkey
                
                wallet_transactions.sort(key=lambda x: x['prep_time'])
                wallet_configs.extend(wallet_transactions)
                
                config_dict_entry = {
                    'hotkeys': hotkeys,
                    'password': wallet_passwords[wallet],
                    'prep_time': coldkey_timings[0] if coldkey_timings else 0,
                    'current_hotkey_index': 0,
                    'current_attempt': 0,
                    'max_attempts': attempts_per_hotkey
                }
                
                if use_period:
                    config_dict_entry['period'] = period_values[idx][0] if idx in period_values else min_period
                if use_era:
                    config_dict_entry['era'] = era_values[idx][0] if idx in era_values else min_era
                    
                wallet_config_dict[wallet] = config_dict_entry
            
            all_transaction_timings.sort(key=lambda x: x[2])
            
            for order, transaction_data in enumerate(all_transaction_timings, 1):
                row_data = list(transaction_data)
                row_data.append(str(order))
                table.add_row(*[str(item) if not isinstance(item, float) and not isinstance(item, int) else 
                            (f"{item}s" if i == 2 else str(item)) for i, item in enumerate(row_data)])
            
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
                    
        elif mode == 4:
            all_wallet_info = {}
            wallet_passwords = {}
            
            sample_wallet = selected_wallets[0] if selected_wallets else None
            if not sample_wallet:
                console.print("[red]No valid wallet selected![/red]")
                return
                    
            hotkeys = self.wallet_utils.get_wallet_hotkeys(sample_wallet)
            if not hotkeys:
                console.print(f"[red]No hotkeys found for sample wallet {sample_wallet}![/red]")
                return

            default_password = self.config.get('wallet.default_password')
            common_password = None
            if default_password:
                common_password = Prompt.ask(
                    f"Enter password for all wallets (press Enter to use default: {default_password})", 
                    password=True,
                    show_default=False
                )
                common_password = common_password if common_password else default_password
            else:
                common_password = Prompt.ask("Enter password for all wallets", password=True)
                
            invalid_wallets = []
            for wallet in selected_wallets:
                if not self.registration_manager.verify_wallet_password(wallet, common_password):
                    invalid_wallets.append(wallet)
            
            if invalid_wallets:
                console.print(f"[red]Password is invalid for wallets: {', '.join(invalid_wallets)}[/red]")
                return
            
            console.print(f"\nHotkeys found for wallet {sample_wallet}:")
            for i, hotkey in enumerate(hotkeys, 1):
                console.print(f"{i}. {hotkey}")

            console.print("\nSelect hotkeys to use for ALL wallets (comma-separated numbers, e.g. 1,3,5)")
            hotkey_selection = Prompt.ask("Selection").strip()

            try:
                hotkey_indices = [int(i.strip()) - 1 for i in hotkey_selection.split(',')]
                
                if not hotkey_indices:
                    console.print("[red]No valid hotkey selection![/red]")
                    return
                    
            except:
                console.print(f"[red]Invalid hotkey selection![/red]")
                return
                
            for wallet in selected_wallets:
                wallet_passwords[wallet] = common_password
                
                wallet_hotkeys = self.wallet_utils.get_wallet_hotkeys(wallet)
                if not wallet_hotkeys:
                    console.print(f"[yellow]No hotkeys found for wallet {wallet}, skipping...[/yellow]")
                    continue
                    
                selected_hotkeys = []
                for idx in hotkey_indices:
                    if idx < len(wallet_hotkeys):
                        selected_hotkeys.append(wallet_hotkeys[idx])
                    else:
                        console.print(f"[yellow]Warning: Wallet {wallet} doesn't have hotkey at index {idx+1}, skipping this hotkey[/yellow]")
                
                if selected_hotkeys:
                    all_wallet_info[wallet] = selected_hotkeys
            
            if not all_wallet_info:
                console.print("[red]No valid wallet/hotkey combinations selected![/red]")
                return
                
            console.print(f"\n[cyan]Successfully processed {len(all_wallet_info)} wallets with a total of {sum(len(hotkeys) for hotkeys in all_wallet_info.values())} hotkeys[/cyan]")
                
            console.print("\n[bold]Timing Distribution Range[/bold]")
            console.print("Enter the range of timing values to distribute across coldkeys")
            min_timing = IntPrompt.ask("Minimum timing value (e.g. -20)", default=-20)
            max_timing = IntPrompt.ask("Maximum timing value (e.g. 0)", default=0)
            
            console.print("\n[bold]Transaction Validity Configuration[/bold]")
            console.print("Select options for transaction validity:")
            console.print("1. Use period only (recommended, new parameter)")
            console.print("2. Use era only (legacy parameter)")
            console.print("3. Use both period and era")
            console.print("4. Don't use any")
            tx_param_choice = IntPrompt.ask("Select option", default=1)
            
            use_period = False
            use_era = False
            min_period = None
            max_period = None
            min_era = None
            max_era = None
            
            if tx_param_choice == 1 or tx_param_choice == 3:
                use_period = True
                console.print("\n[bold]Period Distribution Range[/bold]")
                console.print("Enter the range of period values to distribute across coldkeys (number of blocks transaction is valid for)")
                min_period = IntPrompt.ask("Minimum period value (e.g. 1)", default=1)
                max_period = IntPrompt.ask("Maximum period value (e.g. 3)", default=3)
            
            if tx_param_choice == 2 or tx_param_choice == 3:
                use_era = True
                console.print("\n[bold]ERA Distribution Range[/bold]")
                console.print("Enter the range of era values to distribute across coldkeys (number of blocks transaction is valid for)")
                min_era = IntPrompt.ask("Minimum era value (e.g. 1)", default=1)
                max_era = IntPrompt.ask("Maximum era value (e.g. 3)", default=3)
            
            use_coldkey_delay = Confirm.ask("Add delay between transactions from the same coldkey?", default=True)
            coldkey_delay = 6
            if use_coldkey_delay:
                coldkey_delay = IntPrompt.ask("Delay between transactions from the same coldkey (seconds)", default=6)
            else:
                coldkey_delay = 0
            
            coldkeys_count = len(all_wallet_info)
            hotkeys_per_coldkey = [len(hotkeys) for coldkey, hotkeys in all_wallet_info.items()]
            
            console.print(f"\n[cyan]Distributing timing values across {coldkeys_count} coldkeys with {sum(hotkeys_per_coldkey)} total hotkeys...[/cyan]")
            
            timing_values, period_values, era_values = self.registration_manager.spread_timing_across_hotkeys(
                coldkeys_count,
                hotkeys_per_coldkey,
                min_timing,
                max_timing,
                coldkey_delay,
                min_period if use_period else None,
                max_period if use_period else None,
                min_era if use_era else None,
                max_era if use_era else None
            )
            
            wallet_configs = []
            
            title_parts = ["Timing"]
            if use_period:
                title_parts.append("Period")
            if use_era:
                title_parts.append("ERA")
            table_title = " and ".join(title_parts) + " Distribution"
            
            table = Table(title=table_title)
            table.add_column("Wallet")
            table.add_column("Hotkey")
            table.add_column("Timing")
            if use_period:
                table.add_column("Period")
            if use_era:
                table.add_column("ERA")
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
                    
                    transaction_data = [wallet, hotkey, timing]
                    
                    if use_period:
                        period_val = period_values[idx][hotkey_idx]
                        cfg['period'] = period_val
                        transaction_data.append(period_val)
                    
                    if use_era:
                        era_val = era_values[idx][hotkey_idx]
                        cfg['era'] = era_val
                        transaction_data.append(era_val)
                    
                    wallet_transactions.append(cfg)
                    all_transaction_timings.append(tuple(transaction_data))
                
                wallet_transactions.sort(key=lambda x: x['prep_time'])
                wallet_configs.extend(wallet_transactions)
            
            all_transaction_timings.sort(key=lambda x: x[2])
            
            for order, transaction_data in enumerate(all_transaction_timings, 1):
                row_data = list(transaction_data)
                row_data.append(str(order))
                table.add_row(*[str(item) if not isinstance(item, float) and not isinstance(item, int) else 
                            (f"{item}s" if i == 2 else str(item)) for i, item in enumerate(row_data)])
            
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
                    
                    if use_period:
                        manual_config_table.add_column("Period Range")
                    if use_era:
                        manual_config_table.add_column("ERA Range")
                    
                    row_values = [
                        str(subnet_id),
                        str(target_block),
                        str(len(all_wallet_info)),
                        str(sum(hotkeys_per_coldkey)),
                        f"{min_timing}s to {max_timing}s"
                    ]
                    
                    if use_period:
                        row_values.append(f"{min_period} to {max_period}")
                    if use_era:
                        row_values.append(f"{min_era} to {max_era}")
                    
                    manual_config_table.add_row(*row_values)
                    
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
                    
        elif mode == 5:
            
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
                for hotkey in hotkeys:
                    console.print(f"  • {hotkey}")

                console.print("\nSelect hotkeys (comma-separated names or 'all')")
                hotkey_selection = Prompt.ask("Selection").strip()

                if hotkey_selection.lower() == 'all':
                    selected_hotkeys = hotkeys
                else:
                    selected_hotkeys = [h.strip() for h in hotkey_selection.split(',') if h.strip() in hotkeys]

                if not selected_hotkeys:
                    console.print(f"[red]No valid hotkeys selected for {wallet}![/red]")
                    continue

                console.print("\n[bold]Transaction Validity Parameters[/bold]")
                use_period = Confirm.ask("Use period parameter?", default=True)
                period_value = None
                if use_period:
                    period_value = IntPrompt.ask("Enter period value (blocks transaction remains valid)", default=16)
                
                use_era = Confirm.ask("Use era parameter?", default=False)
                era_value = None
                if use_era:
                    era_value = IntPrompt.ask("Enter era value (legacy parameter)", default=1)

                for hotkey in selected_hotkeys:
                    config = {
                        'coldkey': wallet,
                        'hotkey': hotkey,
                        'password': password,
                        'prep_time': -4
                    }
                    
                    if period_value is not None:
                        config['period'] = period_value
                    if era_value is not None:
                        config['era'] = era_value
                        
                    wallet_configs.append(config)
            
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

        elif mode == 6:
            self._handle_price_monitor_registration(selected_wallets, rpc_endpoint, subnet_id)
            return


    def _handle_price_monitor_registration(self, selected_wallets, rpc_endpoint, subnet_id=None):
        console.print("\n[bold yellow]Price monitor mode supports only one coldkey.[/bold yellow]")
        
        if len(selected_wallets) > 1:
            console.print("\nAvailable Wallets:")
            for wallet in selected_wallets:
                console.print(f"  • {wallet}")
            
            wallet_selection = Prompt.ask("Select one wallet (enter wallet name)").strip()
            
            if wallet_selection not in selected_wallets:
                console.print("[red]Invalid wallet name![/red]")
                return
            
            selected_wallet = wallet_selection
        else:
            selected_wallet = selected_wallets[0]
            console.print(f"\nUsing wallet: {selected_wallet}")
        
        password = self._get_wallet_password(selected_wallet)
        if not self.registration_manager.verify_wallet_password(selected_wallet, password):
            console.print(f"[red]Invalid password for {selected_wallet}[/red]")
            return
        
        if subnet_id is None:
            subnet_id = IntPrompt.ask("Enter subnet ID for registration", default=1)
        
        hotkeys = self.wallet_utils.get_wallet_hotkeys(selected_wallet)
        if not hotkeys:
            console.print(f"[red]No hotkeys found for wallet {selected_wallet}![/red]")
            return
        
        console.print(f"\nHotkeys for wallet {selected_wallet}:")
        for i, hotkey in enumerate(hotkeys, 1):
            console.print(f"{i}. {hotkey}")
        
        console.print("\nSelect hotkeys (comma-separated numbers, e.g. 1,2,3,4)")
        hotkey_selection = Prompt.ask("Selection").strip()
        
        try:
            hotkey_indices = [int(i.strip()) - 1 for i in hotkey_selection.split(',')]
            selected_hotkeys = [hotkeys[i] for i in hotkey_indices if 0 <= i < len(hotkeys)]
        except:
            console.print(f"[red]Invalid hotkey selection![/red]")
            return
                
        if not selected_hotkeys:
            console.print("[red]No valid hotkeys selected![/red]")
            return
        
        console.print("\n[bold]Transaction Validity Parameters[/bold]")
        use_period = Confirm.ask("Use period parameter?", default=True)
        period_value = None
        if use_period:
            period_value = IntPrompt.ask("Enter period value (blocks transaction remains valid)", default=16)
        
        use_era = Confirm.ask("Use era parameter?", default=False)
        era_value = None
        if use_era:
            era_value = IntPrompt.ask("Enter era value (legacy parameter)", default=1)
        
        wallet_configs = []
        for hotkey in selected_hotkeys:
            config = {
                'coldkey': selected_wallet,
                'hotkey': hotkey,
                'password': password
            }
            
            if period_value is not None:
                config['period'] = period_value
            if era_value is not None:
                config['era'] = era_value
                
            wallet_configs.append(config)
        
        target_price = float(Prompt.ask("Enter target price threshold in TAO (e.g. 0.04)", default="0.04"))
        check_interval = IntPrompt.ask("Enter check interval in seconds", default=5)
        
        use_offset = Confirm.ask("Add +1 block to adjustment block when waiting?", default=False)
        adjustment_block_offset = 1 if use_offset else 0
        
        try:
            self.registration_manager.start_price_monitor_registration(
                wallet_configs=wallet_configs,
                subnet_id=subnet_id,
                target_price=target_price,
                check_interval=check_interval,
                rpc_endpoint=rpc_endpoint,
                adjustment_block_offset=adjustment_block_offset
            )
        except Exception as e:
            console.print(f"[red]Error in price monitor: {str(e)}[/red]")
            
class WalletCreationMenu:
    def __init__(self, wallet_manager, config):
        self.wallet_manager = wallet_manager
        self.config = config
        self.wallet_utils = WalletUtils()

    def show(self):
        while True:
            console.print("\n[bold]Create Wallet Menu[/bold]")
            console.print(Panel.fit(
                "1. Create new coldkey with hotkeys\n"
                "2. Add hotkeys to existing coldkey\n"
                "3. Batch add hotkeys to multiple coldkeys\n"
                "4. Back to Main Menu"
            ))

            choice = IntPrompt.ask("Select option", default=4)

            if choice == 4:
                return

            if choice == 1:
                self._handle_create_new_coldkey()
            elif choice == 2:
                self._handle_add_hotkeys_single()
            elif choice == 3:
                self._handle_batch_add_hotkeys()

    def _handle_create_new_coldkey(self):
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

    def _handle_add_hotkeys_single(self):
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

    def _handle_batch_add_hotkeys(self):
        wallets = self.wallet_utils.get_available_wallets()
        
        if not wallets:
            console.print("[red]No wallets found![/red]")
            return

        console.print("\n[bold]Available Wallets:[/bold]")
        for wallet in wallets:
            console.print(f"  • {wallet}")

        console.print("\nSelect wallets (comma-separated names, e.g. bot_1,bot_2,bot_3 or 'all')")
        selection = Prompt.ask("Selection").strip()

        selected_wallets = self.wallet_utils.parse_wallet_selection_by_names(selection, wallets)
        if not selected_wallets:
            console.print("[red]No valid wallets selected![/red]")
            return

        if not selected_wallets:
            console.print("[red]No wallets selected![/red]")
            return

        num_hotkeys = IntPrompt.ask("Enter number of hotkeys to add to each wallet", default=1)

        # Prepare wallet configs
        wallet_configs = []
        for wallet_name in selected_wallets:
            wallet_configs.append({'name': wallet_name})

        console.print(f"\n[cyan]Will add {num_hotkeys} hotkeys to {len(selected_wallets)} wallets[/cyan]")
        
        if not Confirm.ask("Proceed?"):
            return

        # Execute batch addition
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(
                f"[cyan]Adding hotkeys to wallets...", 
                total=len(selected_wallets)
            )

            results = self.wallet_manager.batch_add_hotkeys(wallet_configs, num_hotkeys)
            
            for wallet_name in selected_wallets:
                progress.update(task, advance=1)

        # Display results
        console.print("\n[bold]Batch Operation Results:[/bold]")
        
        success_count = sum(1 for r in results.values() if r.get('success'))
        fail_count = len(results) - success_count
        
        table = Table(title="Results Summary")
        table.add_column("Wallet")
        table.add_column("Status")
        table.add_column("Hotkeys Added")
        table.add_column("Details")
        
        for wallet_name, result in results.items():
            if result.get('success'):
                table.add_row(
                    wallet_name,
                    "[green]Success[/green]",
                    str(result.get('count', 0)),
                    f"Created hotkeys: {', '.join([h['name'] for h in result.get('hotkeys', [])])}"
                )
            else:
                table.add_row(
                    wallet_name,
                    "[red]Failed[/red]",
                    "0",
                    result.get('error', 'Unknown error')
                )
        
        console.print(table)
        console.print(f"\n[bold]Total: {success_count} successful, {fail_count} failed[/bold]")

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
        daily_rewards = sum(sum(n.get('daily_rewards_usd', 0) for n in subnet['neurons']) for subnet in stats['subnets'])
        console.print(f"Total daily reward: ${daily_rewards:.2f}")
        console.print(f"Total Alpha in $: ${total_alpha_usd:.2f}")

        subnet_netuids = [subnet['netuid'] for subnet in stats['subnets']]
        console.print(f"[dim]Displaying {len(stats['subnets'])} subnets: {subnet_netuids}[/dim]")

        for subnet in stats['subnets']:
            subnet['neurons'].sort(key=lambda x: x['stake'], reverse=True)
            
            has_unregistered = any(not n.get('is_registered', True) for n in subnet['neurons'])
            
            subnet_name = ""
            if 'name' in subnet and subnet['name']:
                subnet_name = f" ({subnet['name']})"
                if subnet['name'].startswith("Subnet ") and str(subnet['netuid']) in subnet['name']:
                    subnet_name = ""
            
            if has_unregistered:
                table = Table(title=f"Subnet {subnet['netuid']}{subnet_name} (Rate: ${subnet['rate_usd']:.4f})")
                table.add_column("Hotkey")
                table.add_column("Status")
                table.add_column("UID")
                table.add_column("Alpha Stake", justify="right")
                table.add_column("Rank", justify="right")
                table.add_column("Trust", justify="right")
                table.add_column("Consensus", justify="right")
                table.add_column("Incentive", justify="right")
                if not all(not n.get('is_registered', True) for n in subnet['neurons']):
                    table.add_column("Emission(ρ)", justify="right") 
                    table.add_column("Daily Alpha τ", justify="right")
                    table.add_column("Daily USD", justify="right")
                
                for neuron in subnet['neurons']:
                    is_registered = neuron.get('is_registered', True)
                    status = "[green]Registered[/green]" if is_registered else "[yellow]Unregistered[/yellow]"
                    
                    if is_registered:
                        table.add_row(
                            neuron['hotkey'],
                            status,
                            str(neuron['uid']),
                            f"{neuron['stake']:.9f}",
                            f"{neuron['rank']:.4f}",
                            f"{neuron['trust']:.4f}",
                            f"{neuron['consensus']:.4f}",
                            f"{neuron['incentive']:.4f}",
                            f"{neuron['emission']}",
                            f"{neuron['daily_rewards_alpha']:.9f}",
                            f"${neuron['daily_rewards_usd']:.2f}"
                        )
                    else:
                        if all(not n.get('is_registered', True) for n in subnet['neurons']):
                            table.add_row(
                                neuron['hotkey'],
                                status,
                                str(neuron.get('uid', 'N/A')),
                                f"{neuron['stake']:.9f}",
                                f"{neuron.get('rank', 0):.4f}",
                                f"{neuron.get('trust', 0):.4f}",
                                f"{neuron.get('consensus', 0):.4f}",
                                f"{neuron.get('incentive', 0):.4f}"
                            )
                        else:
                            table.add_row(
                                neuron['hotkey'],
                                status,
                                str(neuron.get('uid', 'N/A')),
                                f"{neuron['stake']:.9f}",
                                f"{neuron.get('rank', 0):.4f}",
                                f"{neuron.get('trust', 0):.4f}",
                                f"{neuron.get('consensus', 0):.4f}",
                                f"{neuron.get('incentive', 0):.4f}",
                                "0",
                                "0.000000000",
                                "$0.00"
                            )
            else:
                table = Table(title=f"Subnet {subnet['netuid']}{subnet_name} (Rate: ${subnet['rate_usd']:.4f})")
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
            for wallet in wallets:
                console.print(f"  • {wallet}")

            console.print("\nSelect wallets (comma-separated names, e.g. bot_1,bot_2,bot_3 or 'all')")
            selection = Prompt.ask("Selection").strip()

            # Используем новый метод
            selected_wallets = self.wallet_utils.parse_wallet_selection_by_names(selection, wallets)
            if not selected_wallets:
                console.print("[red]No valid wallets selected![/red]")
                return
                
            include_unregistered = Confirm.ask("Include wallets with Alpha stake that aren't registered as neurons?", default=True)

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
            unregistered_neurons = 0
            all_wallet_stats = []

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True
            ) as progress:
                task = progress.add_task("[cyan]Processing wallets...", total=len(selected_wallets))
                
                for wallet_index, wallet in enumerate(selected_wallets):
                    progress.update(task, description=f"[cyan]Processing wallet {wallet} ({wallet_index+1}/{len(selected_wallets)})...[/cyan]")
                    
                    try:
                        progress.update(task, description=f"[cyan]Finding active subnets for {wallet}...[/cyan]")
                        
                        if subnet_list is None:
                            active_subnets_list = self.stats_manager.get_active_subnets_direct(wallet)
                        else:
                            active_subnets_list = subnet_list
                        
                        progress.update(task, description=f"[cyan]Getting data for {wallet} ({len(active_subnets_list)} subnets)...[/cyan]")
                        
                        if include_unregistered and (not active_subnets_list or subnet_choice == 1):
                            unregistered_subnets = self.stats_manager.get_all_unregistered_stake_subnets(wallet)
                            if unregistered_subnets:
                                unregistered_subnets_int = [int(netuid) if isinstance(netuid, str) else netuid for netuid in unregistered_subnets]
                                new_subnets = [s for s in unregistered_subnets_int if s not in active_subnets_list]
                                if new_subnets:
                                    active_subnets_list.extend(new_subnets)
                                    console.print(f"[cyan]Found {len(new_subnets)} additional subnets with unregistered stake for {wallet}: {new_subnets}[/cyan]")
                                else:
                                    console.print(f"[cyan]All unregistered stakes are in already detected subnets[/cyan]")
                        
                        stats = await self.stats_manager.get_wallet_stats(wallet, active_subnets_list, hide_zeros, include_unregistered)
                        
                        if stats:
                            console.print(f"[green]Completed data collection for {wallet}[/green]")
                            self._display_wallet_stats(stats)
                            
                            total_balance += stats['balance']
                            
                            wallet_daily_reward = sum(sum(n.get('daily_rewards_usd', 0) for n in subnet['neurons']) 
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
                                            if neuron.get('is_registered', True):
                                                active_neurons += 1
                                            else:
                                                unregistered_neurons += 1
                            
                            total_alpha_usd_value += wallet_alpha_usd
                            all_wallet_stats.append(stats)
                        else:
                            console.print(f"[yellow]No stats found for wallet {wallet}[/yellow]")
                    except Exception as e:
                        console.print(f"[red]Error getting stats for {wallet}: {str(e)}[/red]")
                    
                    progress.update(task, advance=1)
            
            if all_wallet_stats:
                self.display_wallets_summary(
                    total_balance, 
                    total_daily_reward_usd, 
                    total_alpha_usd_value,
                    len(active_wallets),
                    len(selected_wallets),
                    len(active_subnets),
                    active_neurons,
                    unregistered_neurons
                )

    def display_wallets_summary(self, total_balance: float, total_daily_reward_usd: float, 
                             total_alpha_usd_value: float, active_wallets_count: int = 0, 
                             total_wallets_count: int = 0, active_subnets_count: int = 0,
                             active_neurons_count: int = 0, unregistered_neurons_count: int = 0):
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
            
        if unregistered_neurons_count > 0:
            table.add_row("Unregistered Neurons with Stake", str(unregistered_neurons_count))
        
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
        import subprocess
        import re
        import os
        import time
        import json
        self.subprocess = subprocess
        self.re = re
        self.os = os
        self.time = time
        self.json = json

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
            for wallet in wallets:
                console.print(f"  • {wallet}")

            console.print("\nSelect wallets (comma-separated names, e.g. bot_1,bot_2,bot_3 or 'all')")
            selection = Prompt.ask("Selection").strip()

            selected_wallets = self.wallet_utils.parse_wallet_selection_by_names(selection, wallets)
            if not selected_wallets:
                console.print("[red]No valid wallets selected![/red]")
                continue

            table = Table(title="TAO Balances", show_header=True, header_style="bold")
            table.add_column("Wallet")
            table.add_column("Address", width=50)
            table.add_column("Free Balance (τ)")
            table.add_column("Staked Value (τ)")
            table.add_column("Total Balance (τ)")

            total_free_balance = 0.0
            total_staked_balance = 0.0
            total_balance = 0.0

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True
            ) as progress:
                task = progress.add_task("[cyan]Checking balances...", total=len(selected_wallets))

                for wallet_index, wallet_name in enumerate(selected_wallets):
                    try:
                        progress.update(task, description=f"[cyan]Checking {wallet_name} ({wallet_index+1}/{len(selected_wallets)})...[/cyan]")
                        
                        detailed_balance = self._get_wallet_balance(wallet_name)
                        
                        if detailed_balance:
                            free_balance = detailed_balance.get('free_balance', 0.0)
                            staked_value = detailed_balance.get('staked_value', 0.0)
                            total_wallet_balance = detailed_balance.get('total_balance', 0.0)
                            address = detailed_balance.get('address', 'N/A')
                            
                            total_free_balance += free_balance
                            total_staked_balance += staked_value
                            total_balance += total_wallet_balance
                            
                            table.add_row(
                                wallet_name,
                                address,
                                f"{free_balance:.6f}",
                                f"{staked_value:.6f}",
                                f"{total_wallet_balance:.6f}"
                            )
                        else:
                            wallet = bt.wallet(name=wallet_name)
                            free_balance = float(self.stats_manager.subtensor.get_balance(
                                wallet.coldkeypub.ss58_address
                            ))
                            
                            total_free_balance += free_balance
                            total_balance += free_balance
                            
                            table.add_row(
                                wallet_name,
                                wallet.coldkeypub.ss58_address,
                                f"{free_balance:.6f}",
                                "0.000000",
                                f"{free_balance:.6f}"
                            )
                        
                        if wallet_index < len(selected_wallets) - 1:
                            self.time.sleep(0.1)
                            
                    except Exception as e:
                        console.print(f"[yellow]Error processing {wallet_name}: {str(e)}[/yellow]")
                        table.add_row(
                            wallet_name,
                            "[red]Error getting address[/red]",
                            "[red]Error[/red]",
                            "[red]Error[/red]",
                            f"[red]Error: {str(e)}[/red]"
                        )
                    progress.update(task, advance=1)

            table.add_row(
                "[bold]Total[/bold]",
                "",
                f"[bold]{total_free_balance:.6f}[/bold]",
                f"[bold]{total_staked_balance:.6f}[/bold]",
                f"[bold]{total_balance:.6f}[/bold]",
                style="bold green"
            )

            console.print("\n")
            console.print(table)

            if not Confirm.ask("Check another balance?"):
                return
    
    def _get_wallet_balance(self, wallet_name: str) -> dict:
        try:
            cmd = f'btcli wallet balance --wallet.name {wallet_name} --json-output'
            process = self.subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if process.returncode == 0 and process.stdout.strip():
                try:
                    data = self.json.loads(process.stdout)
                    if 'balances' in data and wallet_name in data['balances']:
                        wallet_data = data['balances'][wallet_name]
                        return {
                            'address': wallet_data.get('coldkey', 'N/A'),
                            'free_balance': float(wallet_data.get('free', 0.0)),
                            'staked_value': float(wallet_data.get('staked', 0.0)),
                            'total_balance': float(wallet_data.get('total', 0.0))
                        }
                except self.json.JSONDecodeError:
                    console.print(f"[yellow]Failed to parse JSON output for {wallet_name}[/yellow]")
            
            wallet = bt.wallet(name=wallet_name)
            address = wallet.coldkeypub.ss58_address
            
            free_balance = float(self.stats_manager.subtensor.get_balance(address))
            
            try:
                staked_value = 0.0
                cmd = f'btcli stake list --wallet.name {wallet_name} --json-output'
                process = self.subprocess.run(cmd, shell=True, capture_output=True, text=True)
                
                if process.returncode == 0 and process.stdout:
                    try:
                        data = self.json.loads(process.stdout)
                        if 'total_tao_value' in data:
                            staked_value = float(data['total_tao_value'])
                    except self.json.JSONDecodeError:
                        console.print(f"[yellow]Failed to parse staking JSON output for {wallet_name}[/yellow]")
                
                total_balance = free_balance + staked_value
                
                return {
                    'address': address,
                    'free_balance': free_balance,
                    'staked_value': staked_value,
                    'total_balance': total_balance
                }
            except Exception as e:
                console.print(f"[yellow]Error getting staked value: {str(e)}[/yellow]")
                return {
                    'address': address,
                    'free_balance': free_balance,
                    'staked_value': 0.0,
                    'total_balance': free_balance
                }
            
        except Exception as e:
            console.print(f"[yellow]Warning: Could not get detailed balance for {wallet_name}: {str(e)}[/yellow]")
            
            try:
                wallet = bt.wallet(name=wallet_name)
                address = wallet.coldkeypub.ss58_address
                
                free_balance = float(self.stats_manager.subtensor.get_balance(address))
                
                return {
                    'address': address,
                    'free_balance': free_balance,
                    'staked_value': 0.0,
                    'total_balance': free_balance
                }
            except Exception as inner_e:
                console.print(f"[yellow]Error getting basic balance: {str(inner_e)}[/yellow]")
                return None

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
            "4. Unstake Alpha TAO (Simple)\n"
            "5. Unstake Alpha TAO (Advanced)\n"
            "6. Back to Main Menu"
        ))

        choice = IntPrompt.ask("Select option", default=6)

        if choice == 6:
            return

        if choice == 1:
            self._handle_transfer()
        elif choice == 2:
            self._handle_batch_transfer()
        elif choice == 3:
            self._handle_collect_tao()
        elif choice == 4:
            self._handle_unstake_alpha_simple()
        elif choice == 5:
            self._handle_unstake_alpha()

    def _handle_transfer(self):
        wallets = self.wallet_utils.get_available_wallets()
        if not wallets:
            console.print("[red]No wallets found![/red]")
            return

        console.print("\nAvailable Wallets:")
        for wallet in wallets:
            console.print(f"  • {wallet}")

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
        import subprocess
        import time
        
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
        for wallet in wallets:
            console.print(f"  • {wallet}")

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

            default_tolerance = 0.90
            tolerance = Prompt.ask(
                f"Enter tolerance value (default: {default_tolerance})",
                default=str(default_tolerance)
            )
            tolerance = float(tolerance)

            auto_unstake = True
            
            retry_failed = Confirm.ask("Retry failed unstaking operations?", default=True)
            max_retries = 0
            if retry_failed:
                max_retries = IntPrompt.ask("Maximum number of retries per hotkey", default=3)

        stake_summary = {}

        for wallet in selected_wallets:
            try:
                console.print(f"\n[bold]Getting stake information for {wallet}...[/bold]")
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
                                'uid': hotkey_info['uid'],
                                'is_registered': hotkey_info.get('is_registered', True)
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
                    
                    sorted_hotkeys = sorted(
                        subnet_info['hotkeys'], 
                        key=lambda x: (not x.get('is_registered', True), -x['stake'])
                    )
                    
                    for hotkey_info in sorted_hotkeys:
                        if hotkey_info['stake'] > 0:
                            hotkey = hotkey_info['name']
                            stake_amount = hotkey_info['stake']
                            is_registered = hotkey_info.get('is_registered', True)
                            
                            safe_amount = stake_amount * 0.99
                            status_type = "registered" if is_registered else "unregistered"
                            
                            if auto_unstake:
                                success = False
                                retry_count = 0
                                result = {"success": False, "error": "No attempt made"}
                                
                                while not success and retry_count <= max_retries:
                                    try:
                                        current_tolerance = min(tolerance + (retry_count * 0.02), 0.99)
                                        
                                        if retry_count > 0:
                                            console.print(f"[cyan]Retry attempt {retry_count} with tolerance {current_tolerance:.2f}...[/cyan]")
                                        
                                        result = self.transfer_manager.unstake_alpha(
                                            wallet,
                                            hotkey,
                                            netuid,
                                            safe_amount,
                                            password,
                                            tolerance=current_tolerance
                                        )
                                        
                                        success = result.get('success', False)
                                        if success:
                                            break
                                    except Exception as e:
                                        console.print(f"[red]Error unstaking from {hotkey}: {str(e)}[/red]")
                                        result = {"success": False, "error": str(e)}
                                    
                                    retry_count += 1
                                    if not success and retry_count <= max_retries:
                                        time.sleep(0.5)
                                
                                if success:
                                    stake_summary[wallet][netuid]['after'][hotkey] = {
                                        'success': True,
                                        'unstaked_amount': result.get('unstaked_amount', safe_amount),
                                        'method': result.get('method', 'standard')
                                    }
                                else:
                                    error_msg = result.get('error', 'Unknown error')
                                    console.print(f"[red]Failed to unstake from {hotkey}: {error_msg}[/red]")
                                    stake_summary[wallet][netuid]['after'][hotkey] = {
                                        'success': False,
                                        'error': error_msg
                                    }
                            else:
                                if Confirm.ask(
                                    f"Unstake {safe_amount:.6f} Alpha TAO from hotkey {hotkey} in subnet {netuid} ({status_type})?"
                                ):
                                    current_tolerance = tolerance
                                    if Confirm.ask("Use maximum tolerance for this unstake?", default=True):
                                        current_tolerance = 0.99
                                    
                                    try:
                                        result = self.transfer_manager.unstake_alpha(
                                            wallet,
                                            hotkey,
                                            netuid,
                                            safe_amount,
                                            password,
                                            tolerance=current_tolerance
                                        )
                                        
                                        if result.get('success', False):
                                            stake_summary[wallet][netuid]['after'][hotkey] = {
                                                'success': True,
                                                'unstaked_amount': result.get('unstaked_amount', safe_amount),
                                                'method': result.get('method', 'standard')
                                            }
                                        else:
                                            error_msg = result.get('error', 'Unknown error')
                                            console.print(f"[red]Failed to unstake from {hotkey}: {error_msg}[/red]")
                                            stake_summary[wallet][netuid]['after'][hotkey] = {
                                                'success': False,
                                                'error': error_msg
                                            }
                                    except Exception as e:
                                        console.print(f"[red]Error unstaking from {hotkey}: {str(e)}[/red]")
                                        stake_summary[wallet][netuid]['after'][hotkey] = {
                                            'success': False,
                                            'error': str(e)
                                        }
                                else:
                                    stake_summary[wallet][netuid]['after'][hotkey] = {
                                        'success': None,
                                        'skipped': True
                                    }

            except Exception as e:
                console.print(f"[red]Error processing wallet {wallet}: {str(e)}[/red]")
        
        self._display_unstaking_summary(stake_summary)
        
        problem_hotkeys = []
        for wallet_name, wallet_data in stake_summary.items():
            for netuid, subnet_data in wallet_data.items():
                for hotkey, hotkey_data in subnet_data.get('after', {}).items():
                    if not hotkey_data.get('success', False) and not hotkey_data.get('skipped', False):
                        problem_hotkeys.append({
                            'wallet': wallet_name,
                            'hotkey': hotkey,
                            'netuid': netuid,
                            'stake': subnet_data.get('before', {}).get(hotkey, {}).get('stake', 0),
                            'orig_stake': subnet_data.get('before', {}).get(hotkey, {}).get('stake', 0)
                        })
        
        if problem_hotkeys:
            console.print("\n[yellow]The following hotkeys still have significant stake:[/yellow]")
            problem_table = Table(title="Problematic Hotkeys")
            problem_table.add_column("Wallet")
            problem_table.add_column("Hotkey")
            problem_table.add_column("Subnet")
            problem_table.add_column("Remaining Stake")
            problem_table.add_column("Original Stake")
            problem_table.add_column("% Remaining")
            
            for item in problem_hotkeys:
                percent = (item['stake'] / item['orig_stake'] * 100) if item['orig_stake'] > 0 else 100
                problem_table.add_row(
                    item['wallet'],
                    item['hotkey'],
                    str(item['netuid']),
                    f"{item['stake']:.9f}",
                    f"{item['orig_stake']:.9f}",
                    f"{percent:.2f}%"
                )
            
            console.print(problem_table)
            
            console.print("\n[yellow]Automatically attempting SUPER EMERGENCY unstake for problematic hotkeys...[/yellow]")
            
            for item in problem_hotkeys:
                console.print(f"\n[bold]Attempting super emergency unstake for {item['wallet']}:{item['hotkey']} in subnet {item['netuid']} (stake: {item['stake']:.9f})[/bold]")
                
                try:
                    cmd = [
                        "btcli", "stake", "remove",
                        "--wallet.name", item['wallet'],
                        "--wallet.hotkey", item['hotkey'],
                        "--netuid", str(item['netuid']),
                        "--all",
                        "--allow-partial-stake",
                        "--tolerance", "0.999",
                        "--no_prompt"
                    ]
                    
                    console.print(f"[cyan]Running super emergency unstake command...[/cyan]")
                    
                    process = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    
                    pwd = shared_password if shared_password else password
                    stdout, stderr = process.communicate(input=f"{pwd}\n")
                    
                    if "Successfully" in stdout:
                        console.print(f"[green]Super emergency unstake successful![/green]")
                    else:
                        console.print(f"[yellow]Output from command:[/yellow]\n{stdout}")
                        if stderr:
                            console.print(f"[red]Errors:[/red]\n{stderr}")
                        
                        try:
                            specific_amount = item['stake'] * 0.95
                            alt_cmd = [
                                "btcli", "stake", "remove",
                                "--wallet.name", item['wallet'],
                                "--wallet.hotkey", item['hotkey'],
                                "--netuid", str(item['netuid']),
                                "--amount", f"{specific_amount:.9f}",
                                "--allow-partial-stake",
                                "--tolerance", "0.999",
                                "--no_prompt"
                            ]
                            
                            console.print(f"[cyan]Trying with specific amount {specific_amount:.9f}...[/cyan]")
                            
                            alt_process = subprocess.Popen(
                                alt_cmd,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True
                            )
                            
                            alt_stdout, alt_stderr = alt_process.communicate(input=f"{pwd}\n")
                            
                            if "Successfully" in alt_stdout:
                                console.print(f"[green]Specific amount unstake successful![/green]")
                            else:
                                console.print(f"[red]All unstake methods failed for this hotkey.[/red]")
                        except Exception as e:
                            console.print(f"[red]Error in specific amount unstake: {str(e)}[/red]")
                except Exception as e:
                    console.print(f"[red]Error in super emergency unstake: {str(e)}[/red]")

    def _handle_unstake_alpha_simple(self):
        import subprocess
        import time
        
        wallets = self.wallet_utils.get_available_wallets()
        if not wallets:
            console.print("[red]No wallets found![/red]")
            return

        console.print("\n[bold cyan]Simple Unstake Mode[/bold cyan]")
        console.print("[dim]This mode will unstake ALL tokens from selected wallets[/dim]")

        console.print("\n1. Unstake from specific subnet")
        console.print("2. Unstake from all subnets")
        subnet_choice = IntPrompt.ask("Select option", default=2)

        netuid_param = []
        if subnet_choice == 1:
            subnet_input = Prompt.ask("\nEnter subnet number")
            try:
                subnet_id = int(subnet_input.strip())
                netuid_param = ["--netuid", str(subnet_id)]
            except:
                console.print("[red]Invalid subnet input![/red]")
                return

        console.print("\nAvailable Wallets:")
        for wallet in wallets:
            console.print(f"  • {wallet}")

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

        if not selected_wallets:
            console.print("[red]No wallets selected![/red]")
            return

        console.print("\nPassword options:")
        console.print("1. Use same password for all wallets")
        console.print("2. Enter password for each wallet")
        password_choice = IntPrompt.ask("Select option", default=1)

        shared_password = None
        if password_choice == 1:
            default_password = self.config.get('wallet.default_password')
            if default_password:
                shared_password = Prompt.ask(
                    "Enter password (press Enter for default)",
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
                console.print(f"[red]Invalid password for: {', '.join(invalid_wallets)}[/red]")
                return

        console.print(f"\n[yellow]This will unstake ALL tokens from {len(selected_wallets)} wallets[/yellow]")
        if not Confirm.ask("Continue?"):
            return

        successful = 0
        failed = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Processing...", total=len(selected_wallets))

            for wallet_name in selected_wallets:
                progress.update(task, description=f"[cyan]Processing {wallet_name}...[/cyan]")
                
                try:
                    password = shared_password
                    if not shared_password:
                        password = Prompt.ask(f"Password for {wallet_name}", password=True)
                        if not self.transfer_manager.verify_wallet_password(wallet_name, password):
                            console.print(f"[red]Invalid password for {wallet_name}[/red]")
                            failed += 1
                            progress.update(task, advance=1)
                            continue

                    cmd = ["btcli", "stake", "remove", "--wallet-name", wallet_name, "--all-hotkeys", "--unstake-all", "--no-prompt"]
                    cmd.extend(netuid_param)

                    process = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )

                    stdout, stderr = process.communicate(input=f"{password}\n")
                    
                    if process.returncode == 0 and ("Successfully" in stdout or "Finalized" in stdout):
                        successful += 1
                        console.print(f"[green]Success: {wallet_name}[/green]")
                    else:
                        failed += 1
                        console.print(f"[red]Failed: {wallet_name}[/red]")
                        if stderr:
                            console.print(f"[red]{stderr}[/red]")

                except Exception as e:
                    failed += 1
                    console.print(f"[red]Error with {wallet_name}: {str(e)}[/red]")

                progress.update(task, advance=1)
                time.sleep(0.5)

        console.print(f"\n[bold]Results:[/bold]")
        console.print(f"[green]Successful: {successful}[/green]")
        console.print(f"[red]Failed: {failed}[/red]")
        console.print(f"Total: {len(selected_wallets)}")

    def _display_unstaking_summary(self, stake_summary):
        console.print("\n[bold cyan]===== Unstaking Summary =====[/bold cyan]")
        
        total_unstaked = 0
        successful_operations = 0
        failed_operations = 0
        total_attempted_wallets = len(stake_summary)
        wallets_with_operations = set()
        
        for wallet, wallet_data in stake_summary.items():
            wallet_unstaked = 0
            wallet_successful_ops = 0
            
            for netuid, subnet_data in wallet_data.items():
                for hotkey, before_data in subnet_data.get('before', {}).items():
                    original_stake = before_data.get('stake', 0.0)
                    
                    after_data = subnet_data.get('after', {}).get(hotkey, {})
                    success = after_data.get('success')
                    
                    if success == True:
                        if 'unstaked_amount' in after_data:
                            unstaked_amount = after_data['unstaked_amount']
                        else:
                            remaining = after_data.get('remaining', 0.0)
                            unstaked_amount = original_stake - remaining
                            
                        wallet_unstaked += unstaked_amount
                        wallet_successful_ops += 1
                        successful_operations += 1
                    elif success == False:
                        failed_operations += 1
                
            if wallet_successful_ops > 0 or wallet_unstaked > 0:
                wallets_with_operations.add(wallet)
                console.print(f"[green]Wallet {wallet}: Successfully unstaked {wallet_unstaked:.9f} Alpha TAO[/green]")
            
            total_unstaked += wallet_unstaked
        
        console.print("\n[bold cyan]===== Overall Statistics =====[/bold cyan]")
        stats_table = Table()
        stats_table.add_column("Metric", style="cyan")
        stats_table.add_column("Value", justify="right")
        
        stats_table.add_row("Total Alpha TAO Unstaked", f"[bold green]{total_unstaked:.9f}[/bold green]")
        stats_table.add_row("Successful Wallets", f"{len(wallets_with_operations)}/{total_attempted_wallets}")
        stats_table.add_row("Successful Operations", f"{successful_operations}")
        
        if failed_operations > 0:
            stats_table.add_row("Failed Operations", f"{failed_operations}")
        
        console.print(stats_table)
            

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

        console.print("\nAvailable Wallets:")
        for wallet in wallets:
            console.print(f"  • {wallet}")

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

        console.print("\nAvailable Wallets:")
        for wallet in wallets:
            console.print(f"  • {wallet}")

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
        for wallet in wallets:
            console.print(f"  • {wallet}")

        selection = Prompt.ask("Select wallet (enter wallet name)").strip()

        if selection not in wallets:
            console.print("[red]Invalid wallet name![/red]")
            return

        wallet_name = selection
            
        hotkeys = self.wallet_utils.get_wallet_hotkeys(wallet_name)
        if not hotkeys:
            console.print(f"[red]No hotkeys found for wallet {wallet_name}![/red]")
            return
            
        console.print(f"\nHotkeys for wallet {wallet_name}:")
        for hotkey in hotkeys:
            console.print(f"  • {hotkey}")
        
        hotkey_selection = Prompt.ask("Select hotkey (enter hotkey name)").strip()
        
        if hotkey_selection not in hotkeys:
            console.print("[red]Invalid hotkey name![/red]")
            return
        
        hotkey_name = hotkey_selection
            
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
        for wallet in wallets:
            console.print(f"  • {wallet}")

        selection = Prompt.ask("Select wallet (enter wallet name)").strip()
        
        if selection not in wallets:
            console.print("[red]Invalid wallet name![/red]")
            return
        
        wallet_name = selection
            
        hotkeys = self.wallet_utils.get_wallet_hotkeys(wallet_name)
        if not hotkeys:
            console.print(f"[red]No hotkeys found for wallet {wallet_name}![/red]")
            return
            
        console.print(f"\nHotkeys for wallet {wallet_name}:")
        for hotkey in hotkeys:
            console.print(f"  • {hotkey}")
            
        hotkey_selection = Prompt.ask("Select hotkey (enter hotkey name)").strip()
        
        if hotkey_selection not in hotkeys:
            console.print("[red]Invalid hotkey name![/red]")
            return
        
        hotkey_name = hotkey_selection
            
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
        for wallet in wallets:
            console.print(f"  • {wallet}")
        
        wallet_configs = []
        
        console.print("\nSelect wallets (comma-separated names, e.g. bot_1,bot_2,bot_3 or 'all')")
        wallet_selection = Prompt.ask("Selection").strip()
        
        selected_wallets = self.wallet_utils.parse_wallet_selection_by_names(wallet_selection, wallets)
        if not selected_wallets:
            console.print("[red]No valid wallets selected![/red]")
            return
        
        for wallet_name in selected_wallets:
            hotkeys = self.wallet_utils.get_wallet_hotkeys(wallet_name)
            if not hotkeys:
                console.print(f"[red]No hotkeys found for wallet {wallet_name}![/red]")
                continue
                
            console.print(f"\nHotkeys for wallet {wallet_name}:")
            for hotkey in hotkeys:
                console.print(f"  • {hotkey}")
                
            console.print("Select hotkeys (comma-separated names or 'all')")
            hotkey_selection = Prompt.ask("Selection").strip()
            
            if hotkey_selection.lower() == 'all':
                selected_hotkeys = hotkeys
            else:
                selected_hotkeys = [h.strip() for h in hotkey_selection.split(',') if h.strip() in hotkeys]
            
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
