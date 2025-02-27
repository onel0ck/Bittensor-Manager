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
           "6. Back to Main Menu"
        ))

        mode = IntPrompt.ask("Select option", default=6)

        if mode == 6:
            return

        if mode not in [1, 2, 3, 4, 5]:
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

                    if len(selected_hotkeys) > 1 and False:  # Disabled check to allow multiple hotkeys
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
            wallet_config_dict = {}
            
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

                    wallet_config_dict[wallet] = {
                        'hotkeys': selected_hotkeys,
                        'password': password,
                        'prep_time': prep_time,
                        'current_index': 0
                    }
                except:
                    console.print(f"[red]Invalid hotkey selection for {wallet}![/red]")
                    continue

            if wallet_config_dict:
                try:
                    asyncio.run(self.registration_manager.start_auto_registration(
                        wallet_config_dict,
                        subnet_id,
                        background_mode=False,
                        rpc_endpoint=rpc_endpoint
                    ))
                    
                except Exception as e:
                    console.print(f"[red]Auto registration error: {str(e)}[/red]")
                    
        elif mode == 5:
            # Spread Registration (Multiple Hotkeys with distributed timing)
            all_wallet_hotkeys = []
            wallet_passwords = {}
            
            # First collect all wallets and hotkeys
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
                    
                    for hotkey in selected_hotkeys:
                        all_wallet_hotkeys.append({
                            'coldkey': wallet,
                            'hotkey': hotkey
                        })
                except:
                    console.print(f"[red]Invalid hotkey selection for {wallet}![/red]")
                    continue
                    
            if not all_wallet_hotkeys:
                console.print("[red]No valid wallet/hotkey combinations selected![/red]")
                return
                
            # Ask for timing range
            console.print("\n[bold]Timing Distribution Range[/bold]")
            console.print("Enter the range of timing values to distribute across all hotkeys")
            min_timing = IntPrompt.ask("Minimum timing value (e.g. -20)", default=-20)
            max_timing = IntPrompt.ask("Maximum timing value (e.g. 0)", default=0)
            
            # Distribute timing values
            console.print(f"\n[cyan]Distributing timing values across {len(all_wallet_hotkeys)} hotkeys...[/cyan]")
            timing_values = self.registration_manager.spread_timing_across_hotkeys(
                len(all_wallet_hotkeys),
                min_timing,
                max_timing
            )
            
            # Create configuration with distributed timings
            wallet_configs = []
            
            table = Table(title="Timing Distribution")
            table.add_column("Wallet")
            table.add_column("Hotkey")
            table.add_column("Timing")
            
            for idx, wallet_hotkey in enumerate(all_wallet_hotkeys):
                timing = timing_values[idx]
                wallet_configs.append({
                    'coldkey': wallet_hotkey['coldkey'],
                    'hotkey': wallet_hotkey['hotkey'],
                    'password': wallet_passwords[wallet_hotkey['coldkey']],
                    'prep_time': timing
                })
                
                table.add_row(
                    wallet_hotkey['coldkey'],
                    wallet_hotkey['hotkey'],
                    f"{timing}s"
                )
                
            console.print(table)
            
            # Ask about retry strategy
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
            
            # Get registration info and confirm
            try:
                reg_info = self.registration_manager.get_registration_info(subnet_id)
                if reg_info:
                    self.registration_manager._display_registration_info(reg_info)
                    self.registration_manager._display_registration_config(wallet_configs, subnet_id, reg_info)
                    
                    if Confirm.ask("Proceed with registration?"):
                        results = asyncio.run(
                            self.registration_manager.start_registration(
                                wallet_configs=wallet_configs,
                                subnet_id=subnet_id,
                                start_block=reg_info['next_adjustment_block'],
                                prep_time=max(abs(cfg['prep_time']) for cfg in wallet_configs),
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
                    console.print("[red]Failed to get registration information![/red]")
                    
            except Exception as e:
                console.print(f"[red]Registration error: {str(e)}[/red]")

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

            for wallet_index, wallet in enumerate(selected_wallets):
                console.print(f"\nProcessing wallet {wallet} ({wallet_index+1}/{len(selected_wallets)})...")
                
                try:
                    console.print(f"Finding active subnets for {wallet}...")
                    
                    if subnet_list is None:
                        active_subnets = self.stats_manager.get_active_subnets_direct(wallet)
                    else:
                        active_subnets = subnet_list
                    
                    console.print(f"Getting data for {wallet} ({len(active_subnets)} subnets)...")
                    
                    stats = await self.stats_manager.get_wallet_stats(wallet, active_subnets, hide_zeros)
                    
                    if stats:
                        console.print(f"[green]Completed data collection for {wallet}[/green]")
                        self._display_wallet_stats(stats)
                    else:
                        console.print(f"[yellow]No stats found for wallet {wallet}[/yellow]")
                except Exception as e:
                    console.print(f"[red]Error getting stats for {wallet}: {str(e)}[/red]")

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
            "2. Unstake Alpha TAO\n"
            "3. Back to Main Menu"
        ))

        choice = IntPrompt.ask("Select option", default=3)

        if choice == 3:
            return

        if choice == 1:
            self._handle_transfer()
        elif choice == 2:
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
            """Try to get TAO price from various sources"""
            try:
                if hasattr(self.transfer_manager, 'stats_manager') and hasattr(self.transfer_manager.stats_manager, '_get_tao_price'):
                    return self.transfer_manager.stats_manager._get_tao_price()
                return None
            except:
                return None
