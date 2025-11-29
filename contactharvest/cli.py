import argparse
import sys
import os
import asyncio
import json
import csv
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

# Add parent directory to path when run as script
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from contactharvest import Crawler

console = Console()

def save_results(results, output_file):
    """Save results to a file (JSON or CSV)."""
    if not results:
        return

    ext = os.path.splitext(output_file)[1].lower()
    
    if ext == '.json':
        data = [
            {
                "type": item.type,
                "value": item.value,
                "source_url": item.source_url,
                "metadata": item.metadata
            }
            for item in results
        ]
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        console.print(f"[green]Results saved to {output_file}[/green]")
        
    elif ext == '.csv':
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Type", "Value", "Source URL", "Metadata"])
            for item in results:
                writer.writerow([item.type, item.value, item.source_url, str(item.metadata) if item.metadata else ""])
        console.print(f"[green]Results saved to {output_file}[/green]")
    else:
        console.print(f"[red]Unsupported output format: {ext}. Use .json or .csv[/red]")

async def main():
    parser = argparse.ArgumentParser(description="Extract emails and phone numbers from a website.")
    parser.add_argument("url", help="URL of the website to analyze")
    parser.add_argument("--max-pages", "-mp", type=int, default=50, help="Maximum number of pages to crawl (default: 50)")
    parser.add_argument("--timeout", "-t", type=int, default=30, help="Request timeout in seconds (default: 30)")
    parser.add_argument("--delay", "-d", type=float, default=1.0, help="Delay between requests in seconds (default: 1.0)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print every page being searched")
    parser.add_argument("--verify_ssl", "-vssl", action="store_true", help="Whether to verify SSL certificates (default: True)")
    parser.add_argument("--recursive", "-r", action="store_true", help="Follow every internal link (default: only crawl the final page after redirects)")
    parser.add_argument("--proxy", "-p", help="Proxy URL (e.g., http://user:pass@host:port)")
    parser.add_argument("--output", "-o", help="Output file path (.json or .csv)")
    args = parser.parse_args()

    # Create crawler instance
    crawler = Crawler(
        url=args.url,
        max_pages=args.max_pages,
        timeout=args.timeout,
        delay=args.delay,
        verbose=args.verbose,
        recursive=args.recursive,
        verify_ssl=args.verify_ssl,
        proxy=args.proxy
    )
    
    try:
        async with crawler:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
            ) as progress:
                task = progress.add_task(f"Fetching {args.url}...", total=None)
                await crawler.fetch()
                progress.update(task, description=f"Crawling {crawler.final_url}...")
                
                # We need to run extract_emails which runs the main loop
                # To show progress, we might need to hook into the crawler, but for now let's just run it
                await crawler.extract_emails()
            
            results = crawler.get_results()
            
            if results:
                console.print(f"\n[bold green]Found {len(results)} items across {len(crawler.visited_urls)} pages[/bold green]")
                
                # Create a table for results
                table = Table(title="Extraction Results")
                table.add_column("Type", style="cyan")
                table.add_column("Value", style="magenta")
                table.add_column("Source", style="blue")
                
                for item in results:
                    # Don't show metadata in the main table to avoid clutter
                    if item.type != 'metadata':
                        table.add_row(item.type, item.value, item.source_url)
                
                console.print(table)
                
                # Show metadata separately if verbose
                metadata_items = [item for item in results if item.type == 'metadata']
                if metadata_items:
                    console.print("\n[bold]Metadata:[/bold]")
                    for item in metadata_items:
                        console.print(f"[dim]{item.value}[/dim] ({item.source_url})")

                if args.output:
                    save_results(results, args.output)
            else:
                console.print("\n[yellow]No email, phone, or social links found.[/yellow]")
            
    except RuntimeError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
    except KeyboardInterrupt:
        console.print("\n[bold red]Crawling interrupted by user[/bold red]")
    except Exception as e:
        console.print(f"[bold red]Unexpected error:[/bold red] {e}")

def cli():
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())

if __name__ == "__main__":
    cli()
