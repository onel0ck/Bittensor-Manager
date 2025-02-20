import bittensor as bt
import asyncio
import threading
import queue
from rich.prompt import Prompt, IntPrompt
import time
from datetime import datetime
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
from typing import List, Dict, Optional, Tuple, Set
from ..utils.logger import setup_logger

logger = setup_logger('registration_manager', 'logs/registration.log')
console = Console()

class RegistrationError(Exception):
    pass

class RegistrationLimitReached(RegistrationError):
    pass

class ThreadedRegistration(threading.Thread):
    def __init__(self, registration_manager, wallet_config: dict, subnet_id: int, start_block: int):
        super().__init__()
        self.registration_manager = registration_manager
        self.wallet_config = wallet_config
        self.subnet_id = subnet_id
        self.start_block = start_block
        self.result = None
        self.registration = WalletRegistration(
            self.wallet_config['coldkey'],
            self.wallet_config['hotkey'],
            self.wallet_config['password'],
            self.wallet_config.get('prep_time', 0)
        )

    def run(self):
        try:
            success = asyncio.run(self.registration_manager._register_wallet(
                self.registration,
                self.subnet_id
            ))

            if "Registered on netuid" in self.registration.buffer:
                try:
                    uid_match = re.search(r"with UID (\d+)", self.registration.buffer)
                    if uid_match:
                        uid = int(uid_match.group(1))
                        self.registration.uid = uid
                        self.registration.status = "Success"
                        self.registration.progress = 100
                        self.registration.complete(True)
                        self.result = self.registration
                        return
                except Exception as e:
                    logger.error(f"Error extracting UID from output: {e}")

            if success:
                success, uid = self.registration_manager._verify_registration_success(
                    self.registration,
                    self.subnet_id
                )
                if success and uid is not None:
                    self.registration.uid = uid
                    self.registration.status = "Success"
                    self.registration.progress = 100
                    self.registration.complete(True)
                    self.result = self.registration
                    return

            error_text = self.registration.buffer
            if "TooManyRegistrationsThisBlock" in error_text:
                self.registration.complete(False, "TooManyRegistrationsThisBlock")
            elif "SubstrateRequestException" in error_text:
                if "InsufficientBalance" in error_text:
                    self.registration.complete(False, "InsufficientBalance")
                elif "priority is too low" in error_text:
                    self.registration.complete(False, "LowPriority")
                else:
                    self.registration.complete(False, "SubstrateRequestException")
            else:
                if "Success" in error_text or "Registered" in error_text:
                    self.registration.complete(True)
                else:
                    self.registration.complete(False, "Registration Failed")

            self.result = self.registration

        except Exception as e:
            logger.error(f"Thread error: {str(e)}")
            self.registration.complete(False, str(e))
            self.result = self.registration

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

    def _set_subtensor_network(self, rpc_endpoint: str = None):
        if rpc_endpoint:
            try:
                import ssl
                ssl_context = ssl.SSLContext()
                ssl_context.verify_mode = ssl.CERT_NONE
                ssl_context.check_hostname = False
                
                if rpc_endpoint.startswith('ws://'):
                    self.subtensor = bt.subtensor(network=rpc_endpoint, ssl_context=ssl_context)
                elif rpc_endpoint.startswith('wss://'):
                    self.subtensor = bt.subtensor(network=rpc_endpoint, ssl_context=ssl_context)
                else:
                    modified_endpoint = f"ws://{rpc_endpoint}"
                    self.subtensor = bt.subtensor(network=modified_endpoint, ssl_context=ssl_context)
                    
                logger.info(f"Connected to custom RPC: {rpc_endpoint}")
                return True
            except Exception as e:
                logger.error(f"Failed to connect to {rpc_endpoint}: {e}")
                try:
                    import ssl
                    ssl_context = ssl.SSLContext()
                    ssl_context.verify_mode = ssl.CERT_NONE
                    ssl_context.check_hostname = False
                    self.subtensor = bt.subtensor(ssl_context=ssl_context)
                    logger.info("Fallback to default endpoint")
                    return True
                except Exception as e2:
                    logger.error(f"Failed to connect to default endpoint: {e2}")
                    return False
        return True

    async def start_degen_registration(self, wallet_configs: List[Dict], target_subnet: int) -> None:
        degen = DegenRegistration(self)
        await degen.run(wallet_configs, target_subnet)

    async def _get_current_block_with_retry(self) -> int:
        max_retries = 3
        retry_delay = 0.2
        
        for attempt in range(max_retries):
            try:
                return self.subtensor.get_current_block()
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to get current block after {max_retries} attempts: {e}")
                    raise
                logger.warning(f"Error getting current block (attempt {attempt + 1}/{max_retries}): {e}")
                await asyncio.sleep(retry_delay)

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

    def _verify_registration_success(self, reg, subnet_id: int) -> tuple[bool, Optional[int]]:
        try:
            wallet = bt.wallet(name=reg.coldkey, hotkey=reg.hotkey)
            metagraph = self.subtensor.metagraph(netuid=subnet_id)

            if reg.buffer:
                uid_match = re.search(r"with UID (\d+)", reg.buffer)
                if uid_match:
                    uid = int(uid_match.group(1))
                    reg.uid = uid
                    reg.complete(True)
                    return True, uid

            try:
                uid = metagraph.hotkeys.index(wallet.hotkey.ss58_address)
                if uid >= 0:
                    reg.uid = uid
                    reg.status = "Success"
                    reg.progress = 100
                    reg.complete(True)
                    return True, uid
            except ValueError:
                pass

            neuron = self.subtensor.get_neuron_for_pubkey_and_subnet(
                wallet.hotkey.ss58_address,
                subnet_id
            )
            if neuron is not None and neuron.uid >= 0:
                reg.uid = neuron.uid
                reg.status = "Success"
                reg.progress = 100
                reg.complete(True)
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

                            if "Registered on netuid" in buffer:
                                try:
                                    import re
                                    uid_match = re.search(r"with UID (\d+)", buffer)
                                    if uid_match:
                                        registration.uid = int(uid_match.group(1))
                                        registration.complete(True)
                                        return True
                                except Exception as e:
                                    logger.error(f"Error extracting UID from output: {e}")

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
                                    if "Registered on netuid" in buffer:
                                        try:
                                            uid_match = re.search(r"with UID (\d+)", buffer)
                                            if uid_match:
                                                registration.uid = int(uid_match.group(1))
                                        except Exception as e:
                                            logger.error(f"Error extracting UID from output: {e}")
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
            if "Registered on netuid" in reg.buffer:
                try:
                    uid_match = re.search(r"with UID (\d+)", reg.buffer)
                    if uid_match:
                        reg.uid = int(uid_match.group(1))
                        reg.status = "Success"
                        reg.progress = 100
                        reg.complete(True)
                except:
                    pass

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

            uid_display = str(reg.uid) if reg.uid is not None else ""
            error_display = reg.error if reg.error else ""

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

    async def start_registration(self, wallet_configs: list, subnet_id: int, start_block: int, prep_time: int, rpc_endpoint: str = None):
        if not self._set_subtensor_network(rpc_endpoint):
            return None

        registrations = {}
        threads = []
        check_interval = 0.1
        consecutive_errors = 0
        max_consecutive_errors = 5

        for cfg in wallet_configs:
            key = f"{cfg['coldkey']}:{cfg['hotkey']}"
            prep_seconds = cfg.get('prep_time', 0)
            registrations[key] = WalletRegistration(
                cfg['coldkey'],
                cfg['hotkey'],
                cfg['password'],
                abs(prep_seconds)
            )

        status_table = self._create_status_table(registrations, 0, start_block)
        
        with Live(status_table, auto_refresh=False, vertical_overflow="visible") as live:
            last_block = 0
            
            while True:
                try:
                    current_block = await self._get_current_block_with_retry()
                    consecutive_errors = 0
                    
                    if current_block > last_block + 1 and last_block != 0:
                        logger.warning(f"Detected block jump: {last_block} -> {current_block}")
                        for cfg in wallet_configs:
                            key = f"{cfg['coldkey']}:{cfg['hotkey']}"
                            if registrations[key].status == "Waiting":
                                logger.info(f"Force starting registration for {key} due to block jump")
                                thread = ThreadedRegistration(
                                    self,
                                    cfg,
                                    subnet_id,
                                    current_block
                                )
                                thread.start()
                                threads.append(thread)

                    self.block_info.update(current_block)

                    for cfg in wallet_configs:
                        key = f"{cfg['coldkey']}:{cfg['hotkey']}"
                        prep_seconds = cfg.get('prep_time', 0)

                        if prep_seconds < 0:
                            blocks_early = abs(prep_seconds) / 12
                            target_block = start_block - blocks_early
                        else:
                            target_block = start_block

                        if current_block >= target_block and not any(t.registration.coldkey == cfg['coldkey'] for t in threads):
                            if registrations[key].status == "Waiting":
                                if prep_seconds > 0:
                                    registrations[key].status = f"Waiting +{prep_seconds}s"
                                    live.update(self._create_status_table(registrations, current_block, target_block))
                                    live.refresh()
                                    await asyncio.sleep(1)
                                    
                                thread = ThreadedRegistration(
                                    self,
                                    cfg,
                                    subnet_id,
                                    current_block
                                )
                                thread.start()
                                threads.append(thread)

                    active_threads = []
                    for thread in threads:
                        if thread.is_alive():
                            active_threads.append(thread)
                        else:
                            if thread.result:
                                key = f"{thread.wallet_config['coldkey']}:{thread.wallet_config['hotkey']}"
                                registrations[key] = thread.result

                    threads = active_threads
                    
                    live.update(self._create_status_table(registrations, current_block, target_block))
                    live.refresh()
                    await asyncio.sleep(1)

                    if not threads and not any(reg.status == "Waiting" for reg in registrations.values()):
                        break

                    last_block = current_block
                    await asyncio.sleep(check_interval)

                except Exception as e:
                    consecutive_errors += 1
                    logger.error(f"Error in registration loop: {e}")
                    
                    if consecutive_errors >= max_consecutive_errors:
                        raise Exception(f"Too many consecutive errors: {e}")
                    
                    await asyncio.sleep(0.2 * consecutive_errors)
                    continue

            return registrations


    async def start_auto_registration(self, wallet_configs: dict, subnet_id: int):
        max_registration_cost = float(Prompt.ask(
            "Enter maximum registration cost in TAO (0 for no limit)",
            default="0"
        ))

        while True:
            console.print(f"\n[cyan]Checking next registration batch...[/cyan]")

            all_complete = True
            for coldkey, cfg in wallet_configs.items():
                if cfg['current_index'] < len(cfg['hotkeys']):
                    all_complete = False
                    break

            if all_complete:
                console.print("[green]All registrations completed successfully![/green]")
                break

            reg_info = self.get_registration_info(subnet_id)
            if not reg_info:
                console.print("[red]Failed to get registration information![/red]")
                await asyncio.sleep(60)
                continue

            cost_in_tao = float(reg_info['neuron_cost']) / 1e9
            if max_registration_cost > 0 and cost_in_tao > max_registration_cost:
                console.print(f"[red]Registration cost ({cost_in_tao:.9f} TAO) exceeds limit ({max_registration_cost} TAO)[/red]")
                await asyncio.sleep(60)
                continue

            current_batch = []
            for coldkey, cfg in wallet_configs.items():
                if cfg['current_index'] < len(cfg['hotkeys']):
                    current_batch.append({
                        'coldkey': coldkey,
                        'hotkey': cfg['hotkeys'][cfg['current_index']],
                        'password': cfg['password'],
                        'prep_time': cfg['prep_time']
                    })

            if not current_batch:
                break

            try:
                registrations = await self.start_registration(
                    wallet_configs=current_batch,
                    subnet_id=subnet_id,
                    start_block=reg_info['next_adjustment_block'],
                    prep_time=max(cfg['prep_time'] for cfg in current_batch)
                )

                for reg in registrations.values():
                    if reg.status == "Success":
                        wallet_configs[reg.coldkey]['current_index'] += 1

                if reg_info['blocks_until_adjustment'] > 0:
                    await asyncio.sleep(reg_info['seconds_until_adjustment'])

            except Exception as e:
                console.print(f"[red]Registration error: {str(e)}[/red]")
                await asyncio.sleep(60)
                continue

    async def start_sniper_registration(self, wallet_configs: list, subnet_ids: list, check_interval: int, max_cost: float):
        table = Table(show_header=True, header_style="bold")
        table.add_column("Wallet")
        table.add_column("Hotkey")
        table.add_column("Subnet")
        table.add_column("Status")
        table.add_column("Current Cost")
        table.add_column("Max Cost")
        table.add_column("Registration")
        table.add_column("Messages")

        subnet_statuses = {subnet_id: "Initializing..." for subnet_id in subnet_ids}
        completed_subnets = set()
        last_api_call = {}

        def update_table(reg_infos=None, messages=None):
            table.rows = []
            if reg_infos is None:
                reg_infos = {subnet_id: None for subnet_id in subnet_ids}

            for cfg in wallet_configs:
                for subnet_id in subnet_ids:
                    if subnet_id in completed_subnets:
                        continue

                    reg_info = reg_infos.get(subnet_id)
                    status = subnet_statuses.get(subnet_id, f"Waiting {check_interval}s...")
                    message = messages.get(subnet_id, "") if messages else ""

                    if reg_info:
                        cost_in_tao = float(reg_info['neuron_cost']) / 1e9
                        cost_display = f"TAO {cost_in_tao:.9f}"
                        reg_status = "Open ?" if reg_info['registration_allowed'] else "Closed ?"
                    else:
                        cost_display = "Checking..."
                        reg_status = "Checking..."

                    table.add_row(
                        cfg['coldkey'],
                        cfg['hotkey'],
                        str(subnet_id),
                        status,
                        cost_display,
                        f"TAO {max_cost:.9f}",
                        reg_status,
                        message
                    )

            return table

        with Live(update_table(), refresh_per_second=1) as live:
            while len(completed_subnets) < len(subnet_ids):
                messages = {}
                reg_infos = {}

                for subnet_id in subnet_ids:
                    if subnet_id in completed_subnets:
                        continue

                    current_time = time.time()
                    last_call_time = last_api_call.get(subnet_id, 0)
                    
                    if current_time - last_call_time < 20:
                        messages[subnet_id] = f"Waiting API cooldown ({int(20 - (current_time - last_call_time))}s)"
                        continue

                    try:
                        reg_info = self.get_registration_info(subnet_id)
                        last_api_call[subnet_id] = current_time

                        if reg_info is None:
                            messages[subnet_id] = "Failed to get subnet info"
                            continue

                        reg_infos[subnet_id] = reg_info
                        cost_in_tao = float(reg_info['neuron_cost']) / 1e9

                        if max_cost > 0 and cost_in_tao > max_cost:
                            subnet_statuses[subnet_id] = f"Cost high ({cost_in_tao:.9f})"
                            continue

                        if reg_info['registration_allowed']:
                            subnet_statuses[subnet_id] = "Starting registration..."
                            live.update(update_table(reg_infos, messages))

                            try:
                                registrations = await self.start_registration(
                                    wallet_configs=wallet_configs,
                                    subnet_id=subnet_id,
                                    start_block=0,
                                    prep_time=self.config.get('registration.default_prep_time', 12)
                                )

                                success = all(reg.status == "Success" for reg in registrations.values())
                                subnet_statuses[subnet_id] = "Success" if success else "Failed"
                                if success:
                                    completed_subnets.add(subnet_id)
                                    messages[subnet_id] = "Registration successful"
                                else:
                                    messages[subnet_id] = "Registration failed"

                            except Exception as e:
                                messages[subnet_id] = f"Error: {str(e)}"

                        else:
                            messages[subnet_id] = "Registration closed"

                    except Exception as e:
                        messages[subnet_id] = f"Error: {str(e)}"

                live.update(update_table(reg_infos, messages))
                await asyncio.sleep(check_interval)

        return {subnet_id: subnet_statuses[subnet_id] for subnet_id in subnet_ids}

