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

console = Console()

class RegistrationMenu:
    def __init__(self, registration_manager, config):
        self.registration_manager = registration_manager
        self.config = config
        self.wallet_utils = WalletUtils()

    def show(self):
       console.print("\n[bold]Register Wallets[/bold]")
       console.print(Panel.fit(
           "1. Simple Registration (Immediate)\n"
           "2. Professional Registration (Next Adjustment)\n"
           "3. Auto Registration (Multiple Adjustments)\n"
           "4. Back to Main Menu"
       ))

       mode = IntPrompt.ask("Select option", default=4)
       
       if mode == 4:
           return
           
       if mode not in [1, 2, 3]:
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

       subnet_id = IntPrompt.ask("Enter subnet ID for registration", default=1)

       wallet_configs = []
       for wallet in selected_wallets:
           password = Prompt.ask(f"Enter password for {wallet}", password=True)
           if not self.registration_manager.verify_wallet_password(wallet, password):
               console.print(f"[red]Invalid password for {wallet}[/red]")
               return
               
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
                       'prep_time': 15
                   })
           except:
               console.print(f"[red]Invalid hotkey selection for {wallet}![/red]")
               continue

       try:
           if mode == 1:  # Simple Registration
               asyncio.run(self.registration_manager.start_registration(
                   wallet_configs=wallet_configs,
                   subnet_id=subnet_id,
                   start_block=0,
                   prep_time=15
               ))
           elif mode == 2:  # Professional Registration
               reg_info = self.registration_manager.get_registration_info(subnet_id)
               if reg_info:
                   self.registration_manager._display_registration_info(reg_info)
                   self.registration_manager._display_registration_config(wallet_configs, subnet_id, reg_info)
                   if Confirm.ask("Proceed with registration?"):
                       asyncio.run(self.registration_manager.start_registration(
                           wallet_configs=wallet_configs,
                           subnet_id=subnet_id,
                           start_block=reg_info['next_adjustment_block'],
                           prep_time=15
                       ))
           elif mode == 3:  # Auto Registration
               wallet_config_dict = {}
               for wallet in selected_wallets:
                   wallet_config_dict[wallet] = {
                       'hotkeys': selected_hotkeys,  
                       'password': password,
                       'current_index': 0
                   }
               asyncio.run(self.registration_manager.start_auto_registration(wallet_config_dict, subnet_id))
               
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

        console.print(f"\n[bold]Wallet: {stats['coldkey']}[/bold]")
        console.print(f"Balance: {stats['balance']:.9f} τ")
        console.print(f"Total Stake: {stats['total_stake']:.9f} τ")
        console.print(f"Daily Rewards: {stats['daily_rewards']:.9f} $")

        for subnet in stats['subnets']:
            table = Table(title=f"Subnet {subnet['netuid']}")
            table.add_column("Hotkey")
            table.add_column("UID")
            table.add_column("Stake")
            table.add_column("Rank")
            table.add_column("Trust")
            table.add_column("Consensus")
            table.add_column("Incentive")
            table.add_column("Dividends")
            table.add_column("Emission")

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
                    f"{neuron['emission']:.9f}"
                )

            console.print(table)

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

            console.print("\n1. Check all subnets")
            console.print("2. Check specific subnets")
            subnet_choice = IntPrompt.ask("Select option", default=1)

            subnet_list = None
            if subnet_choice == 2:
                subnet_input = Prompt.ask("\nEnter subnet numbers (comma-separated)")
                try:
                    subnet_list = [int(s.strip()) for s in subnet_input.split(',')]
                except:
                    console.print("[red]Invalid subnet input![/red]")
                    continue

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True
            ) as progress:
                task = progress.add_task("[cyan]Fetching stats...", total=len(selected_wallets))

                for wallet in selected_wallets:
                    try:
                        stats = await self.stats_manager.get_wallet_stats(wallet, subnet_list)
                        self._display_wallet_stats(stats)
                    except Exception as e:
                        console.print(f"[red]Error getting stats for {wallet}: {str(e)}[/red]")
                    progress.update(task, advance=1)

