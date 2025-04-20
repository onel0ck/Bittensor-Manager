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
                "1. Scan All Subnets\n"
                "2. Scan Specific Subnet\n"
                "3. Show Subnets with Disabled Weights\n"
                "4. Show Subnets with High Difficulty\n"
                "5. Back to Main Menu"
            ))

            choice = IntPrompt.ask("Select option", default=5)

            if choice == 5:
                return

            if choice == 1:
                console.print("[cyan]Scanning all subnets...[/cyan]")
                try:
                    results = await self.subnet_scanner.analyze_subnets(use_api=True)
                    if results:
                        self.subnet_scanner.display_results(results)
                    else:
                        console.print("[red]No results found.[/red]")
                except Exception as e:
                    console.print(f"[red]Error during subnet scanning: {str(e)}[/red]")
                Prompt.ask("\nPress Enter to continue")
            elif choice == 2:
                await self._scan_specific_subnet()
            elif choice == 3:
                await self._show_disabled_weights_subnets()
            elif choice == 4:
                await self._show_high_difficulty_subnets()
            else:
                console.print("[red]Invalid option![/red]")


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
    
    async def _show_disabled_weights_subnets(self):
        console.print("\n[bold cyan]Scanning for subnets with disabled commit-reveal weights mechanism[/bold cyan]")
        
        use_api = True
        if not self.subnet_scanner.api_key:
            console.print("[red]TAO Stats API key not configured in config.yaml[/red]")
            if Confirm.ask("Continue with Direct Blockchain method instead?"):
                use_api = False
            else:
                return
        
        console.print("[cyan]Fetching subnet data...[/cyan]")
        
        try:
            results = await self.subnet_scanner.analyze_subnets(use_api=use_api)
            if results and 'weights_disabled' in results and results['weights_disabled']:
                console.print(f"\n[bold]Found {len(results['weights_disabled'])} subnets with disabled weights mechanism[/bold]")
                
                sorted_results = sorted(
                    results['weights_disabled'], 
                    key=lambda x: (x.get('active_keys', 0), x.get('active_miners', 0)), 
                    reverse=True
                )
                
                subset_results = {
                    'weights_disabled': sorted_results,
                    'all_subnets': sorted_results
                }
                
                self.subnet_scanner.display_results(subset_results)
                
                active_subnets = sum(1 for subnet in sorted_results if subnet.get('active_miners', 0) > 0)
                subnets_with_high_emission = sum(1 for subnet in sorted_results if subnet.get('emission', 0) > 1000000)
                console.print(f"\n[bold]Analysis of Subnets with Disabled Weights:[/bold]")
                console.print(f"- Active subnets (with miners): {active_subnets}")
                console.print(f"- Subnets with high emission (>1M): {subnets_with_high_emission}")
                console.print(f"- Total disabled weights subnets: {len(sorted_results)}")
                
                console.print("\n[bold green]" + "=" * 80 + "[/bold green]")
                console.print("[bold green]NEXT STEP: Check registration activity?[/bold green]")
                console.print("[bold green]" + "=" * 80 + "[/bold green]")
                
                if Confirm.ask("\nCheck registration activity for popular disabled-weights subnets?", default=True):
                    console.print("[bold cyan]Starting registration activity check...[/bold cyan]")
                    
                    interesting_subnets = [s for s in sorted_results if s.get('registration_allowed', False) and s.get('active_keys', 0) >= 10]
                    subnets_to_check = interesting_subnets[:5]
                    
                    if not subnets_to_check:
                        console.print("[yellow]No suitable subnets found for registration activity check.[/yellow]")
                    else:
                        subnet_ids = [s['netuid'] for s in subnets_to_check]
                        console.print(f"[cyan]Will check {len(subnets_to_check)} subnets: {subnet_ids}[/cyan]")
                        console.print(f"[cyan]This will take approximately {len(subnets_to_check) * 12} seconds due to API rate limits[/cyan]")
                        console.print(f"[yellow]Press Ctrl+C to abort if it takes too long...[/yellow]")
                        
                        try:
                            activity_results = self.subnet_scanner.check_registration_activity(sorted_results)
                            
                            if activity_results:
                                self.subnet_scanner.display_registration_activity(activity_results)
                                
                                console.print("\n[bold green]" + "=" * 80 + "[/bold green]")
                                console.print("[bold green]NEXT STEP: Check all remaining subnets?[/bold green]")
                                console.print("[bold green]" + "=" * 80 + "[/bold green]")
                                
                                if Confirm.ask("\nWould you like to see all remaining subnets in the network?", default=True):
                                    console.print("[cyan]Fetching information about all subnets...[/cyan]")
                                    
                                    all_subnets_results = await self.subnet_scanner.analyze_subnets(use_api=use_api)
                                    
                                    if all_subnets_results and 'all_subnets' in all_subnets_results:
                                        disabled_weights_netuid = [s['netuid'] for s in sorted_results]
                                        

                                        remaining_subnets = [
                                            subnet for subnet in all_subnets_results['all_subnets'] 
                                            if subnet['netuid'] not in disabled_weights_netuid
                                        ]
                                        
                                        if remaining_subnets:
                                            console.print(f"\n[bold]Found {len(remaining_subnets)} other subnets in the network[/bold]")
                                            
                                            remaining_results = {
                                                'all_subnets': remaining_subnets
                                            }
                                            
                                            self.subnet_scanner.display_results(remaining_results)
                                            
                                            console.print("\n[bold green]" + "=" * 80 + "[/bold green]")
                                            console.print("[bold green]NEXT STEP: Check registration activity for remaining subnets?[/bold green]")
                                            console.print("[bold green]" + "=" * 80 + "[/bold green]")
                                            
                                            if Confirm.ask("\nWould you like to check registration activity for remaining subnets?", default=True):
                                                console.print("\n[bold]Select method to check registration activity:[/bold]")
                                                console.print("1. Auto-select most active subnets")
                                                console.print("2. Specify subnet IDs manually")
                                                console.print("3. Check ALL remaining subnets (will take a long time)")
                                                
                                                method = IntPrompt.ask("Select option", default=1)
                                                
                                                selected_to_check = []
                                                
                                                if method == 1:
                                                    interesting_remaining = [
                                                        s for s in remaining_subnets 
                                                        if s.get('registration_allowed', False) and s.get('active_keys', 0) >= 10
                                                    ]
                                                    
                                                    if not interesting_remaining:
                                                        console.print("[yellow]No suitable subnets found for registration activity check.[/yellow]")
                                                        return
                                                    
                                                    interesting_remaining.sort(
                                                        key=lambda x: (x.get('active_keys', 0), x.get('active_miners', 0)), 
                                                        reverse=True
                                                    )
                                                    
                                                    max_subnets = min(20, len(interesting_remaining))
                                                    num_to_check = IntPrompt.ask(
                                                        f"How many subnets to check (max {max_subnets})?", 
                                                        default=10
                                                    )
                                                    num_to_check = min(num_to_check, max_subnets)
                                                    
                                                    selected_to_check = interesting_remaining[:num_to_check]
                                                
                                                elif method == 2:
                                                    sorted_by_id = sorted(remaining_subnets, key=lambda x: x['netuid'])
                                                    
                                                    console.print("\n[bold]Available subnets:[/bold]")
                                                    for i, subnet in enumerate(sorted_by_id):
                                                        netuid = subnet['netuid']
                                                        active = subnet.get('active_keys', 0)
                                                        total = subnet.get('max_neurons', 'Unknown')
                                                        miners = subnet.get('active_miners', 0)
                                                        console.print(f"{netuid}: Active: {active}/{total}, Miners: {miners}")
                                                    
                                                    subnet_ids_input = Prompt.ask("Enter subnet IDs to check (comma-separated, e.g. 1,5,43)")
                                                    try:
                                                        subnet_ids_to_check = [int(x.strip()) for x in subnet_ids_input.split(',') if x.strip()]
                                                        
                                                        for subnet_id in subnet_ids_to_check:
                                                            for subnet in remaining_subnets:
                                                                if subnet['netuid'] == subnet_id:
                                                                    selected_to_check.append(subnet)
                                                                    break
                                                        
                                                        if not selected_to_check:
                                                            console.print("[yellow]No valid subnet IDs provided.[/yellow]")
                                                            return
                                                    except:
                                                        console.print("[red]Invalid subnet IDs format.[/red]")
                                                        return
                                                
                                                elif method == 3:
                                                    if not Confirm.ask(f"This will check ALL {len(remaining_subnets)} remaining subnets and may take a long time. Proceed?", default=False):
                                                        return
                                                    selected_to_check = remaining_subnets
                                                
                                                else:
                                                    console.print("[red]Invalid option selected.[/red]")
                                                    return
                                                
                                                if selected_to_check:
                                                    subnet_ids = [s['netuid'] for s in selected_to_check]
                                                    console.print(f"[cyan]Will check {len(selected_to_check)} subnets: {subnet_ids}[/cyan]")
                                                    console.print(f"[cyan]This will take approximately {len(selected_to_check) * 12} seconds due to API rate limits[/cyan]")
                                                    console.print(f"[yellow]Press Ctrl+C to abort if it takes too long...[/yellow]")
                                                    
                                                    try:
                                                        remaining_activity_results = self.subnet_scanner.check_registration_activity(selected_to_check)
                                                        
                                                        if remaining_activity_results:
                                                            self.subnet_scanner.display_registration_activity(remaining_activity_results)
                                                        else:
                                                            console.print("[yellow]No registration activity data available for remaining subnets.[/yellow]")
                                                    except KeyboardInterrupt:
                                                        console.print("[yellow]Process interrupted by user.[/yellow]")
                                                    except Exception as e:
                                                        console.print(f"[red]Error during registration activity check: {str(e)}[/red]")
                                            else:
                                                console.print("[yellow]Registration activity check for remaining subnets skipped.[/yellow]")
                                        else:
                                            console.print("[yellow]All subnets in the network have been already displayed.[/yellow]")
                                    else:
                                        console.print("[yellow]Failed to retrieve information about all subnets.[/yellow]")
                            else:
                                console.print("[yellow]No registration activity data available.[/yellow]")
                        except KeyboardInterrupt:
                            console.print("[yellow]Process interrupted by user.[/yellow]")
                        except Exception as e:
                            console.print(f"[red]Error during registration activity check: {str(e)}[/red]")
                else:
                    console.print("[yellow]Registration activity check skipped.[/yellow]")
            else:
                console.print("[yellow]No subnets with disabled weights mechanism found.[/yellow]")
        except Exception as e:
            console.print(f"[red]Error during subnet scanning: {str(e)}[/red]")
        
        Prompt.ask("\nPress Enter to continue")
    
    async def _show_high_difficulty_subnets(self):
        console.print("\n[bold cyan]Scanning for subnets with high registration difficulty[/bold cyan]")
        
        console.print("\n[bold]Difficulty Detection Mode:[/bold]")
        console.print("1. Normalized difficulty (0.0-1.0)")
        console.print("2. Both normalized and absolute values")
        difficulty_mode = IntPrompt.ask("Select mode", default=2)
        
        difficulty_threshold = 0.5
        if difficulty_mode == 1:
            difficulty_threshold = Prompt.ask("Enter normalized difficulty threshold (0.0-1.0)", default="0.5")
            try:
                difficulty_threshold = float(difficulty_threshold)
                if not 0 <= difficulty_threshold <= 1:
                    console.print("[red]Threshold must be between 0.0 and 1.0. Using default of 0.5.[/red]")
                    difficulty_threshold = 0.5
            except ValueError:
                console.print("[red]Invalid threshold. Using default of 0.5.[/red]")
                difficulty_threshold = 0.5
        
        use_api = True
        if not self.subnet_scanner.api_key:
            console.print("[red]TAO Stats API key not configured in config.yaml[/red]")
            if Confirm.ask("Continue with Direct Blockchain method instead?"):
                use_api = False
            else:
                return
        
        with Status("[bold cyan]Scanning subnets...", spinner="dots") as status:
            try:
                results = await self.subnet_scanner.analyze_subnets(use_api=use_api)
                
                high_difficulty_subnets = []
                for subnet in results['all_subnets']:
                    is_high_difficulty = False
                    if 'normalized_difficulty' in subnet and subnet['normalized_difficulty'] >= difficulty_threshold:
                        is_high_difficulty = True
                    elif difficulty_mode == 2 and 'difficulty' in subnet:
                        if subnet['difficulty'] == 1.0:
                            is_high_difficulty = True
                        elif subnet['difficulty'] > 0.1 and 'max_difficulty' in subnet and subnet['max_difficulty'] > 0:
                            is_high_difficulty = True
                    
                    if is_high_difficulty:
                        high_difficulty_subnets.append(subnet)
                
                sorted_results = sorted(
                    high_difficulty_subnets, 
                    key=lambda x: (x.get('normalized_difficulty', 0), x.get('difficulty', 0)), 
                    reverse=True
                )
                
                if sorted_results:
                    console.print(f"\n[bold]Found {len(sorted_results)} subnets with high difficulty (threshold: {difficulty_threshold})[/bold]")
                    
                    subset_results = {
                        'high_difficulty': sorted_results,
                        'all_subnets': sorted_results
                    }
                    
                    self.subnet_scanner.display_results(subset_results)
                    
                    max_difficulty = max((subnet.get('normalized_difficulty', 0) for subnet in sorted_results), default=0)
                    open_reg = sum(1 for subnet in sorted_results if subnet.get('registration_allowed', False))
                    closed_reg = len(sorted_results) - open_reg
                    
                    console.print(f"\n[bold]Analysis of High Difficulty Subnets:[/bold]")
                    console.print(f"- Subnets with open registration: {open_reg}")
                    console.print(f"- Subnets with closed registration: {closed_reg}")
                    console.print(f"- Maximum difficulty found: {max_difficulty:.4f}")
                    
                else:
                    console.print(f"[yellow]No subnets with difficulty ? {difficulty_threshold} found.[/yellow]")
            except Exception as e:
                console.print(f"[red]Error during subnet scanning: {str(e)}[/red]")
        
        Prompt.ask("\nPress Enter to continue")
        
