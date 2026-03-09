#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TikTok Scraper with Playwright Browser Automation
Handles profile extraction and anti-bot detection
"""

import asyncio
import json
import os
import sys
import logging
import time
import csv
import re
from typing import List, Dict, Optional
from pathlib import Path
from playwright.async_api import async_playwright, Page, Browser
from datetime import datetime
import random
from dotenv import load_dotenv
import aiohttp
import hashlib
from PIL import Image
import io

# Set UTF-8 encoding for stdout
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Base directory for the skill
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / 'data'
OUTPUT_DIR = DATA_DIR / 'output'
QUEUE_DIR = DATA_DIR / 'queue'
THUMBNAILS_DIR = BASE_DIR / 'thumbnails'
CONFIG_PATH = BASE_DIR / 'config' / 'scraper_config.json'
SESSION_PATH = DATA_DIR / 'tiktok_session.json'


class ProfileSkippedException(Exception):
    """Exception raised when a profile should be skipped"""
    pass


class ProfileNotFoundException(Exception):
    """Exception raised when a profile doesn't exist"""
    pass


class RateLimitException(Exception):
    """Exception raised when TikTok rate limits the request"""
    pass


class DailyLimitException(Exception):
    """Exception raised when TikTok daily limit is reached"""
    pass


class TikTokScraper:
    """TikTok scraper using Playwright for browser automation"""

    def __init__(self, config_path: Path = None):
        self.config = self._load_config(config_path or CONFIG_PATH)
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None

        # Setup directories
        self.thumbnails_dir = THUMBNAILS_DIR
        self.output_dir = OUTPUT_DIR
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize anti-detection
        from anti_detection import AntiDetectionManager
        self.anti_detection_mgr = AntiDetectionManager(DATA_DIR)

        # Initialize proxy manager
        from proxy_manager import ProxyManager
        self.proxy_manager = ProxyManager.from_config(config_path or CONFIG_PATH)
        if not self.proxy_manager.enabled:
            self.proxy_manager = ProxyManager.from_env()
        if self.proxy_manager.enabled:
            logger.info(f"Proxy enabled: {self.proxy_manager.info()}")

    def _load_config(self, config_path: Path) -> Dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load config: {e}. Using defaults.")
            return {
                'scraper': {
                    'headless': False,
                    'min_followers': 1000,
                    'download_thumbnails': True,
                    'max_thumbnails': 6
                }
            }

    async def start_browser(self, headless: bool = None, use_session: bool = True):
        """Start Playwright browser with anti-detection"""
        if headless is None:
            headless = self.config.get('scraper', {}).get('headless', False)
        
        self._headless = headless
        self._use_session = use_session
        logger.info("Starting browser with anti-detection...")
        from anti_detection import BrowserFingerprint
        
        self.playwright = await async_playwright().start()
        self._fingerprint_mgr = BrowserFingerprint(DATA_DIR)

        launch_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-setuid-sandbox',
        ]

        self.browser = await self.playwright.chromium.launch(
            headless=headless,
            args=launch_args,
        )

        await self._new_context()
        logger.info("Browser started with anti-detection")

    async def _new_context(self):
        """Create a fresh browser context with a new fingerprint, restoring session if available"""
        if self.context:
            await self.context.close()

        fingerprint = self._fingerprint_mgr.get_random_fingerprint()
        context_options = self._fingerprint_mgr.get_context_options(fingerprint)

        proxy_settings = self.proxy_manager.get_playwright_proxy() if self.proxy_manager.enabled else None
        if proxy_settings:
            context_options['proxy'] = proxy_settings

        # Restore saved session (cookies, localStorage) if available
        if getattr(self, '_use_session', True) and SESSION_PATH.exists():
            try:
                context_options['storage_state'] = str(SESSION_PATH)
                logger.info("Restoring saved TikTok session (logged in)")
            except Exception as e:
                logger.warning(f"Could not restore session: {e}")

        self.context = await self.browser.new_context(**context_options)
        self.page = await self.context.new_page()

        stealth_js = self._fingerprint_mgr.get_stealth_scripts(fingerprint)
        await self.page.add_init_script(stealth_js)

        has_session = getattr(self, '_use_session', True) and SESSION_PATH.exists()
        logger.info(f"Browser context created (session: {'restored' if has_session else 'anonymous'})")

    async def save_session(self):
        """Save current browser session (cookies + localStorage) to disk"""
        if self.context:
            SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
            state = await self.context.storage_state()
            with open(SESSION_PATH, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)
            logger.info(f"Session saved to {SESSION_PATH}")

    @staticmethod
    def has_saved_session() -> bool:
        """Check if a saved session exists"""
        return SESSION_PATH.exists()

    @staticmethod
    def clear_session():
        """Delete saved session"""
        if SESSION_PATH.exists():
            SESSION_PATH.unlink()
            logger.info("Saved session cleared")

    async def download_image(self, url: str, username: str, image_type: str, index: int = 0) -> Optional[str]:
        """Download and resize image to ~150KB"""
        try:
            user_dir = self.thumbnails_dir / username
            user_dir.mkdir(parents=True, exist_ok=True)

            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            filename = f"{image_type}_{index}_{url_hash}.jpg" if image_type != 'profile' else f"profile_{url_hash}.jpg"
            filepath = user_dir / filename

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        content = await response.read()

                        img = Image.open(io.BytesIO(content))

                        # Convert to RGB
                        if img.mode in ('RGBA', 'LA', 'P'):
                            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                            if img.mode == 'P':
                                img = img.convert('RGBA')
                            rgb_img.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                            img = rgb_img

                        # Resize to max 1000px
                        max_dimension = 1000
                        if max(img.size) > max_dimension:
                            ratio = max_dimension / max(img.size)
                            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                            img = img.resize(new_size, Image.Resampling.LANCZOS)

                        # Save with compression
                        quality = 85
                        output = io.BytesIO()
                        img.save(output, format='JPEG', quality=quality, optimize=True)

                        # Adjust quality to meet ~150KB target
                        while output.tell() > 150 * 1024 and quality > 50:
                            output = io.BytesIO()
                            quality -= 5
                            img.save(output, format='JPEG', quality=quality, optimize=True)

                        with open(filepath, 'wb') as f:
                            f.write(output.getvalue())

                        logger.info(f"Downloaded: {filename} ({output.tell()/1024:.1f}KB)")
                        return str(filepath)

            return None
        except Exception as e:
            logger.error(f"Error downloading image: {e}")
            return None

    async def scrape_profile(self, username: str, category: str = '', location: str = '') -> Optional[Dict]:
        """Scrape a single TikTok profile"""
        try:
            from anti_detection import HumanBehaviorSimulator, NetworkPatternRandomizer
            behavior_sim = HumanBehaviorSimulator()
            network_sim = NetworkPatternRandomizer()
            
            url = f'https://www.tiktok.com/@{username}'
            logger.info(f"Scraping profile: @{username}")

            # Warm up: visit TikTok homepage first to look like a real user
            await network_sim.randomize_network(self.page)
            await behavior_sim.simulate_pre_navigation(self.page)
            try:
                await self.page.goto('https://www.tiktok.com/', wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(random.uniform(2, 4))
                await behavior_sim.simulate_scroll(self.page)
                await asyncio.sleep(random.uniform(1, 3))
            except Exception:
                pass

            # Navigate to the actual profile
            response = await self.page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await behavior_sim.simulate_post_navigation(self.page)

            # Wait for main content to load
            try:
                await self.page.wait_for_selector('[data-e2e="user-page"], h1, h2, main', timeout=15000)
            except:
                pass

            await behavior_sim.simulate_content_render(self.page)

            # Check HTTP status
            if response and response.status >= 400:
                if response.status == 404:
                    raise ProfileNotFoundException(f"Profile @{username} not found")
                elif response.status == 429:
                    raise RateLimitException("Rate limited")

            # Scroll to load video thumbnails
            await behavior_sim.simulate_scroll(self.page)

            try:
                await self.page.wait_for_selector('[data-e2e="user-post-item"] img, div[class*="DivVideoFeed"] img, article img', timeout=10000)
            except:
                pass

            # Handle "Something went wrong":
            #   Attempt 1-2: human-like Refresh button click
            #   Attempt 3: fresh browser context + re-navigate with warm-up
            max_refresh_attempts = 3
            for attempt in range(max_refresh_attempts):
                visible_text = await self.page.evaluate('() => document.body ? document.body.innerText : ""')
                if 'something went wrong' not in visible_text.lower():
                    break

                if attempt < 2:
                    logger.warning(f"Detected 'Something went wrong' — Refresh button (attempt {attempt + 1}/{max_refresh_attempts})")
                    try:
                        refresh_btn = self.page.get_by_role('button', name='Refresh')
                        await refresh_btn.wait_for(state='visible', timeout=5000)
                        box = await refresh_btn.bounding_box()
                        if box:
                            await refresh_btn.scroll_into_view_if_needed()
                            await asyncio.sleep(random.uniform(0.3, 0.8))

                            start_x = random.randint(200, 600)
                            start_y = random.randint(100, 300)
                            await self.page.mouse.move(start_x, start_y)
                            await asyncio.sleep(random.uniform(0.2, 0.5))

                            target_x = box['x'] + box['width'] / 2 + random.uniform(-3, 3)
                            target_y = box['y'] + box['height'] / 2 + random.uniform(-2, 2)
                            await self.page.mouse.move(target_x, target_y, steps=random.randint(8, 15))
                            await asyncio.sleep(random.uniform(0.15, 0.4))

                            await self.page.mouse.down()
                            await asyncio.sleep(random.uniform(0.05, 0.12))
                            await self.page.mouse.up()
                        else:
                            await refresh_btn.click(timeout=5000)

                        await asyncio.sleep(random.uniform(3, 6))
                    except Exception as e:
                        logger.warning(f"Refresh button click failed: {e}")

                else:
                    # Nuclear option: fresh context with new fingerprint + cooldown
                    cooldown = random.uniform(8, 15)
                    logger.warning(f"Detected 'Something went wrong' — fresh browser context + {cooldown:.0f}s cooldown (attempt {attempt + 1}/{max_refresh_attempts})")
                    await asyncio.sleep(cooldown)
                    await self._new_context()

                    # Warm up again with the fresh context
                    try:
                        await self.page.goto('https://www.tiktok.com/', wait_until='domcontentloaded', timeout=30000)
                        await asyncio.sleep(random.uniform(2, 4))
                        await behavior_sim.simulate_scroll(self.page)
                        await asyncio.sleep(random.uniform(1, 2))
                    except Exception:
                        pass

                    await self.page.goto(url, wait_until='domcontentloaded', timeout=60000)
                    await behavior_sim.simulate_post_navigation(self.page)
                    await behavior_sim.simulate_content_render(self.page)

                # Scroll and wait for video grid
                await behavior_sim.simulate_scroll(self.page)
                try:
                    await self.page.wait_for_selector('[data-e2e="user-post-item"] img, div[class*="DivVideoFeed"] img, article img', timeout=10000)
                except:
                    pass

            # Check visible page text for error states (avoid raw HTML which
            # contains JS template strings that cause false positives)
            visible_text = await self.page.evaluate('() => document.body ? document.body.innerText : ""')
            visible_text_lower = visible_text.lower()

            # Check for rate limiting
            if 'http error 429' in visible_text_lower or 'too many requests' in visible_text_lower:
                raise RateLimitException("Rate limited")

            # Check for private account first (more specific than not-found)
            if 'this account is private' in visible_text_lower:
                raise ProfileSkippedException(f"Profile @{username} is private")

            # Check for not found / banned — only match when the text appears
            # as a prominent page message, not inside JS bundles
            not_found_phrases = [
                "couldn't find this account",
                "page not available",
            ]
            # Only raise not-found when stats are absent (the phrases can
            # appear in TikTok's generic HTML even on valid profiles)
            has_stats = any(kw in visible_text_lower for kw in ['following', 'followers', 'likes'])
            if not has_stats:
                for phrase in not_found_phrases:
                    if phrase in visible_text_lower:
                        raise ProfileNotFoundException(f"Profile @{username} not found")

            await behavior_sim.simulate_final_wait(self.page)

            # Extract profile data via JavaScript evaluation
            profile_data = await self.page.evaluate(r'''() => {
                const data = {};

                // Username from URL
                const pathParts = window.location.pathname.split('/').filter(x => x);
                data.username = pathParts[0] ? pathParts[0].replace('@', '') : '';

                // Display name / nickname
                const nameSelectors = [
                    'h1[data-e2e="user-title"]',
                    'h2[data-e2e="user-subtitle"]',
                    'span[data-e2e="user-title"]',
                    'h1',
                    'h2'
                ];
                data.full_name = '';
                data.nickname = '';
                for (const sel of nameSelectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText && el.innerText.trim().length > 0) {
                        const text = el.innerText.trim();
                        if (!data.nickname) {
                            data.nickname = text;
                        } else if (!data.full_name && text !== data.nickname) {
                            data.full_name = text;
                        }
                    }
                }
                if (!data.full_name) data.full_name = data.nickname;

                // Stats: followers, following, likes
                const statsText = document.body.innerText;

                function parseCount(text) {
                    if (!text) return 0;
                    text = text.toUpperCase().replace(/,/g, '');
                    if (text.includes('K')) return Math.floor(parseFloat(text) * 1000);
                    if (text.includes('M')) return Math.floor(parseFloat(text) * 1000000);
                    if (text.includes('B')) return Math.floor(parseFloat(text) * 1000000000);
                    return parseInt(text) || 0;
                }

                // Try data-e2e attributes first (TikTok's semantic markers)
                const followingEl = document.querySelector('[data-e2e="following-count"]');
                const followersEl = document.querySelector('[data-e2e="followers-count"]');
                const likesEl = document.querySelector('[data-e2e="likes-count"]');

                if (followersEl) {
                    data.followers = parseCount(followersEl.innerText.trim());
                } else {
                    const followersMatch = statsText.match(/([\d,KkMmBb.]+)\s+Follower/i);
                    data.followers = followersMatch ? parseCount(followersMatch[1]) : 0;
                }

                if (followingEl) {
                    data.following = parseCount(followingEl.innerText.trim());
                } else {
                    const followingMatch = statsText.match(/([\d,KkMmBb.]+)\s+Following/i);
                    data.following = followingMatch ? parseCount(followingMatch[1]) : 0;
                }

                if (likesEl) {
                    data.likes = parseCount(likesEl.innerText.trim());
                } else {
                    const likesMatch = statsText.match(/([\d,KkMmBb.]+)\s+Like/i);
                    data.likes = likesMatch ? parseCount(likesMatch[1]) : 0;
                }

                // Video/post count (number of videos on the profile grid)
                const videoItems = document.querySelectorAll(
                    '[data-e2e="user-post-item"], div[class*="DivVideoFeed"] > div, div[class*="DivItemContainer"]'
                );
                data.videos_count = videoItems.length;

                // Bio / signature
                const bioSelectors = [
                    'h2[data-e2e="user-bio"]',
                    '[data-e2e="user-bio"]',
                    'span[data-e2e="user-bio"]',
                ];
                data.bio = '';
                for (const sel of bioSelectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText && el.innerText.length > 1) {
                        data.bio = el.innerText.trim();
                        break;
                    }
                }

                // Profile link (bio link)
                const linkSelectors = [
                    'a[data-e2e="user-link"]',
                    'a[target="_blank"][rel*="noopener"]',
                ];
                data.bio_link = '';
                for (const sel of linkSelectors) {
                    const el = document.querySelector(sel);
                    if (el && el.href && !el.href.includes('tiktok.com')) {
                        data.bio_link = el.href;
                        break;
                    }
                }

                // Profile picture
                const avatarSelectors = [
                    '[data-e2e="user-avatar"] img',
                    'img[class*="ImgAvatar"]',
                    'span[class*="SpanAvatarContainer"] img',
                    'header img',
                ];
                data.profile_pic_url = '';
                for (const sel of avatarSelectors) {
                    const el = document.querySelector(sel);
                    if (el && el.src && el.src.startsWith('http')) {
                        data.profile_pic_url = el.src;
                        break;
                    }
                }

                // Verified badge
                data.is_verified = !!(
                    document.querySelector('svg[class*="Verified"]') ||
                    document.querySelector('[data-e2e="verify-badge"]') ||
                    document.querySelector('path[d*="verified"]') ||
                    statsText.includes('Verified account')
                );

                // Private account
                data.is_private = statsText.toLowerCase().includes('this account is private');

                // Video thumbnails from the grid
                data.content_thumbnails = [];
                const thumbnails = document.querySelectorAll(
                    '[data-e2e="user-post-item"] img, div[class*="DivVideoFeed"] img, div[class*="DivItemContainer"] img'
                );
                for (const img of thumbnails) {
                    if (data.content_thumbnails.length >= 6) break;
                    const src = img.src;
                    if (src && src.startsWith('http') && !src.includes('avatar') && !src.includes('profile')) {
                        data.content_thumbnails.push(src);
                    }
                }

                // Video view counts from the grid
                data.video_views = [];
                const viewElements = document.querySelectorAll(
                    '[data-e2e="video-views"], [class*="DivVideoCount"] strong, [class*="SpanViews"]'
                );
                for (const el of viewElements) {
                    if (data.video_views.length >= 6) break;
                    const text = el.innerText.trim();
                    if (text) {
                        data.video_views.push({
                            display: text,
                            count: parseCount(text)
                        });
                    }
                }

                return data;
            }''')

            # Validate data
            if not profile_data.get('username'):
                return None

            if profile_data.get('is_private'):
                logger.warning(f"Skipping private account: @{username}")
                return None

            # Check minimum followers
            min_followers = self.config.get('scraper', {}).get('min_followers', 1000)
            if profile_data.get('followers', 0) < min_followers:
                logger.warning(f"Skipping @{username}: {profile_data.get('followers', 0)} followers < {min_followers}")
                return None

            # Classify influencer tier
            followers = profile_data.get('followers', 0)
            if followers < 1000:
                tier = 'nano'
            elif followers < 10000:
                tier = 'micro'
            elif followers < 100000:
                tier = 'mid'
            elif followers < 1000000:
                tier = 'macro'
            else:
                tier = 'mega'

            profile_data['influencer_tier'] = tier

            # Download profile picture
            if profile_data.get('profile_pic_url'):
                profile_pic_local = await self.download_image(
                    profile_data['profile_pic_url'],
                    username,
                    'profile'
                )
                profile_data['profile_pic_local'] = profile_pic_local

            # Download content thumbnails
            content_thumbnails_local = []
            if profile_data.get('content_thumbnails'):
                max_thumbnails = self.config.get('scraper', {}).get('max_thumbnails', 6)
                for idx, thumb_url in enumerate(profile_data['content_thumbnails'][:max_thumbnails], 1):
                    local_path = await self.download_image(thumb_url, username, 'content', idx)
                    if local_path:
                        content_thumbnails_local.append(local_path)
                profile_data['content_thumbnails_local'] = content_thumbnails_local

            # Add metadata
            profile_data['category'] = category
            profile_data['location'] = location
            profile_data['profile_url'] = f'https://www.tiktok.com/@{username}'
            profile_data['scrape_timestamp'] = datetime.now().isoformat()

            logger.info(f"✅ Scraped: @{username} ({followers:,} followers, {tier})")
            return profile_data

        except (ProfileNotFoundException, ProfileSkippedException, RateLimitException, DailyLimitException):
            raise
        except Exception as e:
            logger.error(f"Error scraping @{username}: {e}")
            return None

    def save_profile(self, profile: Dict):
        """Save profile to JSON file"""
        username = profile.get('username', 'unknown')
        filepath = self.output_dir / f"{username}.json"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved: {filepath}")

    async def cleanup(self):
        """Close browser"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser closed")


def load_queue_file(filepath: str) -> Dict:
    """Load queue file with checkpoint data"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if 'completed' not in data:
        data['completed'] = []
    if 'current_index' not in data:
        data['current_index'] = 0
    if 'failed' not in data:
        data['failed'] = {}

    return data


def save_queue_file(filepath: str, data: Dict):
    """Save queue file with checkpoint"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


async def scrape_from_queue(queue_file: str, resume: bool = True, use_session: bool = True) -> List[Dict]:
    """Scrape profiles from a queue file"""
    queue_data = load_queue_file(queue_file)
    
    usernames = queue_data.get('usernames', [])
    completed = set(queue_data.get('completed', []))
    location = queue_data.get('location', '')
    category = queue_data.get('category', '')
    
    remaining = [u for u in usernames if u not in completed]
    
    print(f"\n{'='*50}")
    print(f"📋 Queue: {Path(queue_file).name}")
    print(f"   Location: {location}")
    print(f"   Category: {category}")
    print(f"   Total: {len(usernames)} | Completed: {len(completed)} | Remaining: {len(remaining)}")
    print(f"{'='*50}\n")
    
    if not remaining:
        print("✅ All profiles already scraped!")
        return []
    
    scraper = TikTokScraper()
    results = []
    
    try:
        await scraper.start_browser(use_session=use_session)
        
        for i, username in enumerate(remaining, 1):
            print(f"\n[{i}/{len(remaining)}] Scraping: @{username}")
            
            try:
                profile = await scraper.scrape_profile(username, category, location)
                
                if profile:
                    results.append(profile)
                    scraper.save_profile(profile)
                    queue_data['completed'].append(username)
                else:
                    queue_data['failed'][username] = 'no_data'
                
            except ProfileNotFoundException:
                queue_data['failed'][username] = 'not_found'
                logger.warning(f"Profile not found: @{username}")
            except ProfileSkippedException:
                queue_data['failed'][username] = 'skipped'
            except RateLimitException:
                logger.error("Rate limited! Waiting 60 seconds...")
                await asyncio.sleep(60)
            except DailyLimitException:
                logger.error("Daily limit reached! Stopping.")
                break
            except Exception as e:
                queue_data['failed'][username] = str(e)
                logger.error(f"Error: {e}")
            
            # Save checkpoint
            save_queue_file(queue_file, queue_data)
            
            # Cooldown + fresh browser context between profiles
            delay = random.uniform(8, 15)
            logger.info(f"Cooldown {delay:.1f}s + resetting browser state...")
            await asyncio.sleep(delay)
            await scraper._new_context()
        
    finally:
        await scraper.cleanup()
    
    return results


async def scrape_single(username: str, output_json: bool = False, use_session: bool = True) -> Optional[Dict]:
    """Scrape a single TikTok profile"""
    scraper = TikTokScraper()
    
    try:
        await scraper.start_browser(use_session=use_session)
        
        profile = await scraper.scrape_profile(username)
        
        if profile:
            scraper.save_profile(profile)
            if output_json:
                return profile
            print(f"\n✅ Scraped: @{username}")
            print(f"   Followers: {profile.get('followers', 0):,}")
            print(f"   Likes: {profile.get('likes', 0):,}")
            print(f"   Tier: {profile.get('influencer_tier', 'unknown')}")
            return profile
        else:
            if output_json:
                return {"error": "Could not scrape profile"}
            print(f"\n❌ Could not scrape: @{username}")
            return None
        
    finally:
        await scraper.cleanup()


async def login_interactive():
    """Open a browser for manual TikTok login, then save the session"""
    scraper = TikTokScraper()

    try:
        await scraper.start_browser(headless=False, use_session=False)

        print("\n" + "=" * 55)
        print("  TikTok Login — Manual Authentication")
        print("=" * 55)
        print("\n  A browser window has opened to tiktok.com/login.")
        print("  Log in with your account (QR code, phone, email, etc).")
        print("  The session will be saved automatically once login is detected.\n")
        print("  Waiting for login...", flush=True)

        await scraper.page.goto('https://www.tiktok.com/login', wait_until='domcontentloaded', timeout=60000)

        # Poll for login by checking for session cookies
        login_cookie_names = {'sessionid', 'sid_tt', 'ssid_ucp_v1', 'sid_guard', 'passport_csrf_token'}
        max_wait = 300  # 5 minutes
        poll_interval = 3
        elapsed = 0
        logged_in = False

        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            cookies = await scraper.context.cookies()
            cookie_names = {c.get('name') for c in cookies}
            found = cookie_names & login_cookie_names

            if found:
                logged_in = True
                break

            # Also check if URL changed away from login page
            current_url = scraper.page.url
            if '/login' not in current_url and 'tiktok.com' in current_url:
                logged_in = True
                break

        if logged_in:
            # Give a moment for all cookies to settle
            await asyncio.sleep(2)
            await scraper.save_session()
            cookies = await scraper.context.cookies()
            print(f"\n  ✅ Login detected! Session saved.")
            print(f"     Cookies captured: {len(cookies)}")
            print(f"     Session file: {SESSION_PATH}")
            print("     The scraper will now use this session automatically.\n")
        else:
            print(f"\n  ⏱️  Timed out after {max_wait}s waiting for login.")
            print("     Try again with: python main.py login\n")

    finally:
        await scraper.cleanup()


def logout():
    """Clear saved TikTok session"""
    if TikTokScraper.has_saved_session():
        TikTokScraper.clear_session()
        print("\n  ✅ Logged out — saved session cleared.")
        print("     The scraper will now run anonymously.\n")
    else:
        print("\n  No saved session found.\n")


def session_status():
    """Show current session status"""
    if TikTokScraper.has_saved_session():
        stat = SESSION_PATH.stat()
        mod_time = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n  ✅ Saved session found")
        print(f"     File: {SESSION_PATH}")
        print(f"     Last updated: {mod_time}")
        print(f"     Size: {stat.st_size / 1024:.1f} KB\n")
    else:
        print("\n  No saved session — scraper will run anonymously.")
        print("  Run 'python main.py login' to authenticate.\n")


def export_data(output_format: str = 'both'):
    """Export all scraped data to JSON and/or CSV"""
    output_files = list(OUTPUT_DIR.glob('*.json'))
    
    if not output_files:
        print("No data to export")
        return
    
    profiles = []
    for f in output_files:
        with open(f, 'r', encoding='utf-8') as file:
            profiles.append(json.load(file))
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if output_format in ('json', 'both'):
        json_path = DATA_DIR / f"export_{timestamp}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(profiles, f, indent=2, ensure_ascii=False)
        print(f"📁 JSON export: {json_path}")
    
    if output_format in ('csv', 'both'):
        csv_path = DATA_DIR / f"export_{timestamp}.csv"
        if profiles:
            keys = ['username', 'full_name', 'nickname', 'followers', 'following', 'likes',
                   'videos_count', 'is_verified', 'bio', 'bio_link', 'influencer_tier',
                   'category', 'location', 'profile_url']
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(profiles)
        print(f"📁 CSV export: {csv_path}")


def list_queue_files():
    """List all queue files"""
    queue_files = sorted(QUEUE_DIR.glob('*.json'))
    
    if not queue_files:
        print("No queue files found")
        return
    
    print(f"\n{'='*60}")
    print("📋 Available Queue Files")
    print(f"{'='*60}")
    
    for i, qf in enumerate(queue_files, 1):
        try:
            with open(qf, 'r') as f:
                data = json.load(f)
            total = len(data.get('usernames', []))
            completed = len(data.get('completed', []))
            pct = int(completed/total*100) if total > 0 else 0
            print(f"{i}. {qf.name}")
            print(f"   Location: {data.get('location', 'N/A')} | Category: {data.get('category', 'N/A')}")
            print(f"   Progress: {completed}/{total} ({pct}%)")
        except:
            print(f"{i}. {qf.name} (error reading)")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='TikTok Profile Scraper')
    parser.add_argument('queue_file', nargs='?', help='Queue file to scrape')
    parser.add_argument('--username', '-u', type=str, help='Single username to scrape')
    parser.add_argument('--list', '-l', action='store_true', help='List queue files')
    parser.add_argument('--resume', '-r', action='store_true', default=True, help='Resume from checkpoint')
    parser.add_argument('--export', '-e', type=str, choices=['json', 'csv', 'both'], help='Export data')
    parser.add_argument('--output', '-o', type=str, choices=['json', 'text'], default='text', help='Output format')
    
    args = parser.parse_args()
    
    if args.list:
        list_queue_files()
    elif args.export:
        export_data(args.export)
    elif args.username:
        result = asyncio.run(scrape_single(args.username, args.output == 'json'))
        if args.output == 'json' and result:
            print(json.dumps(result, indent=2))
    elif args.queue_file:
        asyncio.run(scrape_from_queue(args.queue_file, args.resume))
    else:
        parser.print_help()
