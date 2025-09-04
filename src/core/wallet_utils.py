import os
import bittensor as bt
from rich.console import Console
from rich.prompt import Prompt
from typing import Tuple, List, Dict
from ..utils.config import Config

console = Console()

class WalletUtils:
    def __init__(self):
        self.config = Config()
        self.default_password = self.config.get('wallet.default_password', None)

    def _get_wallet_password(self, wallet: str) -> str:
        if self.default_password:
            password = Prompt.ask(
                f"Enter password for {wallet} (press Enter to use default: {self.default_password})", 
                password=True,
                show_default=False
            )
            return password if password else self.default_password
        else:
            return Prompt.ask(f"Enter password for {wallet}", password=True)

    def _get_wallet_hotkeys_input(self, wallet: str, single_choice: bool = False) -> tuple[list, str]:
        hotkeys_path = os.path.expanduser(f"~/.bittensor/wallets/{wallet}/hotkeys")
        if not os.path.exists(hotkeys_path):
            console.print(f"[red]No hotkeys found for wallet {wallet}![/red]")
            return [], ""

        hotkeys = [d for d in os.listdir(hotkeys_path)]
        if not hotkeys:
            console.print(f"[red]No hotkeys found for wallet {wallet}![/red]")
            return [], ""

        console.print(f"\nHotkeys for wallet {wallet}:")
        for i, hotkey in enumerate(hotkeys, 1):
            console.print(f"{i}. {hotkey}")

        try:
            if len(hotkeys) == 1:
                hotkey_selection = "1"
            else:
                if single_choice:
                    console.print("\nSelect one hotkey (enter the number)")
                else:
                    console.print("\nSelect hotkeys (comma-separated numbers, e.g. 1,2,3,4)")
                hotkey_selection = Prompt.ask("Selection").strip()

            if single_choice:
                try:
                    index = int(hotkey_selection) - 1
                    if 0 <= index < len(hotkeys):
                        selected_hotkeys = [hotkeys[index]]
                    else:
                        console.print(f"[red]Invalid hotkey number for {wallet}![/red]")
                        return [], ""
                except ValueError:
                    console.print(f"[red]Invalid selection for {wallet}![/red]")
                    return [], ""
            else:
                selected_indices = [int(i.strip()) - 1 for i in hotkey_selection.split(',')]
                selected_hotkeys = [hotkeys[i] for i in selected_indices if 0 <= i < len(hotkeys)]

            if not selected_hotkeys:
                console.print(f"[red]No valid hotkeys selected for {wallet}![/red]")
                return [], ""

            password = self._get_wallet_password(wallet)
            return selected_hotkeys, password

        except ValueError:
            console.print(f"[red]Invalid selection for {wallet}![/red]")
            return [], ""

    @staticmethod
    def get_available_wallets() -> List[str]:
        wallet_path = os.path.expanduser("~/.bittensor/wallets")
        if not os.path.exists(wallet_path):
            return []

        return [d for d in os.listdir(wallet_path) if os.path.isdir(os.path.join(wallet_path, d))]

    @staticmethod
    def get_wallet_hotkeys(wallet: str) -> list:
        hotkeys_path = os.path.expanduser(f"~/.bittensor/wallets/{wallet}/hotkeys")
        return [d for d in os.listdir(hotkeys_path)] if os.path.exists(hotkeys_path) else []

    @staticmethod
    def parse_wallet_selection_by_names(selection: str, wallets: List[str]) -> List[str]:
        from rich.console import Console
        console = Console()
        
        if selection.strip().lower() == 'all':
            return wallets
        
        selected_names = [name.strip() for name in selection.split(',')]
        
        valid_wallets = []
        invalid_wallets = []
        
        for name in selected_names:
            if name in wallets:
                valid_wallets.append(name)
            else:
                invalid_wallets.append(name)
        
        if invalid_wallets:
            console.print(f"[yellow]Warning: Invalid wallet names: {', '.join(invalid_wallets)}[/yellow]")
        
        return valid_wallets