class BalanceMenu:
    def __init__(self, stats_manager, wallet_utils):
        self.stats_manager = stats_manager
        self.wallet_utils = wallet_utils

    def show(self):
        while True:
            console.print("\n[bold]Balance Menu[/bold]")
            console.print(Panel.fit(
                "1. Check TAO Balance\n"
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
                            f"{balance_float:.2f}"
                        )
                    except Exception as e:
                        table.add_row(
                            wallet_name,
                            f"[red]Error: {str(e)}[/red]"
                        )
                    progress.update(task, advance=1)

            table.add_row(
                "[bold]Total[/bold]",
                f"[bold]{total_balance:.2f}[/bold]",
                style="bold green"
            )

            console.print("\n")
            console.print(table)

            if not Confirm.ask("Check another balance?"):
                return

class TransferMenu:
    def __init__(self, transfer_manager, wallet_utils):
        self.transfer_manager = transfer_manager
        self.wallet_utils = wallet_utils

    def show(self):
        console.print("\n[bold]TAO Transfer and Unstaking Menu[/bold]")
        console.print(Panel.fit(
            "1. Transfer TAO\n"
            "2. Unstake TAO\n"
            "3. Back to Main Menu"
        ))

        choice = IntPrompt.ask("Select option", default=3)

        if choice == 3:
            return

        if choice == 1:
            self._handle_transfer()
        elif choice == 2:
            self._handle_unstake()

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

    def _handle_unstake(self):
        wallets = self.wallet_utils.get_available_wallets()
        if not wallets:
            console.print("[red]No wallets found![/red]")
            return

        console.print("\nAvailable Wallets:")
        for i, wallet in enumerate(wallets, 1):
            console.print(f"{i}. {wallet}")

        selection = Prompt.ask("Select wallet (number)").strip()
        try:
            index = int(selection) - 1
            if not (0 <= index < len(wallets)):
                console.print("[red]Invalid wallet selection![/red]")
                return
            selected_wallet = wallets[index]
        except ValueError:
            console.print("[red]Invalid input![/red]")
            return

        with Status("[bold green]Getting stake information...", spinner="dots"):
            try:
                stake_info = self.transfer_manager.get_stake_info(selected_wallet)
                if stake_info['total_stake'] == 0:
                    console.print("[yellow]No active stakes found for this wallet![/yellow]")
                    return

                self.transfer_manager.display_stake_summary(stake_info)
            except Exception as e:
                console.print(f"[red]Error getting stake information: {str(e)}[/red]")
                return

        console.print("\n1. Unstake all TAO")
        console.print("2. Unstake from specific hotkey")
        console.print("3. Cancel")

        unstake_choice = IntPrompt.ask("Select option", default=3)

        if unstake_choice == 1:
            if Confirm.ask("Are you sure you want to unstake all TAO?"):
                password = Prompt.ask("Enter wallet password", password=True)
                
                with Status("[bold green]Processing unstake...", spinner="dots"):
                    try:
                        if not self.transfer_manager.verify_wallet_password(selected_wallet, password):
                            console.print("[red]Invalid password![/red]")
                            return
                        if self.transfer_manager.unstake_all(selected_wallet, password):
                            console.print("[green]Successfully unstaked all TAO![/green]")
                        else:
                            console.print("[red]Error during unstaking process![/red]")
                    except Exception as e:
                        console.print(f"[red]Error: {str(e)}[/red]")

        elif unstake_choice == 2:
            staked_hotkeys = [h for h in stake_info['hotkeys'] if h['stake'] > 0]
            if not staked_hotkeys:
                console.print("[yellow]No staked hotkeys found![/yellow]")
                return

            console.print("\nStaked Hotkeys:")
            for i, hotkey in enumerate(staked_hotkeys, 1):
                console.print(f"{i}. {hotkey['name']} - {hotkey['stake']:.9f} TAO")

            hotkey_selection = Prompt.ask("Select hotkey (number)").strip()
            try:
                hotkey_index = int(hotkey_selection) - 1
                if not (0 <= hotkey_index < len(staked_hotkeys)):
                    console.print("[red]Invalid hotkey selection![/red]")
                    return
                selected_hotkey = staked_hotkeys[hotkey_index]
            except ValueError:
                console.print("[red]Invalid input![/red]")
                return

            console.print("\n1. Unstake specific amount")
            console.print("2. Unstake all from this hotkey")
            amount_choice = IntPrompt.ask("Select option", default=2)

            amount = None
            if amount_choice == 1:
                try:
                    amount = float(Prompt.ask("Enter amount of TAO to unstake"))
                    if amount <= 0 or amount > selected_hotkey['stake']:
                        console.print("[red]Invalid amount![/red]")
                        return
                except ValueError:
                    console.print("[red]Invalid input![/red]")
                    return

            password = Prompt.ask("Enter wallet password", password=True)
            
            with Status("[bold green]Processing unstake...", spinner="dots"):
                try:
                    if not self.transfer_manager.verify_wallet_password(selected_wallet, password):
                        console.print("[red]Invalid password![/red]")
                        return

                    if self.transfer_manager.unstake_from_hotkey(
                        selected_wallet, selected_hotkey['name'], amount, password
                    ):
                        console.print("[green]Successfully unstaked TAO![/green]")
                    else:
                        console.print("[red]Error during unstaking process![/red]")
                except Exception as e:
                    console.print(f"[red]Error: {str(e)}[/red]")
