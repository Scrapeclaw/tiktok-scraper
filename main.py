#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TikTok Profile Scraper - Main Entry Point
ClawHub Skill for OpenClaw Agent Integration

Commands:
    login     - Log in to TikTok (saves session for better scraping)
    logout    - Clear saved TikTok session
    status    - Show current session status
    discover  - Discover TikTok profiles via Google Search API
    scrape    - Scrape TikTok profiles using browser automation
    list      - List available queue files
    export    - Export scraped data to JSON/CSV
"""

import sys
import json
import asyncio
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        prog='tiktok-scraper',
        description='TikTok Profile Discovery and Scraping Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s login                                          # Log in to TikTok (recommended)
  %(prog)s scrape --username charlidamelio                # Scrape with saved session
  %(prog)s scrape --username charlidamelio --no-login     # Scrape anonymously
  %(prog)s discover --location "New York" --category "dance"
  %(prog)s scrape data/queue/NewYork_dance_20260302.json
  %(prog)s list
  %(prog)s export --format json
  %(prog)s logout                                         # Clear saved session
  %(prog)s status                                         # Check session status
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Login command
    subparsers.add_parser('login', help='Log in to TikTok (opens browser for manual login)')
    
    # Logout command
    subparsers.add_parser('logout', help='Clear saved TikTok session')
    
    # Status command
    subparsers.add_parser('status', help='Show current session status')
    
    # Discover command
    discover_parser = subparsers.add_parser('discover', help='Discover TikTok profiles via Google API')
    discover_parser.add_argument('--location', '-l', type=str, help='Location/city to search')
    discover_parser.add_argument('--category', '-c', type=str, help='Category to search')
    discover_parser.add_argument('--count', '-n', type=int, default=10, help='Number of profiles to discover')
    discover_parser.add_argument('--batch', '-b', action='store_true', help='Batch mode for multiple locations')
    discover_parser.add_argument('--output', '-o', type=str, choices=['json', 'text'], default='text')
    
    # Scrape command
    scrape_parser = subparsers.add_parser('scrape', help='Scrape TikTok profiles')
    scrape_parser.add_argument('queue_file', nargs='?', help='Queue file to scrape')
    scrape_parser.add_argument('--username', '-u', type=str, help='Single username to scrape')
    scrape_parser.add_argument('--resume', '-r', action='store_true', default=True, help='Resume from checkpoint')
    scrape_parser.add_argument('--headless', action='store_true', help='Run browser in headless mode')
    scrape_parser.add_argument('--no-login', action='store_true', help='Skip saved session, scrape anonymously')
    scrape_parser.add_argument('--output', '-o', type=str, choices=['json', 'text'], default='text')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List available queue files')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export scraped data')
    export_parser.add_argument('--format', '-f', type=str, choices=['json', 'csv', 'both'], default='both')
    
    args = parser.parse_args()
    
    if args.command == 'login':
        from scraper import login_interactive
        asyncio.run(login_interactive())
    
    elif args.command == 'logout':
        from scraper import logout
        logout()
    
    elif args.command == 'status':
        from scraper import session_status
        session_status()
    
    elif args.command == 'discover':
        from discovery import discover_command, interactive_discovery, batch_discovery
        
        if args.batch:
            batch_discovery()
        elif args.location and args.category:
            result = discover_command(
                args.location, 
                args.category, 
                args.count, 
                args.output == 'json'
            )
            if args.output == 'json' and result:
                print(json.dumps(result, indent=2))
        else:
            interactive_discovery()
    
    elif args.command == 'scrape':
        from scraper import scrape_from_queue, scrape_single, list_queue_files
        use_session = not getattr(args, 'no_login', False)
        
        if args.username:
            result = asyncio.run(scrape_single(args.username, args.output == 'json', use_session=use_session))
            if args.output == 'json' and result:
                print(json.dumps(result, indent=2))
        elif args.queue_file:
            asyncio.run(scrape_from_queue(args.queue_file, args.resume, use_session=use_session))
        else:
            list_queue_files()
            print("\nUsage: python main.py scrape <queue_file>")
    
    elif args.command == 'list':
        from scraper import list_queue_files
        list_queue_files()
    
    elif args.command == 'export':
        from scraper import export_data
        export_data(args.format)
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
