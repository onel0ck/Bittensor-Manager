from src.core.wallet_manager import WalletManager
from src.core.stats_manager import StatsManager
from src.core.registration import RegistrationManager
from src.core.transfer_manager import TransferManager
from src.core.subnet_scanner import SubnetScanner
from src.utils.config import Config
from src.core.wallet_utils import WalletUtils
from src.ui.menus import RegistrationMenu, WalletCreationMenu, StatsMenu, BalanceMenu, TransferMenu, AutoBuyerMenu
from src.ui.subnet_scanner_menu import SubnetScannerMenu
from rich.console import Console
from rich.prompt import IntPrompt, Prompt
from rich.panel import Panel
import signal
import sys
import asyncio

console = Console()

def signal_handler(sig, frame):
    console.print("\n[yellow]Exiting gracefully...[/yellow]")
    sys.exit(0)

class BitensorManager:
    def __init__(self):
        self.config = Config()
        self.wallet_manager = WalletManager(self.config)
        self.stats_manager = StatsManager(self.config)
        self.registration_manager = RegistrationManager(self.config)
        self.wallet_utils = WalletUtils()
        self.transfer_manager = TransferManager(self.config)
        self.subnet_scanner = SubnetScanner(self.config)

    def register_menu(self):
        menu = RegistrationMenu(self.registration_manager, self.config)
        menu.show()

    def create_wallet_menu(self):
        menu = WalletCreationMenu(self.wallet_manager, self.config)
        menu.show()

    def check_balance_menu(self):
        menu = BalanceMenu(self.stats_manager, self.wallet_utils)
        menu.show()

    async def show_stats_menu(self):
        menu = StatsMenu(self.stats_manager, self.wallet_utils)
        await menu.show()

    def transfer_menu(self):
        menu = TransferMenu(self.transfer_manager, self.wallet_utils, self.config)
        menu.show()
        
    async def auto_buyer_menu(self):
        menu = AutoBuyerMenu(self.transfer_manager, self.wallet_utils, self.config)
        await menu.show()

    def main_menu(self):
        while True:
            console.clear()
            console.print("[bold blue]Bittensor Manager[/bold blue]\n")
            console.print(Panel.fit(
                "1. Create Coldkey/Hotkey\n"
                "2. Show Wallet Stats\n"
                "3. Check TAO Balance/Addresses\n"
                "4. Register Wallets\n"
                "5. Transfer/Unstake Alpha TAO(DTAO)\n"
                "6. Subnet Scanner\n"
                "7. Auto Token Buyer\n"
                "8. Exit"
            ))

            choice = IntPrompt.ask("Select option", default=8)

            if choice == 1:
                self.create_wallet_menu()
            elif choice == 2:
                asyncio.run(self.show_stats_menu())
            elif choice == 3:
                self.check_balance_menu()
            elif choice == 4:
                self.register_menu()
            elif choice == 5:
                self.transfer_menu()
            elif choice == 6:
                asyncio.run(self.subnet_scanner_menu())
            elif choice == 7:
                asyncio.run(self.auto_buyer_menu())
            elif choice == 8:
                console.print("[yellow]Goodbye![/yellow]")
                break

            if choice != 8:
                Prompt.ask("\nPress Enter to continue")
                
    async def subnet_scanner_menu(self):
        menu = SubnetScannerMenu(self.subnet_scanner, self.config)
        await menu.show()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    manager = BitensorManager()
    manager.main_menu()
    
