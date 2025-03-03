import bittensor as bt
import asyncio
import threading
import queue
from rich.prompt import Prompt, IntPrompt
import time
from datetime import datetime, timedelta
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

                    logger.info(f"Connected to custom RPC: {rpc_endpoint}")
                    return True
                except Exception as e:
                    logger.error(f"Failed to connect to {rpc_endpoint}: {e}")
                    try:
                        self.subtensor = bt.subtensor()
                        logger.info("Connected to default endpoint")
                        return True
                    except Exception as e2:
                        logger.error(f"Failed to connect to default endpoint: {e2}")
                        return False
            else:
                self.subtensor = bt.subtensor()
                logger.info("Connected to default endpoint")
                return True
        except Exception as e:
            logger.error(f"Error setting up subtensor network: {e}")
            return False
    def spread_timing_across_hotkeys(self, hotkeys_count, min_timing=-20, max_timing=0):
        min_timing = max(-19, min(0, min_timing))
        max_timing = min(19, max(0, max_timing))
        
        if min_timing > max_timing:
            min_timing, max_timing = max_timing, min_timing
        
        if min_timing >= 0 and max_timing >= 0:
            if min_timing > max_timing:
                min_timing, max_timing = max_timing, min_timing
        elif min_timing <= 0 and max_timing <= 0:
            if abs(min_timing) < abs(max_timing):
                min_timing, max_timing = max_timing, min_timing
        
        total_range = max_timing - min_timing
        
        timing_values = []
        
        if hotkeys_count <= 1:
            middle_value = min_timing + (total_range // 2)
            return [middle_value]
        
        if total_range > 0:
            if hotkeys_count > total_range + 1:
                for i in range(min_timing, max_timing + 1):
                    timing_values.append(i)
                
                remaining = hotkeys_count - len(timing_values)
                cycle_index = 0
                for _ in range(remaining):
                    timing_values.append(timing_values[cycle_index])
                    cycle_index = (cycle_index + 1) % (total_range + 1)
            else:
                step = total_range / (hotkeys_count - 1) if hotkeys_count > 1 else 0
                for i in range(hotkeys_count):
                    value = min_timing + int(i * step)
                    timing_values.append(value)
        else:
            return [min_timing] * hotkeys_count
            
        return timing_values

    async def start_degen_registration(
        self,
        wallet_configs: List[Dict],
        target_subnet: int,
        background_mode: bool = False,
        rpc_endpoint: Optional[str] = None
    ):
        if rpc_endpoint:
            self.subtensor = bt.subtensor(network="finney", chain_endpoint=rpc_endpoint)
        else:
            self.subtensor = bt.subtensor(network="finney")
        
        degen_registration = DegenRegistration(self)
        await degen_registration.run(wallet_configs, target_subnet, background_mode)
            

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

    async def start_professional_registration(
        self, 
        wallet_configs: list, 
        subnet_id: int, 
        rpc_endpoint: str = None,
        retry_on_failure: bool = True,
        max_retry_attempts: int = 3
    ):
        if not self._set_subtensor_network(rpc_endpoint):
            return None

        reg_info = self.get_registration_info(subnet_id)
        if not reg_info:
            console.print("[red]Failed to get registration information![/red]")
            return None

        self._display_registration_info(reg_info)
        self._display_registration_config(wallet_configs, subnet_id, reg_info)
        
        if not Confirm.ask("Proceed with registration?"):
            return None
        
        registration_configs = []
        for cfg in wallet_configs:
            original_prep_time = cfg.get('prep_time', 0)
            
            timing_variants = []
            base_timing = original_prep_time
            
            if base_timing < 0:
                timing_variants = [
                    base_timing,
                    max(-1, base_timing + 2),
                    min(-9, base_timing - 1),
                    -4,
                    -1
                ]
            else:
                timing_variants = [
                    base_timing,
                    max(0, base_timing - 1),
                    min(5, base_timing + 1),
                    0,
                    1
                ]
            
            registration_configs.append({
                'coldkey': cfg['coldkey'],
                'hotkey': cfg['hotkey'],
                'password': cfg['password'],
                'original_prep_time': original_prep_time,
                'prep_time': original_prep_time,
                'timing_variants': timing_variants,
                'current_variant_index': 0,
                'attempts': 0
            })
        
        tasks = []
        for config in registration_configs:
            task = asyncio.create_task(
                self._execute_registration_with_retry(
                    config, 
                    subnet_id, 
                    reg_info['next_adjustment_block'],
                    retry_on_failure,
                    max_retry_attempts
                )
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        return {f"{cfg['coldkey']}:{cfg['hotkey']}": result for cfg, result in zip(registration_configs, results)}

    async def _execute_registration_with_retry(
        self, 
        config, 
        subnet_id, 
        target_block, 
        retry_on_failure=True, 
        max_retry_attempts=3
    ):
        result = None
        attempt = 0
        
        while attempt <= max_retry_attempts:
            if attempt > 0 and config['current_variant_index'] < len(config['timing_variants']) - 1:
                config['current_variant_index'] += 1
                config['prep_time'] = config['timing_variants'][config['current_variant_index']]
                console.print(f"[yellow]Retry attempt {attempt} for {config['coldkey']}:{config['hotkey']} with prep_time={config['prep_time']}[/yellow]")
            
            current_config = {
                'coldkey': config['coldkey'],
                'hotkey': config['hotkey'],
                'password': config['password'],
                'prep_time': config['prep_time']
            }
            
            try:
                registration = await self._run_single_registration(
                    current_config, subnet_id, target_block
                )
                
                if registration.status == "Success":
                    return registration
                    
                if not retry_on_failure:
                    return registration
                    
                error_type = registration.error if registration.error else ""
                
                if "TooManyRegistrationsThisBlock" in error_type:
                    console.print(f"[red]Block is full for {config['coldkey']}:{config['hotkey']}[/red]")
                    return registration
                    
                if "InsufficientBalance" in error_type:
                    console.print(f"[red]Insufficient balance for {config['coldkey']}:{config['hotkey']}[/red]")
                    return registration
                    
                if "SubstrateRequestException" in error_type:
                    console.print(f"[yellow]SubstrateRequestException detected, immediate retry with adjusted timing[/yellow]")
                    attempt += 1
                    continue
                    
                attempt += 1
                await asyncio.sleep(1)
                
            except Exception as e:
                console.print(f"[red]Error during registration: {str(e)}[/red]")
                logger.error(f"Registration error: {str(e)}")
                attempt += 1
                await asyncio.sleep(2)
        
        console.print(f"[red]All retry attempts failed for {config['coldkey']}:{config['hotkey']}[/red]")
        
        if result is None:
            result = WalletRegistration(
                config['coldkey'],
                config['hotkey'],
                config['password'],
                config['prep_time']
            )
            result.complete(False, "All retry attempts failed")
            
        return result

    async def _run_single_registration(self, config, subnet_id, target_block):
        registration = WalletRegistration(
            config['coldkey'],
            config['hotkey'],
            config['password'],
            config['prep_time']
        )
        
        thread = ThreadedRegistration(
            self,
            config,
            subnet_id,
            target_block
        )
        thread.start()
        
        while thread.is_alive():
            await asyncio.sleep(0.5)
        
        if thread.result:
            return thread.result
        else:
            registration.complete(False, "Registration failed with no result")
            return registration

    async def analyze_optimal_timing(self, subnet_id, num_samples=10):
        console.print("[cyan]Analyzing optimal registration timing...[/cyan]")
        
        try:
            reg_info = self.get_registration_info(subnet_id)
            if not reg_info:
                return -4
                
            registration_ratio = reg_info['total_registrations'] / reg_info['max_registrations']
            
            if registration_ratio > 0.9:
                return -8
            elif registration_ratio > 0.7:
                return -6
            elif registration_ratio > 0.5:
                return -4
            else:
                return -2
        
        except Exception as e:
            logger.error(f"Error analyzing optimal timing: {e}")
            return -4

    async def start_auto_registration(
        self,
        wallet_config_dict: Dict,
        subnet_id: int,
        background_mode: bool = False,
        rpc_endpoint: Optional[str] = None,
        max_registration_cost: float = 0
    ):
        if rpc_endpoint:
            subtensor = bt.subtensor(network="finney", chain_endpoint=rpc_endpoint)
        else:
            subtensor = bt.subtensor(network="finney")
        
        def log_or_print(message, level="INFO"):
            if level == "ERROR":
                console.print(f"[red]{message}[/red]")
            elif level == "WARNING":
                console.print(f"[yellow]{message}[/yellow]")
            elif level == "SUCCESS":
                console.print(f"[green]{message}[/green]")
            else:
                console.print(message)
        
        max_reconnection_attempts = 5
        reconnection_attempt = 0
        connection_failures = 0
        
        # Используем параметр wallet_config_dict
        wallet_configs = wallet_config_dict

        while True:
            log_or_print("\nChecking next registration batch...")

            all_complete = True
            for coldkey, cfg in wallet_configs.items():
                if cfg['current_index'] < len(cfg['hotkeys']):
                    all_complete = False
                    break

            if all_complete:
                log_or_print("All registrations completed successfully!", "SUCCESS")
                break

            try:
                reg_info = self.get_registration_info(subnet_id)
                
                if not reg_info:
                    connection_failures += 1
                    if connection_failures >= 3:
                        reconnection_attempt += 1
                        if reconnection_attempt <= max_reconnection_attempts:
                            log_or_print(f"Connection issues detected. Reconnecting ({reconnection_attempt}/{max_reconnection_attempts})...", "WARNING")
                            
                            try:
                                self.subtensor = bt.subtensor()
                                log_or_print("Reconnected to Bittensor network", "SUCCESS")
                                connection_failures = 0
                            except Exception as conn_err:
                                logger.error(f"Reconnection failed: {conn_err}")
                                log_or_print(f"Reconnection failed: {conn_err}", "ERROR")
                        else:
                            log_or_print("Maximum reconnection attempts reached. Please restart the application.", "ERROR")
                            break
                    
                    log_or_print("Failed to get registration information, retrying in 60 seconds...", "WARNING")
                    await asyncio.sleep(60)
                    continue

                cost_in_tao = float(reg_info['neuron_cost']) / 1e9
                if max_registration_cost > 0 and cost_in_tao > max_registration_cost:
                    log_or_print(f"Registration cost ({cost_in_tao:.9f} TAO) exceeds limit ({max_registration_cost} TAO)", "WARNING")
                    await asyncio.sleep(60)
                    continue

                connection_failures = 0
                reconnection_attempt = 0

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
                            log_or_print(f"Successfully registered {reg.coldkey}:{reg.hotkey} with UID {reg.uid}", "SUCCESS")
                            wallet_configs[reg.coldkey]['current_index'] += 1
                        else:
                            log_or_print(f"Failed to register {reg.coldkey}:{reg.hotkey} - {reg.error or 'Unknown error'}", "ERROR")

                    if reg_info['blocks_until_adjustment'] > 0:
                        log_or_print(f"Waiting for next adjustment ({reg_info['seconds_until_adjustment']:.0f}s)...", "INFO")
                        await asyncio.sleep(reg_info['seconds_until_adjustment'])

                except Exception as e:
                    error_msg = str(e)
                    
                    if "SSL" in error_msg or "certificate" in error_msg or "WebSocket" in error_msg:
                        logger.error(f"Network error during registration: {error_msg}")
                        log_or_print(f"Network connection issue detected: {error_msg}", "ERROR")
                        connection_failures += 1
                        
                        if connection_failures >= 3:
                            reconnection_attempt += 1
                            if reconnection_attempt <= max_reconnection_attempts:
                                log_or_print(f"Network issues detected. Reconnecting ({reconnection_attempt}/{max_reconnection_attempts})...", "WARNING")
                                
                                try:
                                    self.subtensor = bt.subtensor()
                                    log_or_print("Reconnected to Bittensor network", "SUCCESS")
                                    connection_failures = 0
                                except Exception as conn_err:
                                    logger.error(f"Reconnection failed: {conn_err}")
                                    log_or_print(f"Reconnection failed: {conn_err}", "ERROR")
                            else:
                                log_or_print("Maximum reconnection attempts reached. Please restart the application.", "ERROR")
                                break
                        
                        log_or_print("Network connection issue detected. Retrying in 30 seconds...", "WARNING")
                    else:
                        log_or_print(f"Registration error: {error_msg}", "ERROR")
                    
                    await asyncio.sleep(30)
                    continue

            except Exception as e:
                error_msg = str(e)
                
                if "SSL" in error_msg or "certificate" in error_msg or "WebSocket" in error_msg:
                    logger.error(f"Connection error: {error_msg}")
                    log_or_print(f"Connection issue detected: {error_msg}", "WARNING")
                else:
                    logger.error(f"Error in auto registration loop: {error_msg}")
                    log_or_print(f"Error: {error_msg}", "ERROR")
                
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

    async def start_registration_monitor(
        self, 
        wallet_configs: list, 
        subnet_id: int, 
        check_interval: int = 60,
        max_cost: float = 0,
        rpc_endpoint: str = None
    ):
    
        if not self._set_subtensor_network(rpc_endpoint):
            console.print("[red]Failed to connect to the network![/red]")
            return None
            
        
        console.print(f"\n[bold cyan]Starting monitor for subnet {subnet_id}[/bold cyan]")
        console.print(f"[cyan]Monitoring {len(wallet_configs)} hotkeys from {len(set(cfg['coldkey'] for cfg in wallet_configs))} wallets[/cyan]")
        console.print(f"[cyan]Check interval: {check_interval} seconds[/cyan]")
        if max_cost > 0:
            console.print(f"[cyan]Maximum registration cost: {max_cost} TAO[/cyan]")
            
        console.print("[yellow]Press Ctrl+C to stop monitoring at any time[/yellow]\n")
        
        start_time = time.time()
        checks_count = 0
        registered_hotkeys = set()
        
        try:
            while True:
                checks_count += 1
                now = time.time()
                elapsed_time = now - start_time
                hours, remainder = divmod(elapsed_time, 3600)
                minutes, seconds = divmod(remainder, 60)
                elapsed_str = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
                
                console.print(f"[bold]Check #{checks_count}[/bold] | Time: {elapsed_str} | Subnet: {subnet_id}", end="\r")
                
                try:
                    try:
                        subnets = self.subtensor.get_subnets()
                        subnet_exists = subnet_id in subnets
                    except Exception as e:
                        logger.error(f"Error checking subnets: {e}")
                        subnet_exists = False
                    
                    if not subnet_exists:
                        console.print(f"Check #{checks_count} | {elapsed_str} | [yellow]Subnet {subnet_id} not found[/yellow]")
                        await asyncio.sleep(check_interval)
                        continue
                    
                    reg_status = "Unknown"
                    reg_cost = 0
                    try:
                        subnet_info = self.get_registration_info(subnet_id)
                        
                        if subnet_info is None:
                            console.print(f"Check #{checks_count} | {elapsed_str} | [yellow]Subnet {subnet_id} found but could not get registration info[/yellow]")
                            await asyncio.sleep(check_interval)
                            continue
                            
                        current_block = subnet_info.get('current_block', 'Unknown')
                        registration_allowed = subnet_info.get('registration_allowed', False)
                        reg_status = "Open" if registration_allowed else "Closed"
                        
                        if 'neuron_cost' in subnet_info:
                            reg_cost = float(subnet_info['neuron_cost']) / 1e9
                        
                        if 'total_registrations' in subnet_info and 'max_registrations' in subnet_info:
                            reg_count = f"{subnet_info['total_registrations']}/{subnet_info['max_registrations']}"
                        else:
                            reg_count = "Unknown"
                        
                        status_color = "green" if registration_allowed else "red"
                        console.print(f"Check #{checks_count} | {elapsed_str} | Block: {current_block} | Registration: [{status_color}]{reg_status}[/{status_color}] | Slots: {reg_count} | Cost: {reg_cost:.9f} TAO")
                        
                    except Exception as e:
                        logger.error(f"Error getting registration info: {e}")
                        console.print(f"Check #{checks_count} | {elapsed_str} | [yellow]Subnet {subnet_id} found but error getting details: {str(e)}[/yellow]")
                        await asyncio.sleep(check_interval)
                        continue
                    
                    if not registration_allowed:
                        await asyncio.sleep(check_interval)
                        continue
                    
                    if max_cost > 0 and reg_cost > max_cost:
                        console.print(f"Check #{checks_count} | {elapsed_str} | [yellow]Registration OPEN but cost ({reg_cost:.9f} TAO) exceeds limit ({max_cost} TAO)[/yellow]")
                        await asyncio.sleep(check_interval)
                        continue
                    
                    console.print(f"\n[bold green]REGISTRATION OPEN for subnet {subnet_id}![/bold green]")
                    console.print(f"[green]Current cost: {reg_cost:.9f} TAO[/green]")
                    console.print(f"[bold cyan]Starting registration for {len(wallet_configs)} hotkeys...[/bold cyan]")
                    
                    pending_configs = []
                    for cfg in wallet_configs:
                        key = f"{cfg['coldkey']}:{cfg['hotkey']}"
                        if key in registered_hotkeys:
                            continue
                            
                        is_registered, uid = self.check_registration(cfg['coldkey'], cfg['hotkey'], subnet_id)
                        if is_registered:
                            registered_hotkeys.add(key)
                            console.print(f"[yellow]Hotkey {cfg['hotkey']} for wallet {cfg['coldkey']} already registered on subnet {subnet_id} with UID {uid}[/yellow]")
                            continue
                            
                        pending_configs.append(cfg)
                    
                    if not pending_configs:
                        console.print("[green]All hotkeys are already registered![/green]")
                        break
                    
                    try:
                        with Progress(
                            SpinnerColumn(),
                            TextColumn("[progress.description]{task.description}"),
                            console=console
                        ) as progress:
                            progress_task = progress.add_task("[cyan]Registering hotkeys...", total=None)
                            
                            results = await self.start_registration(
                                wallet_configs=pending_configs,
                                subnet_id=subnet_id,
                                start_block=0,
                                prep_time=max(abs(cfg.get('prep_time', 0)) for cfg in pending_configs)
                            )
                            
                            progress.update(progress_task, completed=True)
                        
                        successful = 0
                        failed = 0
                        
                        if results:
                            from rich.table import Table
                            result_table = Table(title="Registration Results")
                            result_table.add_column("Wallet")
                            result_table.add_column("Hotkey")
                            result_table.add_column("Status") 
                            result_table.add_column("UID")
                            result_table.add_column("Details")
                            
                            for key, reg in results.items():
                                coldkey, hotkey = key.split(':')
                                if reg.status == "Success":
                                    successful += 1
                                    status_color = "green"
                                    registered_hotkeys.add(key)
                                else:
                                    failed += 1
                                    status_color = "red"
                                    
                                uid = str(reg.uid) if reg.uid is not None else "N/A"
                                details = reg.error if reg.error else ("Success" if reg.status == "Success" else "N/A")
                                
                                result_table.add_row(
                                    coldkey,
                                    hotkey,
                                    f"[{status_color}]{reg.status}[/{status_color}]",
                                    uid,
                                    details
                                )
                            
                            console.print(result_table)
                            console.print(f"[bold]Registration summary:[/bold] {successful} successful, {failed} failed")
                            
                            all_registered = True
                            for cfg in wallet_configs:
                                key = f"{cfg['coldkey']}:{cfg['hotkey']}"
                                if key not in registered_hotkeys:
                                    all_registered = False
                                    break
                                    
                            if all_registered:
                                console.print("[bold green]All hotkeys successfully registered! Monitoring complete.[/bold green]")
                                return
                            
                            console.print(f"[yellow]Continuing monitoring for {len(wallet_configs) - len(registered_hotkeys)} remaining hotkeys...[/yellow]\n")
                                
                    except Exception as e:
                        logger.error(f"Registration error: {e}")
                        console.print(f"[red]Error during registration: {str(e)}[/red]")
                        console.print("[yellow]Continuing monitoring...[/yellow]\n")
                        
                except Exception as e:
                    logger.error(f"Error in registration monitor: {e}")
                    console.print(f"Check #{checks_count} | {elapsed_str} | [red]Error: {str(e)}[/red]")
                    
                await asyncio.sleep(check_interval)
        
        except KeyboardInterrupt:
            console.print("\n[yellow]Registration monitor stopped by user.[/yellow]")
            
            registered_count = len(registered_hotkeys)
            remaining_count = len(wallet_configs) - registered_count
            
            if registered_count > 0:
                console.print(f"[green]Successfully registered: {registered_count} hotkeys[/green]")
                
            if remaining_count > 0:
                console.print(f"[yellow]Remaining unregistered: {remaining_count} hotkeys[/yellow]")

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
        self.status_table = Table(
            title="DEGEN Registration Status",
            show_header=True,
            header_style="bold"
        )
        self.status_table.add_column("Wallet")
        self.status_table.add_column("Hotkey")
        self.status_table.add_column("Subnet")
        self.status_table.add_column("Status")
        self.status_table.add_column("Progress")
        self.status_table.add_column("Time")
        self.status_table.add_column("Error")

    async def _verify_subnet_exists(self, subnet_id: int) -> bool:
        try:
            current_block = self.subtensor.get_current_block()
            console.print(f"[cyan]Connection confirmed at block {current_block}[/cyan]")
            
            subnets = self.subtensor.get_subnets()
            exists = subnet_id in subnets
            
            if exists:
                console.print(f"[green]Found subnet {subnet_id}![/green]")
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"Error checking subnets: {str(e)}")
            return False

    async def _attempt_registration(self, wallet_config: Dict, subnet_id: int, attempt_count: int = 5) -> bool:
        coldkey = wallet_config['coldkey']
        hotkey = wallet_config['hotkey']
        
        for attempt in range(attempt_count):
            try:
                console.print(f"[cyan]Registration attempt {attempt + 1}/{attempt_count} for {coldkey}:{hotkey}[/cyan]")

                result = await self.registration_manager.start_registration(
                    wallet_configs=[wallet_config],
                    subnet_id=subnet_id,
                    start_block=0,
                    prep_time=abs(wallet_config.get('prep_time', 0))
                )

                if result and isinstance(result, dict):
                    reg_key = f"{coldkey}:{hotkey}"
                    if reg_key in result:
                        reg = result[reg_key]
                        if reg.status == "Success":
                            return True

                reg_check = self.registration_manager.check_registration(coldkey, hotkey, subnet_id)
                if reg_check[0]:
                    return True

                await asyncio.sleep(6)

            except Exception as e:
                logger.error(f"Registration attempt {attempt + 1} failed: {str(e)}")
                await asyncio.sleep(6)

        return False

    async def _update_status_display(self, registrations: Dict[str, WalletRegistration]):
        try:
            self.status_table.rows = []
            
            for reg in registrations.values():
                try:
                    elapsed = ""
                    if reg.start_time:
                        current = reg.end_time or time.time()
                        elapsed = f"{current - reg.start_time:.1f}s"

                    status_color = (
                        "green" if reg.status == "Success" or "confirmed" in reg.status.lower()
                        else "yellow" if "attempt" in reg.status.lower() or "registering" in reg.status.lower()
                        else "red" if reg.status == "Failed" or "error" in reg.status.lower()
                        else "blue"
                    )

                    self.status_table.add_row(
                        str(reg.coldkey),
                        str(reg.hotkey),
                        str(getattr(reg, 'subnet_id', 'N/A')),
                        f"[{status_color}]{reg.status}[/{status_color}]",
                        f"{reg.progress}%",
                        str(elapsed),
                        str(reg.error or "")
                    )
                except Exception as e:
                    logger.error(f"Error adding row for registration: {e}")
                    self.status_table.add_row(
                        "Error", "Error", "Error",
                        "[red]Error displaying registration[/red]",
                        "0%", "", str(e)
                    )

            if len(self.status_table.rows) == 0:
                self.status_table.add_row(
                    "No data", "No data", "No data",
                    "Waiting", "0%", "", ""
                )

            console.print(self.status_table)
        except Exception as e:
            logger.error(f"Error updating status display: {e}", exc_info=True)
            error_table = Table(title="Error Displaying Status")
            error_table.add_column("Error")
            error_table.add_row(f"[red]{str(e)}[/red]")
            console.print(error_table)

    async def run(self, wallet_configs: List[Dict], target_subnet: int, background_mode: bool = False) -> None:
        self.wallet_configs = wallet_configs
        self.target_subnet = target_subnet
        self.monitoring = True
        check_interval = 5
        connection_errors = 0
        consecutive_connection_errors = 0
            
        endpoints = [
            None,
            "wss://entrypoint-finney.opentensor.ai:443",
            "ws://entrypoint-finney.opentensor.ai:80"
        ]
        current_endpoint_index = 0

        console.print(f"[cyan]Starting monitoring for subnet {target_subnet}[/cyan]")
        for config in wallet_configs:
            console.print(f"[cyan]Wallet: {config['coldkey']}, Hotkey: {config['hotkey']}[/cyan]")

        consecutive_checks = 0
        total_monitoring_time = 0
        check_start_time = time.time()

        def log_or_print(message, level="INFO"):
            if level == "ERROR":
                console.print(f"[red]{message}[/red]")
            elif level == "WARNING":
                console.print(f"[yellow]{message}[/yellow]")
            elif level == "SUCCESS":
                console.print(f"[green]{message}[/green]")
            else:
                console.print(message)

        while self.monitoring:
            try:
                try:
                    current_block = self.subtensor.get_current_block()
                    log_or_print(f"Connection confirmed at block {current_block}")
                except Exception as block_err:
                    log_or_print(f"Failed to get current block: {block_err}", "ERROR")
                    raise Exception("Connection check failed")
                    
                subnets = self.subtensor.get_subnets()
                exists = self.target_subnet in subnets
                
                if exists:
                    log_or_print(f"FOUND SUBNET {self.target_subnet}! Starting registration attempts", "SUCCESS")
                    
                    for config in self.wallet_configs:
                        try:
                            check_result = self.registration_manager.check_registration(
                                config['coldkey'],
                                config['hotkey'],
                                self.target_subnet
                            )

                            if check_result[0]:
                                log_or_print(f"Wallet {config['coldkey']} with hotkey {config['hotkey']} already registered on subnet {self.target_subnet} with UID {check_result[1]}", "SUCCESS")
                                continue

                            log_or_print(f"Starting registration for wallet {config['coldkey']} with hotkey {config['hotkey']} on subnet {self.target_subnet}", "INFO")

                            success = await self._attempt_registration(
                                wallet_config=config,
                                subnet_id=self.target_subnet,
                                attempt_count=5
                            )

                            if success:
                                log_or_print(f"Successfully registered wallet {config['coldkey']} with hotkey {config['hotkey']} on subnet {self.target_subnet}", "SUCCESS")
                            else:
                                log_or_print(f"Failed to register wallet {config['coldkey']} with hotkey {config['hotkey']} on subnet {self.target_subnet}", "ERROR")
                        except Exception as e:
                            log_or_print(f"Error processing wallet {config['coldkey']}:{config['hotkey']}: {str(e)}", "ERROR")
                            continue

                    self.monitoring = False
                    break
                else:
                    consecutive_checks += 1
                    consecutive_connection_errors = 0
                    
                    current_time = time.time()
                    elapsed_time = current_time - check_start_time
                    total_monitoring_time += elapsed_time
                    check_start_time = current_time
                    
                    if consecutive_checks % 20 == 0:
                        hours = int(total_monitoring_time // 3600)
                        minutes = int((total_monitoring_time % 3600) // 60)
                        seconds = int(total_monitoring_time % 60)
                        
                        log_or_print(f"Monitoring for {hours:02d}:{minutes:02d}:{seconds:02d} - Subnet {target_subnet} not found yet. Made {consecutive_checks} checks so far.", "WARNING")

                log_or_print(f"Waiting {check_interval} seconds before next check...")
                await asyncio.sleep(check_interval)

            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error in monitoring loop: {error_msg}")
                log_or_print(f"Error in monitoring loop: {error_msg}", "ERROR")
                connection_errors += 1
                consecutive_connection_errors += 1
                
                if consecutive_connection_errors >= 3:
                    current_endpoint_index = (current_endpoint_index + 1) % len(endpoints)
                    endpoint = endpoints[current_endpoint_index]
                    
                    log_or_print(f"Connection issues detected. Switching to another endpoint...", "WARNING")
                    
                    try:
                        if endpoint is None:
                            self.subtensor = bt.subtensor()
                            self.registration_manager.subtensor = self.subtensor
                            log_or_print("Switched to default endpoint", "INFO")
                        else:
                            self.subtensor = bt.subtensor(network=endpoint)
                            self.registration_manager.subtensor = self.subtensor
                            log_or_print(f"Switched to {endpoint}", "INFO")
                        
                        consecutive_connection_errors = 0
                    except Exception as conn_err:
                        logger.error(f"Failed to switch endpoint: {conn_err}")
                        log_or_print(f"Failed to switch to {endpoint or 'default endpoint'}", "ERROR")
                    
                    check_interval = min(check_interval * 2, 60)
                    log_or_print(f"Increased check interval to {check_interval} seconds", "WARNING")
                
                await asyncio.sleep(check_interval)

    def stop(self) -> None:
        self.monitoring = False
        for task in self.active_tasks:
            task.cancel()
