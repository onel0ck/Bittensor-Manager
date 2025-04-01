from rich.console import Console
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.panel import Panel
from rich.status import Status
import asyncio
from ..core.subnet_scanner import SubnetScanner

console = Console()

class SubnetScannerMenu:
    def __init__(self, subnet_scanner, config):
        self.subnet_scanner = subnet_scanner
        self.config = config

    async def show(self):
        while True:
            console.print("\n[bold]Subnet Scanner Menu[/bold]")
            console.print(Panel.fit(
                "1. Scan All Subnets (API Method)\n"
                "2. Scan All Subnets (Direct Method)\n"
                "3. Scan Specific Subnet\n"
                "4. Back to Main Menu"
            ))

            choice = IntPrompt.ask("Select option", default=4)

            if choice == 4:
                return

            if choice == 1:
                await self._scan_all_subnets(use_api=True)
            elif choice == 2:
                await self._scan_all_subnets(use_api=False)
            elif choice == 3:
                await self._scan_specific_subnet()
            else:
                console.print("[red]Invalid option![/red]")

    async def _scan_all_subnets(self, use_api=True):
        method = "API" if use_api else "Direct Blockchain"
        console.print(f"\n[bold cyan]Scanning all subnets using {method} method[/bold cyan]")
        
        if use_api and not self.subnet_scanner.api_key:
            console.print("[red]TAO Stats API key not configured in config.yaml[/red]")
            if Confirm.ask("Continue with Direct Blockchain method instead?"):
                use_api = False
            else:
                return
        
        with Status("[bold cyan]Scanning subnets...", spinner="dots") as status:
            try:
                results = await self.subnet_scanner.analyze_subnets(use_api=use_api)
                if results:
                    self.subnet_scanner.display_results(results)
                else:
                    console.print("[red]No results found.[/red]")
            except Exception as e:
                console.print(f"[red]Error during subnet scanning: {str(e)}[/red]")
        
        Prompt.ask("\nPress Enter to continue")

    async def _scan_specific_subnet(self):
        console.print("\n[bold]Scan Specific Subnet[/bold]")
        
        try:
            subnet_id = IntPrompt.ask("Enter subnet ID")
            use_api = Confirm.ask("Use API method?", default=True)
            
            if use_api and not self.subnet_scanner.api_key:
                console.print("[red]TAO Stats API key not configured in config.yaml[/red]")
                if Confirm.ask("Continue with Direct Blockchain method instead?"):
                    use_api = False
                else:
                    return
            
            with Status(f"[bold cyan]Scanning subnet {subnet_id}...", spinner="dots") as status:
                if use_api:
                    all_subnet_info = self.subnet_scanner.get_all_subnet_info_api()
                    subnet_info = all_subnet_info.get(subnet_id)
                    if not subnet_info:
                        console.print(f"[yellow]Subnet {subnet_id} not found in API data, trying direct query...[/yellow]")
                        subnet_info = self.subnet_scanner.get_subnet_info_direct(subnet_id, verbose=True)
                else:
                    subnet_info = self.subnet_scanner.get_subnet_info_direct(subnet_id, verbose=True)
                
                if subnet_info:
                    if not self.subnet_scanner.tao_price:
                        self.subnet_scanner.get_tao_price()
                    
                    self.subnet_scanner.display_subnet_summary(subnet_info)
                else:
                    console.print(f"[red]Could not get information for subnet {subnet_id}[/red]")
        except Exception as e:
            console.print(f"[red]Error scanning subnet {subnet_id}: {str(e)}[/red]")
        
        Prompt.ask("\nPress Enter to continue")
        
