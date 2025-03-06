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


    def get_alpha_stake_info(self, coldkey_name: str, subnet_list: Optional[List[int]] = None) -> List[Dict]:
        try:
            wallet = bt.wallet(name=coldkey_name)
            stake_info = []

            if subnet_list is None:
                active_subnets = self._get_active_subnets(coldkey_name)
            else:
                active_subnets = subnet_list

            for netuid in active_subnets:
                try:
                    metagraph = self.subtensor.metagraph(netuid)
                    subnet_info = {
                        'netuid': netuid,
                        'hotkeys': []
                    }

                    hotkeys_path = os.path.expanduser(f"~/.bittensor/wallets/{coldkey_name}/hotkeys")
                    for hotkey_name in os.listdir(hotkeys_path):
                        try:
                            hotkey_wallet = bt.wallet(name=coldkey_name, hotkey=hotkey_name)
                            hotkey_address = hotkey_wallet.hotkey.ss58_address

                            try:
                                uid = metagraph.hotkeys.index(hotkey_address)
                                stake = float(metagraph.stake[uid])
                                
                                if stake > 0:
                                    subnet_info['hotkeys'].append({
                                        'name': hotkey_name,
                                        'address': hotkey_address,
                                        'stake': stake,
                                        'uid': uid
                                    })
                            except ValueError:
                                continue

                        except Exception as e:
                            logger.error(f"Error processing hotkey {hotkey_name}: {e}")
                            continue

                    if subnet_info['hotkeys']:
                        stake_info.append(subnet_info)

                except Exception as e:
                    logger.error(f"Error processing subnet {netuid}: {e}")
                    continue

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
            table.add_column("Address")

            total_stake = 0
            for hotkey in subnet['hotkeys']:
                if hotkey['stake'] > 0:
                    total_stake += hotkey['stake']
                    table.add_row(
                        hotkey['name'],
                        str(hotkey['uid']),
                        f"{hotkey['stake']:.9f}",
                        hotkey['address']
                    )

            table.add_row(
                "[bold]Total[/bold]",
                "",
                f"[bold]{total_stake:.9f}[/bold]",
                "",
                style="bold green"
            )

            console.print(table)

    def unstake_alpha(self, coldkey: str, hotkey: str, netuid: int, amount: float, password: str, tolerance: float = 0.45) -> bool:
        try:
            cmd = [
                "btcli", "stake", "remove",
                "--wallet.name", coldkey,
                "--wallet.hotkey", hotkey,
                "--netuid", str(netuid),
                "--amount", f"{amount:.9f}",
                "--allow-partial-stake",
                "--tolerance", str(tolerance),
                "--no_prompt"
            ]

            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            stdout, stderr = process.communicate(input=f"{password}\n")

            if process.returncode == 0 and "Error" not in stdout:
                return True
            else:
                logger.error(f"Unstake failed. Stdout: {stdout}, Stderr: {stderr}")
                return False

        except Exception as e:
            logger.error(f"Error unstaking alpha from {coldkey}:{hotkey}: {e}")
            return False

    def _get_active_subnets(self, wallet_name: str) -> List[int]:
        try:
            temp_file = "overview_output.txt"
            cmd = f'COLUMNS=1000 btcli wallet overview --wallet.name {wallet_name} > {temp_file}'

            process = subprocess.run(cmd, shell=True)

            with open(temp_file, 'r') as f:
                output = f.read()

            subprocess.run(f'rm {temp_file}', shell=True)

            active_subnets = []
            current_subnet = None

            for line in output.split('\n'):
                subnet_match = re.search(r'Subnet:\s*(\d+):', line)
                if subnet_match:
                    current_subnet = int(subnet_match.group(1))

                if current_subnet is not None and ('STAKE' in line or 'EMISSION' in line):
                    numbers = re.findall(r'\d+\.\d+|\d+', line)
                    if numbers and any(float(n) > 0 for n in numbers):
                        active_subnets.append(current_subnet)
                        current_subnet = None

            return list(set(active_subnets))

        except Exception as e:
            logger.error(f"Failed to get active subnets: {e}")
            return []
