import bittensor as bt
import asyncio
import time
import subprocess
import re
import os
import pty
import tty
import termios
import select
import signal
from rich.live import Live
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.console import Console
from typing import List, Dict, Optional, Tuple
from ..utils.logger import setup_logger

logger = setup_logger('registration_manager', 'logs/registration.log')
console = Console()

class RegistrationError(Exception):
    pass

class RegistrationLimitReached(RegistrationError):
    pass

class WalletRegistration:
    def __init__(self, coldkey: str, hotkey: str, password: str, prep_time: int = 15):
        self.coldkey = coldkey
        self.hotkey = hotkey
        self.password = password
        self.prep_time = prep_time
        self.status = "Waiting"
        self.progress = 0
        self.error = None
        self.start_time = None
        self.end_time = None
        self.buffer = ""
        self.uid = None

    def update_status(self, status: str):
        self.status = status
        if not self.start_time:
            self.start_time = time.time()

    def complete(self, success: bool, error: Optional[str] = None):
        self.end_time = time.time()
        self.status = "Success" if success else "Failed"
        self.error = error
        self.progress = 100 if success else 0

    def update_progress(self, progress: int):
        self.progress = progress

class BlockInfo:
    def __init__(self):
        self.current_block = None
        self.blocks_history = []
        self.max_history = 100
        self.last_update = None

    def update(self, block_num: int):
        now = time.time()
        if self.current_block != block_num:
            if self.last_update:
                interval = now - self.last_update
                self.blocks_history.append(interval)
                if len(self.blocks_history) > self.max_history:
                    self.blocks_history.pop(0)
            self.current_block = block_num
            self.last_update = now

    def get_block_time_stats(self):
        if not self.blocks_history:
            return None
        return sum(self.blocks_history) / len(self.blocks_history)

