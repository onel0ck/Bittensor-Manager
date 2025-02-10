import os
import bittensor as bt
from typing import Dict, List, Optional, Tuple
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt
from rich.status import Status
from ..utils.logger import setup_logger
import time

logger = setup_logger('transfer_manager', 'logs/transfer_manager.log')
console = Console()

class TransferManager:
    def __init__(self, config):
        self.config = config
        self.subtensor = bt.subtensor()

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

    def get_stake_info(self, coldkey_name: str) -> Dict:
        try:
            wallet = bt.wallet(name=coldkey_name)
            metagraph = self.subtensor.metagraph(netuid=1)

            stake_info = {
                'total_stake': 0,
                'hotkeys': []
            }

            hotkeys_path = f"~/.bittensor/wallets/{coldkey_name}/hotkeys"
            wallet_hotkeys = []

            for hotkey_name in os.listdir(os.path.expanduser(hotkeys_path)):
                try:
                    hotkey_wallet = bt.wallet(name=coldkey_name, hotkey=hotkey_name)
                    hotkey_info = {
                        'name': hotkey_name,
                        'address': hotkey_wallet.hotkey.ss58_address,
                        'stake': 0
                    }

                    try:
                        uid = metagraph.hotkeys.index(hotkey_wallet.hotkey.ss58_address)
                        stake = float(metagraph.stake[uid])
                        hotkey_info['stake'] = stake
                        stake_info['total_stake'] += stake
                    except ValueError:
                        pass

                    stake_info['hotkeys'].append(hotkey_info)

                except Exception as e:
                    logger.error(f"Error processing hotkey {hotkey_name}: {e}")
                    continue

            return stake_info

        except Exception as e:
            logger.error(f"Error getting stake info for {coldkey_name}: {e}")
            raise

    def unstake_from_hotkey(self, coldkey_name: str, hotkey_name: str, amount: Optional[float] = None, password: str = None) -> bool:
        try:
            wallet = bt.wallet(name=coldkey_name, hotkey=hotkey_name)
            if password:
                wallet.coldkey_file.decrypt(password)

            if amount is None:
                success = self.subtensor.unstake_all(
                    wallet=wallet,
                    wait_for_inclusion=True,
                    wait_for_finalization=True
                )
            else:
                success = self.subtensor.unstake(
                    wallet=wallet,
                    amount=amount,
                    wait_for_inclusion=True,
                    wait_for_finalization=True
                )

            return success

        except Exception as e:
            logger.error(f"Error unstaking from {coldkey_name}:{hotkey_name}: {e}")
            return False

    def unstake_all(self, coldkey_name: str, password: str = None) -> bool:
        try:
            stake_info = self.get_stake_info(coldkey_name)
            success = True

            for hotkey in stake_info['hotkeys']:
                if hotkey['stake'] > 0:
                    if not self.unstake_from_hotkey(coldkey_name, hotkey['name'], password=password):
                        success = False
                    time.sleep(2)

            return success

        except Exception as e:
            logger.error(f"Error unstaking all from {coldkey_name}: {e}")
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

    def display_stake_summary(self, stake_info: Dict):
        table = Table(title="Staking Summary")
        table.add_column("Hotkey")
        table.add_column("Stake (τ)")
        table.add_column("Address")

        for hotkey in stake_info['hotkeys']:
            if hotkey['stake'] > 0:
                table.add_row(
                    hotkey['name'],
                    f"{hotkey['stake']:.9f}",
                    hotkey['address']
                )

        table.add_row(
            "[bold]Total[/bold]",
            f"[bold]{stake_info['total_stake']:.9f}[/bold]",
            "",
            style="bold green"
        )

        console.print(table)

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
                stake_info = self.get_stake_info(selected_wallet)
                if stake_info['total_stake'] == 0:
                    console.print("[yellow]No active stakes found for this wallet![/yellow]")
                    return

                self.display_stake_summary(stake_info)
            except Exception as e:
                console.print(f"[red]Error getting stake information: {str(e)}[/red]")
                return

        console.print("\n1. Unstake all TAO")
        console.print("2. Unstake from specific hotkey")
        console.print("3. Cancel")

        unstake_choice = IntPrompt.ask("Select option", default=3)

        if unstake_choice == 1:
            if Confirm.ask("Are you sure you want to unstake all TAO?"):
                password = self._get_wallet_password(selected_wallet)

                with Status("[bold green]Processing unstake...", spinner="dots"):
                    try:
                        if not self.verify_wallet_password(selected_wallet, password):
                            console.print("[red]Invalid password![/red]")
                            return
                        if self.unstake_all(selected_wallet, password):
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

            password = self._get_wallet_password(selected_wallet)

            with Status("[bold green]Processing unstake...", spinner="dots"):
                try:
                    if not self.verify_wallet_password(selected_wallet, password):
                        console.print("[red]Invalid password![/red]")
                        return

                    if self.unstake_from_hotkey(
                        selected_wallet, selected_hotkey['name'], amount, password
                    ):
                        console.print("[green]Successfully unstaked TAO![/green]")
                    else:
                        console.print("[red]Error during unstaking process![/red]")
                except Exception as e:
                    console.print(f"[red]Error: {str(e)}[/red]")
