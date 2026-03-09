# 🎵 TikTok Profile Scraper

> Part of **[ScrapeClaw](https://www.scrapeclaw.cc/)** — a suite of production-ready, agentic social media scrapers for Instagram, YouTube, X/Twitter, TikTok, and Facebook. Built with Python & Playwright. No API keys required.

[![ScrapeClaw](https://img.shields.io/badge/ScrapeClaw-Visit%20Site-blue?style=flat-square)](https://www.scrapeclaw.cc/)
[![ClawHub](https://img.shields.io/badge/ClawHub-View%20Skill-green?style=flat-square)](https://clawhub.ai/ArulmozhiV/tiktok-scraper)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-PayPal-yellow?style=flat-square&logo=paypal)](https://www.paypal.com/paypalme/arulmozhivelu)

---

## What Is This?

A browser-based TikTok scraper that discovers and extracts structured data from **public TikTok profiles** — without any official API. It uses Playwright for full browser automation with built-in anti-detection, fingerprinting, and human behavior simulation to scrape at scale reliably.

Two-phase workflow:
1. **Discovery** — Find TikTok profiles by location and category via Google Custom Search
2. **Scraping** — Extract full profile data, stats, video thumbnails, and engagement using a real browser session

---

## Features

| Feature | Description |
|---------|-------------|
| 🔍 **Discovery** | Find profiles by city and category automatically |
| 🌐 **Browser Simulation** | Full Playwright browser — renders JavaScript, handles dynamic content |
| 🛡️ **Anti-Detection** | Browser fingerprinting, stealth scripts, human behavior simulation |
| 📊 **Rich Data** | Profile info, follower counts, bios, video views, engagement stats |
| 🖼️ **Media Download** | Profile pics and video thumbnails saved locally |
| 💾 **Flexible Export** | JSON and CSV output formats |
| 🔄 **Resume Support** | Checkpoint-based resume for interrupted sessions |
| ⚡ **Smart Filtering** | Auto-skip private accounts, low-follower profiles, empty accounts |
| 🌍 **Residential Proxy** | Built-in proxy manager supporting 4 major providers |

---

## Installation

```bash
# Clone the repository
git clone https://github.com/Scrapeclaw/tiktok-scraper.git
cd tiktok-scraper

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### Environment Setup

Create a `.env` file in the project root:

```env
# Google Custom Search API (optional, for discovery)
GOOGLE_API_KEY=your_google_api_key
GOOGLE_SEARCH_ENGINE_ID=your_search_engine_id

# Residential proxy (optional — see Proxy section below)
PROXY_ENABLED=false
PROXY_PROVIDER=brightdata
PROXY_USERNAME=your_proxy_user
PROXY_PASSWORD=your_proxy_pass
PROXY_COUNTRY=us
PROXY_STICKY=true
```

> **Note:** TikTok does not require login to view public profiles, but logging in is **recommended** for reliable video grid scraping. See the Login section below.

---

## Usage

### Login (Recommended)

Logging in to TikTok dramatically improves scraping reliability — especially for video thumbnails and view counts which often fail to load for anonymous visitors.

```bash
# Open a browser to log in manually (QR code, phone, email, etc.)
python main.py login

# Check if you have an active session
python main.py status

# Clear your saved session
python main.py logout
```

**How it works:**
1. `login` opens a Chromium browser to TikTok's login page
2. You log in manually using any method (QR code is fastest)
3. Once logged in, press Enter in the terminal to save the session
4. All future `scrape` commands automatically use the saved session
5. To scrape anonymously instead, add `--no-login`

The session is saved to `data/tiktok_session.json` (cookies + localStorage). It persists across runs until it expires or you run `logout`.

### Discover Profiles

```bash
# Discover dance creators in Miami
python main.py discover --location "Miami" --category "dance"

# Discover comedy creators in New York
python main.py discover --location "New York" --category "comedy"

# Return JSON output (for agent integration)
python main.py discover --location "Miami" --category "fitness" --output json

# Batch discovery across multiple locations and categories
python main.py discover --batch
```

### Scrape

```bash
# Scrape a single profile (uses saved session if available)
python main.py scrape --username charlidamelio

# Scrape from a discovery queue file
python main.py scrape data/queue/Miami_dance_20260302.json

# Run headless
python main.py scrape --username charlidamelio --headless

# Scrape anonymously (skip saved session)
python main.py scrape --username charlidamelio --no-login
```

### Manage & Export

```bash
# List available queue files
python main.py list

# Export all scraped data to JSON + CSV
python main.py export --format both
```

---

## Output Data

Each scraped profile is saved to `data/output/{username}.json`:

```json
{
  "username": "example_creator",
  "full_name": "Example Creator",
  "nickname": "Example",
  "bio": "Dance creator | NYC 💃",
  "bio_link": "https://example.com",
  "followers": 250000,
  "following": 800,
  "likes": 5000000,
  "videos_count": 120,
  "is_verified": false,
  "is_private": false,
  "influencer_tier": "macro",
  "category": "dance",
  "location": "New York",
  "profile_url": "https://www.tiktok.com/@example_creator",
  "profile_pic_local": "thumbnails/example_creator/profile_abc123.jpg",
  "content_thumbnails": [
    "thumbnails/example_creator/content_1_def456.jpg",
    "thumbnails/example_creator/content_2_ghi789.jpg"
  ],
  "video_views": [
    {"display": "1.2M", "count": 1200000},
    {"display": "500K", "count": 500000}
  ],
  "scrape_timestamp": "2026-03-02T14:30:00"
}
```

### Influencer Tiers

| Tier | Followers |
|------|-----------|
| nano | < 1,000 |
| micro | 1,000 – 10,000 |
| mid | 10,000 – 100,000 |
| macro | 100,000 – 1M |
| mega | > 1,000,000 |

---

## ⚠️ "Something went wrong" — Why You Need a Proxy

When scraping multiple profiles, you'll likely see TikTok's video grid fail with **"Something went wrong — Sorry about that! Please try again later."** while the profile header (followers, bio, etc.) still loads fine.

**Why this happens:** TikTok's profile header is server-side rendered, but the video feed is loaded via a separate client-side API call. After a few requests from the same IP, TikTok rate-limits this video feed endpoint. This is **IP-based throttling** — clearing cookies, rotating fingerprints, or clicking the Refresh button won't fix it.

**What works without a proxy:**
- Profile info (username, display name, bio, bio link)
- Follower, following, and like counts
- Profile picture download
- Influencer tier classification

**What requires a proxy:**
- Video grid thumbnails and view counts
- Scraping more than ~3-5 profiles in a session without cooldowns

**The fix:** Use a residential proxy to rotate your IP between scrapes. The scraper has built-in support for this — see the proxy setup below or visit **[ScrapeClaw Proxies](https://www.scrapeclaw.cc/#proxies)** for recommended providers and setup guides.

---

## 🌐 Residential Proxy (Recommended for Scale)

Running long scraping sessions without a residential proxy will get your IP blocked. The built-in proxy manager handles rotation, sticky sessions, and country targeting automatically.

> **Need help choosing a proxy?** See our [proxy comparison and setup guide](https://www.scrapeclaw.cc/#proxies) for detailed benchmarks, pricing breakdowns, and step-by-step configuration for each provider.

### Why Use a Residential Proxy?

- ✅ Avoid IP bans — residential IPs look like real users to TikTok
- ✅ Rotate IPs automatically on every request or session
- ✅ Sticky sessions — keep the same IP during a browsing session
- ✅ Geo-target by country for locale-accurate content
- ✅ 95%+ success rates vs ~30% with datacenter proxies

### Recommended Providers

We have affiliate partnerships with the following providers. Using these links supports this project at no extra cost to you:

| Provider | Highlights | Sign Up |
|----------|-----------|---------|
| **Bright Data** | World's largest network, 72M+ IPs, enterprise-grade | 👉 [**Get Bright Data**](https://get.brightdata.com/o1kpd2da8iv4) |
| **IProyal** | Pay-as-you-go, 195+ countries, no traffic expiry | 👉 [**Get IProyal**](https://iproyal.com/?r=ScrapeClaw) |
| **Storm Proxies** | Fast & reliable, developer-friendly API, competitive pricing | 👉 [**Get Storm Proxies**](https://stormproxies.com/clients/aff/go/scrapeclaw) |
| **NetNut** | ISP-grade network, 52M+ IPs, direct connectivity | 👉 [**Get NetNut**](https://netnut.io?ref=mwrlzwv) |

> These are affiliate links. We may earn a commission at no extra cost to you.

### Enabling the Proxy

**Option 1 — Environment variables (recommended):**

```bash
export PROXY_ENABLED=true
export PROXY_PROVIDER=brightdata        # brightdata | iproyal | stormproxies | netnut | custom
export PROXY_USERNAME=your_proxy_user
export PROXY_PASSWORD=your_proxy_pass
export PROXY_COUNTRY=us                 # optional
export PROXY_STICKY=true                # keeps same IP per session
```

**Option 2 — `config/scraper_config.json`:**

```json
{
  "proxy": {
    "enabled": true,
    "provider": "brightdata",
    "country": "us",
    "sticky": true,
    "sticky_ttl_minutes": 10
  }
}
```

Set credentials via env vars (`PROXY_USERNAME`, `PROXY_PASSWORD`) — never hardcode them in the config file.

### Provider Host/Port Reference

| Provider | Host | Port |
|----------|------|------|
| Bright Data | `brd.superproxy.io` | `22225` |
| IProyal | `proxy.iproyal.com` | `12321` |
| Storm Proxies | `rotating.stormproxies.com` | `9999` |
| NetNut | `gw-resi.netnut.io` | `5959` |

Once configured, the scraper uses the proxy automatically — no extra flags needed. The log confirms it:

```
INFO - Proxy enabled: <ProxyManager provider=brightdata enabled host=brd.superproxy.io:22225>
INFO - Browser using proxy: brightdata → brd.superproxy.io:22225
```

---

## Configuration Reference

Edit `config/scraper_config.json` to customise behaviour:

```json
{
  "proxy": {
    "enabled": false,
    "provider": "brightdata",
    "country": "",
    "sticky": true,
    "sticky_ttl_minutes": 10
  },
  "google_search": {
    "enabled": true,
    "api_key": "",
    "search_engine_id": "",
    "queries_per_location": 3
  },
  "scraper": {
    "headless": false,
    "min_followers": 1000,
    "download_thumbnails": true,
    "max_thumbnails": 6,
    "delay_between_profiles": [3, 6],
    "timeout": 60000
  }
}
```

---

## Project Structure

```
tiktok-scraper/
├── main.py               # CLI entry point
├── scraper.py            # Playwright browser scraper
├── discovery.py          # Google-based profile discovery
├── anti_detection.py     # Fingerprinting & stealth
├── proxy_manager.py      # Residential proxy integration
├── config/
│   └── scraper_config.json
├── data/
│   ├── output/           # Scraped JSON files
│   ├── queue/            # Discovery queue files
│   └── browser_fingerprints.json
└── thumbnails/           # Downloaded profile & video images
```

---

## Part of ScrapeClaw

This scraper is one of several tools in the **[ScrapeClaw](https://www.scrapeclaw.cc/)** collection:

| Scraper | Description | Links |
|---------|-------------|-------|
| 🎵 **TikTok** | Profiles, video views, likes & follower counts | [GitHub](https://github.com/Scrapeclaw/tiktok-scraper) · [ClawHub](https://clawhub.ai/ArulmozhiV/tiktok-scraper) |
| 📸 **Instagram** | Profiles, posts, media & follower counts | [GitHub](https://github.com/Scrapeclaw/instagram-scraper) · [ClawHub](https://clawhub.ai/ArulmozhiV/instagram-scraper) |
| 📘 **Facebook** | Pages, groups, posts & engagement data | [GitHub](https://github.com/Scrapeclaw/facebook-scraper) · [ClawHub](https://clawhub.ai/ArulmozhiV/facebook-scraper) |
| 🎥 **YouTube** | Channels, subscribers & video metadata | [GitHub](https://github.com/Scrapeclaw/youtube-scrapper) · [ClawHub](https://clawhub.ai/ArulmozhiV/youtube-scrapper) |
| 🐦 **X / Twitter** | Tweets, profiles & engagement metrics | [GitHub](https://github.com/Scrapeclaw/twitter-scraper) · [ClawHub](https://clawhub.ai/ArulmozhiV/x-twitter-scraper) |

All scrapers share the same anti-detection foundation, proxy support, and JSON/CSV export pipeline.

---

## ☕ Support This Project

If this tool saves you time or helps your workflow, consider buying me a coffee — it keeps the project maintained and new scrapers coming!

[![Buy Me a Coffee via PayPal](https://img.shields.io/badge/☕%20Buy%20Me%20a%20Coffee-PayPal-blue?style=for-the-badge&logo=paypal)](https://www.paypal.com/paypalme/arulmozhivelu)

👉 **[paypal.me/arulmozhivelu](https://www.paypal.com/paypalme/arulmozhivelu)**

---

## Disclaimer

This tool is intended for scraping **publicly available** data only. Always comply with TikTok's Terms of Service and your local data privacy regulations. The author is not responsible for any misuse.

---

*Built by [ScrapeClaw](https://www.scrapeclaw.cc/) · [View all scrapers](https://www.scrapeclaw.cc/#scrapers)*