class RegistrationManager:
    def __init__(self, config):
        self.config = config
        self.subtensor = bt.subtensor()
        self.active_registrations = {}
        self.block_info = BlockInfo()

    def verify_wallet_password(self, coldkey: str, password: str) -> bool:
        try:
            wallet = bt.wallet(name=coldkey)
            wallet.coldkey_file.decrypt(password)
            return True
        except Exception as e:
            logger.error(f"Failed to verify password for wallet {coldkey}: {e}")
            return False

    def _display_registration_info(self, reg_info: dict):
        table = Table(title="Registration Information", show_header=True, header_style="bold")

        table.add_column("Metric")
        table.add_column("Value")

        table.add_row("Current Block", str(reg_info['current_block']))
        table.add_row("Last Adjustment Block", str(reg_info['last_adjustment_block']))
        table.add_row("Blocks Until Next Adjustment", str(reg_info['blocks_until_adjustment']))
        table.add_row("Next Adjustment Block", str(reg_info['next_adjustment_block']))
        table.add_row("Registrations", f"{reg_info['total_registrations']}/{reg_info['max_registrations']}")
        table.add_row("Registration Status", "Open" if reg_info['registration_allowed'] else "Closed")
        table.add_row("Estimated Time Until Adjustment", f"{reg_info['seconds_until_adjustment']:.0f}s")

        console.print(table)

    def _display_registration_config(self, wallet_configs: list, subnet_id: int, reg_info: dict):
        table = Table(title="Registration Configuration", show_header=True, header_style="bold")

        table.add_column("Wallet")
        table.add_column("Hotkey")
        table.add_column("Subnet")
        table.add_column("Start Block")
        table.add_column("Prep Time")
        table.add_column("Registration Cost")

        cost_per_registration = float(reg_info['neuron_cost']) / 1e9

        for cfg in wallet_configs:
            table.add_row(
                cfg['coldkey'],
                cfg['hotkey'],
                str(subnet_id),
                str(reg_info['next_adjustment_block']),
                f"{cfg.get('prep_time', 0)}s",
                f"TAO {cost_per_registration:.9f}"
            )

        console.print(table)

    def get_registration_info(self, netuid: int) -> dict:
        try:
            import requests

            api_key = self.config.get('taostats.api_key')
            if not api_key:
                logger.error("TaoStats API key not configured")
                return None

            url = f"{self.config.get('taostats.api_url', 'https://api.taostats.io/api')}/subnet/latest/v1?netuid={netuid}"
            headers = {
                "accept": "application/json",
                "Authorization": api_key
            }

            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                logger.error(f"API request failed: {response.status_code}")
                return None

            subnet_data = response.json()['data'][0]

            last_adjustment_block = subnet_data['last_adjustment_block']
            adjustment_interval = subnet_data['adjustment_interval']
            next_adjustment_block = last_adjustment_block + adjustment_interval

            avg_block_time = 12 if not self.block_info.blocks_history else sum(self.block_info.blocks_history) / len(self.block_info.blocks_history)

            return {
                'current_block': subnet_data['block_number'],
                'last_adjustment_block': last_adjustment_block,
                'adjustment_interval': adjustment_interval,
                'blocks_until_adjustment': subnet_data['blocks_until_next_adjustment'],
                'next_adjustment_block': next_adjustment_block,
                'total_registrations': subnet_data['active_keys'],
                'max_registrations': subnet_data['max_neurons'],
                'registration_allowed': subnet_data['registration_allowed'],
                'neuron_cost': int(subnet_data['neuron_registration_cost']),
                'avg_block_time': avg_block_time,
                'seconds_until_adjustment': subnet_data['blocks_until_next_adjustment'] * avg_block_time
            }

        except Exception as e:
            logger.error(f"Error getting registration info: {e}")
            return None
    async def start_auto_registration(self, wallet_configs: dict, subnet_id: int):
        max_registration_cost = float(Prompt.ask(
            "Enter maximum registration cost in TAO (0 for no limit)",
            default="0"
        ))
        
        console.print(f"\n[yellow]Enter preparation times (1-19 seconds)[/yellow]")
        for coldkey, cfg in wallet_configs.items():
            suggested_prep = 15
            prep_time = IntPrompt.ask(
                f"Enter preparation time for {coldkey} in seconds",
                default=suggested_prep
            )
            cfg['prep_time'] = max(1, min(19, prep_time))

        while any(cfg['current_index'] < len(cfg['hotkeys']) for cfg in wallet_configs.values()):
            console.print(f"\n[cyan]Checking next registration batch...[/cyan]")

            reg_info = self.get_registration_info(subnet_id)
            if not reg_info:
                console.print("[red]Failed to get registration information![/red]")
                break

            cost_in_tao = float(reg_info['neuron_cost']) / 1e9
            if max_registration_cost > 0 and cost_in_tao > max_registration_cost:
                console.print(f"[red]Registration cost ({cost_in_tao:.9f} TAO) exceeds limit ({max_registration_cost} TAO)[/red]")
                await asyncio.sleep(60)
                continue

            current_batch = []
            for coldkey, cfg in wallet_configs.items():
                if cfg['current_index'] < len(cfg['hotkeys']):
                    hotkey = cfg['hotkeys'][cfg['current_index']]
                    current_batch.append({
                        'coldkey': coldkey,
                        'hotkey': hotkey,
                        'password': cfg['password'],
                        'prep_time': cfg['prep_time']
                    })

            if not current_batch:
                console.print("[green]All hotkeys have been registered successfully![/green]")
                break

            try:
                registrations = await self.start_registration(
                    wallet_configs=current_batch,
                    subnet_id=subnet_id,
                    start_block=reg_info['next_adjustment_block'],
                    prep_time=max(cfg.get('prep_time', 15) for cfg in current_batch)
                )

                for reg in registrations.values():
                    if reg.status == "Success":
                        wallet_configs[reg.coldkey]['current_index'] += 1

            except Exception as e:
                console.print(f"[red]Registration error: {str(e)}[/red]")
                await asyncio.sleep(60)
                continue

            if reg_info['blocks_until_adjustment'] > 0:
                await asyncio.sleep(reg_info['seconds_until_adjustment'])

    def _verify_registration_success(self, reg, subnet_id: int) -> tuple[bool, Optional[int]]:
        try:
            if reg.status != "Success":
                return False, None
            
            wallet = bt.wallet(name=reg.coldkey, hotkey=reg.hotkey)
            metagraph = self.subtensor.metagraph(netuid=subnet_id)

            try:
                uid = metagraph.hotkeys.index(wallet.hotkey.ss58_address)
                if uid > 0:
                    reg.uid = uid
                    return True, uid
            except ValueError:
                pass

            neuron = self.subtensor.get_neuron_for_pubkey_and_subnet(
                wallet.hotkey.ss58_address,
                subnet_id
            )
            if neuron is not None and neuron.uid > 0:
                reg.uid = neuron.uid
                return True, neuron.uid

        except Exception as e:
            logger.error(f"Error verifying registration for {reg.coldkey}:{reg.hotkey}: {e}")

        return False, None

    def check_registration(self, coldkey: str, hotkey: str, subnet_id: int) -> tuple[bool, Optional[int]]:
        try:
            wallet = bt.wallet(name=coldkey, hotkey=hotkey)
            metagraph = self.subtensor.metagraph(netuid=subnet_id)
            try:
                uid = metagraph.hotkeys.index(wallet.hotkey.ss58_address)
                return True, uid
            except ValueError:
                return False, None
        except Exception as e:
            logger.error(f"Error checking registration: {e}")
            return False, None

    def _simplify_error_message(self, error_text: str) -> str:
        if not error_text:
            return "Unknown error"
            
        if "? Failed:" in error_text:
            parts = error_text.split("? Failed:")
            error_part = parts[1].strip()
            
            if "SubstrateRequestException" in error_part:
                if "Custom error: 5" in error_part:
                    return "Registration limit reached"
                if "priority" in error_part:
                    return "Low priority transaction"
                return "Network error during registration"
            
            return error_part.split('\n')[0].strip()
        
        if "default wallet path" in error_text.lower():
            log_path = error_text.split("logs/registration/")[-1].split(".log")[0] + ".log"
            return f"Details in: logs/registration/{log_path}"

        return "Registration failed (see logs)"

    async def _register_wallet(self, registration: WalletRegistration, subnet_id: int) -> bool:
        master_fd, slave_fd = pty.openpty()
        log_file = f"logs/registration/registration_{registration.coldkey}_{registration.hotkey}_{int(time.time())}.log"
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        try:
            old_settings = termios.tcgetattr(slave_fd)
            tty.setraw(master_fd)

            process = subprocess.Popen(
                [
                    "btcli",
                    "subnet",
                    "register",
                    "--wallet.name", registration.coldkey,
                    "--wallet.hotkey", registration.hotkey,
                    "--netuid", str(subnet_id),
                    "--no_prompt"
                ],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                preexec_fn=os.setsid
            )

            registration.update_status("Registering")
            buffer = ""
            registration.buffer = ""
            timeout = time.time() + 180
            password_sent = False

            with open(log_file, 'w') as f:
                while time.time() < timeout:
                    try:
                        ready, _, _ = select.select([master_fd], [], [], 0.1)
                        if ready:
                            output = os.read(master_fd, 1024).decode()
                            buffer += output
                            registration.buffer = buffer
                            f.write(output)
                            f.flush()

                            if "Checking Balance" in buffer:
                                registration.update_progress(25)
                            elif "Recycling" in buffer:
                                registration.update_progress(50)
                            elif "Submitting" in buffer:
                                registration.update_progress(75)

                            if (("Enter password" in buffer.lower() or
                                 "Enter your password" in buffer.lower()) and
                                not password_sent):
                                os.write(master_fd, f"{registration.password}\n".encode())
                                password_sent = True
                                buffer = ""
                                await asyncio.sleep(0.5)
                                continue

                            if "[y/n]" in buffer or "continue?" in buffer:
                                os.write(master_fd, b"y\n")
                                buffer = ""
                                await asyncio.sleep(0.2)
                                continue

                            if "Success" in buffer or "Registered" in buffer:
                                registration.complete(True)
                                return True

                            if "Error" in buffer or "Failed" in buffer or "invalid" in buffer.lower():
                                if "? Failed:" in buffer:
                                    error_parts = buffer.split("? Failed:")
                                    error_msg = error_parts[-1].strip()
                                    error_lines = error_msg.split('\n')[:3]
                                    error_text = ' '.join(line.strip() for line in error_lines)
                                else:
                                    error_text = buffer
                                
                                simplified_error = self._simplify_error_message(error_text)
                                registration.complete(False, simplified_error)
                                return False

                            if process.poll() is not None:
                                if process.returncode == 0:
                                    registration.complete(True)
                                    return True
                                else:
                                    registration.complete(False, "Failed")
                                    return False

                            await asyncio.sleep(0.1)

                    except Exception as e:
                        registration.complete(False, self._simplify_error_message(str(e)))
                        return False

                registration.complete(False, "Timeout")
                return False

        except Exception as e:
            registration.complete(False, self._simplify_error_message(str(e)))
            return False

        finally:
            if process and process.poll() is None:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except:
                    pass

            try:
                termios.tcsetattr(slave_fd, termios.TCSADRAIN, old_settings)
            except:
                pass

            for fd in [master_fd, slave_fd]:
                try:
                    os.close(fd)
                except:
                    pass

    def _create_status_table(self, registrations: Dict[str, WalletRegistration], current_block: int, target_block: int) -> Table:
        table = Table(title=f"Registration Status (Block: {current_block} > {target_block})")
        table.add_column("Wallet")
        table.add_column("Hotkey")
        table.add_column("Status")
        table.add_column("Progress")
        table.add_column("Time")
        table.add_column("UID")
        table.add_column("Error", width=30)

        for reg in registrations.values():
            elapsed = ""
            if reg.start_time:
                current = reg.end_time or time.time()
                elapsed = f"{current - reg.start_time:.1f}s"

            status_color = (
                "green" if reg.status == "Success"
                else "yellow" if reg.status == "Verifying"
                else "red" if reg.status == "Failed"
                else "blue"
            )
            uid_display = f"{reg.uid}" if reg.uid is not None else ""
                
            error_display = ""
            if reg.error:
                if "? Failed:" in reg.buffer:
                    error_parts = reg.buffer.split("? Failed:")
                    error_msg = error_parts[-1].strip()
                    error_lines = error_msg.split('\n')
                    error_display = " ".join(error_lines[:3])
                else:
                    error_display = reg.error

            table.add_row(
                reg.coldkey,
                reg.hotkey,
                f"[{status_color}]{reg.status}[/{status_color}]",
                f"{reg.progress}%",
                elapsed,
                uid_display,
                error_display
            )

        return table

    async def start_registration(self, wallet_configs: list, subnet_id: int, start_block: int, prep_time: int):
        grouped_configs = {}
        for cfg in wallet_configs:
            if cfg['coldkey'] not in grouped_configs:
                grouped_configs[cfg['coldkey']] = []
            grouped_configs[cfg['coldkey']].append(cfg)

        registrations = {
            f"{cfg['coldkey']}:{cfg['hotkey']}": WalletRegistration(
                cfg['coldkey'],
                cfg['hotkey'],
                cfg['password'],
                prep_time=cfg.get('prep_time', 15)
            )
            for cfg in wallet_configs
        }

        for reg in list(registrations.values()):
            is_registered, uid = self.check_registration(reg.coldkey, reg.hotkey, subnet_id)
            if is_registered:
                logger.info(f"Wallet {reg.coldkey}:{reg.hotkey} already registered with UID {uid}")
                reg.uid = uid
                reg.complete(True, "Already registered")

        with Live(self._create_status_table(registrations, 0, start_block), refresh_per_second=4) as live:
            while True:
                try:
                    current_block = self.subtensor.get_current_block()
                    self.block_info.update(current_block)
                    blocks_remaining = start_block - current_block
                    table = self._create_status_table(registrations, current_block, start_block)
                    live.update(table)

                    if blocks_remaining > 0:
                        avg_block_time = self.block_info.get_block_time_stats() or 12
                        estimated_seconds = blocks_remaining * avg_block_time
                        await asyncio.sleep(0.2)
                        continue

                    for coldkey, configs in grouped_configs.items():
                        for cfg in configs:
                            reg = registrations[f"{cfg['coldkey']}:{cfg['hotkey']}"]
                            if reg.status == "Waiting":
                                await self._register_wallet(reg, subnet_id)
                                
                                if reg.status == "Success":
                                    success, uid = self._verify_registration_success(reg, subnet_id)
                                    if not success:
                                        reg.status = "Verifying"
                                        
                                table = self._create_status_table(registrations, current_block, start_block)
                                live.update(table)
                                await asyncio.sleep(2)

                    if not any(reg.status == "Waiting" for reg in registrations.values()):
                        break

                    await asyncio.sleep(0.2)

                except Exception as e:
                    logger.error(f"Registration error: {e}")
                    await asyncio.sleep(1)

        return registrations