class DegenRegistration:
    def __init__(self, registration_manager):
        self.registration_manager = registration_manager
        self.subtensor = registration_manager.subtensor
        self.monitoring = False
        self.target_subnet = None
        self.wallet_configs: List[Dict] = []
        self.active_tasks: Set[asyncio.Task] = set()
        self.status_table = Table(
            title="DEGEN Registration Status",
            show_header=True,
            header_style="bold"
        )
        self._setup_status_table()

    def _setup_status_table(self):
        self.status_table.add_column("Wallet")
        self.status_table.add_column("Hotkey")
        self.status_table.add_column("Subnet")
        self.status_table.add_column("Status")
        self.status_table.add_column("Progress")
        self.status_table.add_column("Time")
        self.status_table.add_column("Error")

    async def _verify_subnet_exists(self, subnet_id: int, attempt: int = 1) -> bool:
        try:
            subnets = self.subtensor.get_subnets()
            console.print(f"[cyan]Attempt {attempt}/5: Found subnets: {subnets}[/cyan]")
            return subnet_id in subnets
        except Exception as e:
            logger.error(f"Error checking subnets: {str(e)}")
            return False

    async def _attempt_registration(self, wallet_config: Dict, subnet_id: int, attempts: int = 2) -> bool:
        coldkey = wallet_config['coldkey']
        hotkey = wallet_config['hotkey']
        
        registration = WalletRegistration(
            coldkey, hotkey, wallet_config['password'],
            wallet_config.get('prep_time', 15)
        )
        registration.subnet_id = subnet_id
        registrations = {f"{coldkey}:{hotkey}": registration}

        for attempt in range(attempts):
            try:
                console.print(f"[cyan]Registration attempt {attempt + 1}/{attempts} for {coldkey}:{hotkey}[/cyan]")
                registration.status = f"Attempt {attempt + 1}"
                await self._update_status_display(registrations)

                if self.registration_manager.check_registration(coldkey, hotkey, subnet_id)[0]:
                    registration.status = "Already registered"
                    registration.complete(True)
                    await self._update_status_display(registrations)
                    return True

                result = await self.registration_manager.start_registration(
                    wallet_configs=[wallet_config],
                    subnet_id=subnet_id,
                    start_block=0,
                    prep_time=abs(wallet_config['prep_time'])
                )

                reg_key = f"{coldkey}:{hotkey}"
                if reg_key in result:
                    reg = result[reg_key]
                    if reg.status == "Success":
                        registration.status = "Success"
                        registration.complete(True)
                        await self._update_status_display(registrations)
                        return True

                await asyncio.sleep(6)

            except Exception as e:
                logger.error(f"Registration attempt {attempt + 1} failed: {str(e)}")
                registration.error = str(e)
                await self._update_status_display(registrations)

        return False

    async def _update_status_display(self, registrations: Dict[str, WalletRegistration]):
        self.status_table.rows = []
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

            self.status_table.add_row(
                reg.coldkey,
                reg.hotkey,
                str(getattr(reg, 'subnet_id', 'N/A')),
                f"[{status_color}]{reg.status}[/{status_color}]",
                f"{reg.progress}%",
                elapsed,
                reg.error or ""
            )
        console.print(self.status_table)

    async def _process_block(self, block_number: int) -> None:
        try:
            block_hash = self.subtensor.substrate.get_block_hash(block_number)
            block = self.subtensor.substrate.get_block(block_hash)
            
            if 'extrinsics' in block:
                for ext in block['extrinsics']:
                    ext_value = ext.value if hasattr(ext, 'value') else ext
                    call = ext_value.get('call', {}) if isinstance(ext_value, dict) else {}
                    
                    if (call.get('call_module') == 'SubtensorModule' and 
                        call.get('call_function') == 'register_network'):
                        console.print(f"\n[bold green]Found network registration! Starting DEGEN process for subnet {self.target_subnet}[/bold green]")
                        
                        for wallet_config in self.wallet_configs:
                            if await self._attempt_registration(wallet_config, self.target_subnet, attempts=2):
                                continue

                            subnet_found = False
                            for i in range(5):
                                if await self._verify_subnet_exists(self.target_subnet, i + 1):
                                    subnet_found = True
                                    break
                                await asyncio.sleep(5)

                            if subnet_found:
                                console.print(f"[green]Subnet {self.target_subnet} found! Making final registration attempts[/green]")
                                await self._attempt_registration(wallet_config, self.target_subnet, attempts=2)
                            else:
                                console.print(f"[yellow]Subnet {self.target_subnet} not found after 5 attempts. Returning to monitoring...[/yellow]")

                        return
                        
        except Exception as e:
            logger.error(f"Error processing block {block_number}: {str(e)}")

    async def run(self, wallet_configs: List[Dict], target_subnet: int) -> None:
        self.wallet_configs = wallet_configs
        self.target_subnet = target_subnet
        self.monitoring = True
        consecutive_errors = 0
        last_block = None
            
        initial_registrations = {}
        for config in wallet_configs:
            reg = WalletRegistration(
                config['coldkey'],
                config['hotkey'],
                config['password'],
                config.get('prep_time', 0)
            )
            reg.subnet_id = target_subnet
            reg.status = "Waiting for network registration..."
            key = f"{config['coldkey']}:{config['hotkey']}"
            initial_registrations[key] = reg
                
        console.print(f"[cyan]Starting monitoring for subnet {target_subnet}[/cyan]")
        console.print("[green]Waiting for network registration...[/green]")
        
        with Live(self.status_table, refresh_per_second=2) as live:
            await self._update_status_display(initial_registrations)
            live.refresh()

            while self.monitoring:
                try:
                    current_block = await self.registration_manager._get_current_block_with_retry()
                    
                    if current_block != last_block:
                        await self._process_block(current_block)
                        last_block = current_block
                        consecutive_errors = 0
                        
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    consecutive_errors += 1
                    logger.error(f"Error in main loop: {str(e)}")
                    
                    if consecutive_errors > 5:
                        logger.error("Too many consecutive errors, waiting longer...")
                        await asyncio.sleep(1)
                        consecutive_errors = 0
                    else:
                        await asyncio.sleep(1)

    def stop(self) -> None:
        self.monitoring = False
        for task in self.active_tasks:
            task.cancel()
