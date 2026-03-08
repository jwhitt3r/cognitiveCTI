#!/usr/bin/env python3
"""
Telegram Channel Scanner & OpenCTI Ingestion Setup
===================================================
Fetches the deepdarkCTI Telegram threat actor list from GitHub,
tests each public channel against RSS Bridge, and adds working
ones to OpenCTI as RSS feed ingestion sources.

Usage:
    pip install requests --break-system-packages
    python3 telegram_channel_scanner.py

Configuration:
    Edit the variables below before running.
"""

import re
import time
import json
import requests
from urllib.parse import quote

# ============================================================
# CONFIGURATION — Edit these to match your setup
# ============================================================

# RSS Bridge URL (from your Docker host)
RSS_BRIDGE_URL = "http://localhost:3000"

# OpenCTI configuration
OPENCTI_URL = "http://OPENCTI_URL:OPENCTI_PORT"
OPENCTI_TOKEN = ""  # Replace with your opencti token

# How long to wait between tests (seconds) — be polite to Telegram
DELAY_BETWEEN_TESTS = 2

# Only add channels marked as VALID in the deepdarkCTI list
ONLY_VALID = True

# Dry run — set to True to test without adding to OpenCTI
DRY_RUN = False

# Output file for results
OUTPUT_FILE = "telegram_channels_results.json"

# ============================================================
# STEP 1: Fetch and parse the deepdarkCTI channel list
# ============================================================

def fetch_channel_list():
    """Fetch the raw markdown from GitHub and extract channel info."""
    url = "https://raw.githubusercontent.com/fastfire/deepdarkCTI/main/telegram_threat_actors.md"
    print(f"[*] Fetching channel list from {url}")

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"[!] Failed to fetch channel list: {e}")
        return []

    content = resp.text
    channels = []

    # Parse markdown table rows
    # Format: | Name | URL | Status | Description |
    # Also handles: | Name | URL | Status |
    lines = content.split('\n')

    for line in lines:
        # Skip header/separator rows
        if '|' not in line or '---' in line:
            continue

        cols = [c.strip() for c in line.split('|')]
        cols = [c for c in cols if c]  # Remove empty strings

        if len(cols) < 3:
            continue

        # Extract Telegram URLs from the columns
        for col in cols:
            # Match t.me/username links (public channels only)
            url_match = re.search(r'https?://t\.me/([A-Za-z0-9_]+)(?:\s|$|\)|\|)', col + ' ')
            if url_match:
                username = url_match.group(1)

                # Skip invite links, bot links, and common non-channel paths
                if username.lower() in ['joinchat', 'addstickers', 'share', 's']:
                    continue

                # Check for VALID/EXPIRED status in the line
                status = 'unknown'
                line_upper = line.upper()
                if 'VALID' in line_upper and 'EXPIRED' not in line_upper:
                    status = 'valid'
                elif 'EXPIRED' in line_upper:
                    status = 'expired'

                # Extract name from first column
                name = cols[0] if cols[0] != username else ''
                # Clean markdown links from name
                name = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', name).strip()

                # Extract description if available
                description = ''
                for c in cols:
                    c_lower = c.lower()
                    if any(kw in c_lower for kw in ['ddos', 'ransomware', 'malware',
                        'phishing', 'carding', 'hack', 'leak', 'breach', 'exploit',
                        'stealer', 'botnet', 'apt', 'rat', 'spam']):
                        description = c
                        break

                channels.append({
                    'username': username,
                    'name': name or username,
                    'status': status,
                    'description': description,
                    'url': f'https://t.me/{username}'
                })

    # Also extract invite-link channels (t.me/+XXXXX) - log but skip
    invite_count = len(re.findall(r'https?://t\.me/\+', content))

    # Deduplicate by username
    seen = set()
    unique = []
    for ch in channels:
        if ch['username'].lower() not in seen:
            seen.add(ch['username'].lower())
            unique.append(ch)

    print(f"[*] Found {len(unique)} public channels, {invite_count} invite-only channels (skipped)")
    return unique


# ============================================================
# STEP 2: Test channels against RSS Bridge
# ============================================================

def test_channel(username):
    """Test if a channel works with RSS Bridge."""
    url = f"{RSS_BRIDGE_URL}/?action=display&bridge=TelegramBridge&username={quote(username)}&format=Atom"

    try:
        resp = requests.get(url, timeout=15)

        # Check for RSS Bridge error responses
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}"

        # Check if response contains actual feed data
        content = resp.text
        if 'error' in content.lower() and ('non-existing' in content.lower() or
            'non-public' in content.lower() or 'unable to find' in content.lower()):
            return False, "Channel not found or not public"

        if '<entry>' in content or '<item>' in content:
            return True, "Working"

        if '<?xml' in content or '<feed' in content:
            return True, "Feed returned (may be empty)"

        return False, "No feed content"

    except requests.exceptions.Timeout:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)


def test_all_channels(channels):
    """Test all channels and return results."""
    results = {
        'working': [],
        'failed': [],
        'skipped': []
    }

    # Filter based on ONLY_VALID setting
    to_test = []
    for ch in channels:
        if ONLY_VALID and ch['status'] == 'expired':
            results['skipped'].append({**ch, 'reason': 'Marked as EXPIRED'})
            continue
        to_test.append(ch)

    print(f"\n[*] Testing {len(to_test)} channels against RSS Bridge...")
    print(f"    (Skipped {len(results['skipped'])} expired channels)\n")

    for i, ch in enumerate(to_test):
        username = ch['username']
        print(f"  [{i+1}/{len(to_test)}] Testing {username}...", end=' ', flush=True)

        success, message = test_channel(username)

        if success:
            print(f"OK - {message}")
            ch['rss_url'] = f"http://rss-bridge:80/?action=display&bridge=TelegramBridge&username={quote(username)}&format=Atom"
            results['working'].append(ch)
        else:
            print(f"FAIL - {message}")
            results['failed'].append({**ch, 'reason': message})

        time.sleep(DELAY_BETWEEN_TESTS)

    print(f"\n[*] Results: {len(results['working'])} working, "
          f"{len(results['failed'])} failed, {len(results['skipped'])} skipped")

    return results


# ============================================================
# STEP 3: Add working channels to OpenCTI
# ============================================================

def create_opencti_org(org_name):
    """Create an organization in OpenCTI if it doesn't exist."""
    query = """
    mutation CreateOrg($input: OrganizationAddInput!) {
      organizationAdd(input: $input) {
        id
        name
      }
    }
    """
    variables = {
        "input": {
            "name": org_name,
            "description": "Telegram OSINT source - lower trust"
        }
    }

    try:
        resp = requests.post(
            f"{OPENCTI_URL}/graphql",
            json={"query": query, "variables": variables},
            headers={
                "Authorization": f"Bearer {OPENCTI_TOKEN}",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        data = resp.json()
        if 'data' in data and data['data'].get('organizationAdd'):
            return data['data']['organizationAdd']['id']
    except Exception as e:
        print(f"    [!] Could not create org: {e}")

    return None


def add_to_opencti(channel):
    """Add a working channel as an RSS feed ingestion in OpenCTI."""
    # OpenCTI RSS Feed Ingestion mutation
    query = """
    mutation IngestionRssAdd($input: IngestionRssAddInput!) {
      ingestionRssAdd(input: $input) {
        id
        name
        uri
      }
    }
    """

    feed_name = f"Telegram - {channel['name']}"
    variables = {
        "input": {
            "name": feed_name,
            "description": f"Telegram channel: {channel['username']} - {channel.get('description', 'Threat actor channel')}",
            "uri": channel['rss_url'],
            "report_types": ["threat-report"],
            "object_marking_refs": [],  # You may need to add TLP:AMBER ID here
            "ingestion_running": True
        }
    }

    try:
        resp = requests.post(
            f"{OPENCTI_URL}/graphql",
            json={"query": query, "variables": variables},
            headers={
                "Authorization": f"Bearer {OPENCTI_TOKEN}",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        data = resp.json()

        if 'errors' in data:
            error_msg = data['errors'][0].get('message', 'Unknown error')
            if 'already exists' in error_msg.lower():
                return 'exists', feed_name
            return 'error', error_msg

        if 'data' in data and data['data'].get('ingestionRssAdd'):
            return 'created', feed_name

        return 'error', str(data)

    except Exception as e:
        return 'error', str(e)


def add_all_to_opencti(working_channels):
    """Add all working channels to OpenCTI."""
    print(f"\n[*] Adding {len(working_channels)} channels to OpenCTI...")

    if DRY_RUN:
        print("    [DRY RUN] Would add the following channels:")
        for ch in working_channels:
            print(f"    - {ch['name']} ({ch['username']})")
            print(f"      URL: {ch['rss_url']}")
        return

    # Create the Telegram OSINT org first
    print("  Creating 'Telegram OSINT' organization...")
    org_id = create_opencti_org("Telegram OSINT")

    created = 0
    existed = 0
    errors = 0

    for i, ch in enumerate(working_channels):
        print(f"  [{i+1}/{len(working_channels)}] Adding {ch['name']}...", end=' ', flush=True)

        status, msg = add_to_opencti(ch)

        if status == 'created':
            print(f"OK - Created")
            created += 1
        elif status == 'exists':
            print(f"SKIP - Already exists")
            existed += 1
        else:
            print(f"ERROR - {msg}")
            errors += 1

        time.sleep(0.5)

    print(f"\n[*] OpenCTI Results: {created} created, {existed} already existed, {errors} errors")


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("Telegram Channel Scanner & OpenCTI Ingestion Setup")
    print("=" * 60)

    # Step 1: Fetch channel list
    channels = fetch_channel_list()
    if not channels:
        print("[!] No channels found. Exiting.")
        return

    # Step 2: Test against RSS Bridge
    results = test_all_channels(channels)

    # Save results to file
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n[*] Full results saved to {OUTPUT_FILE}")

    # Print working channels summary
    if results['working']:
        print(f"\n{'=' * 60}")
        print(f"Working Channels ({len(results['working'])})")
        print(f"{'=' * 60}")
        for ch in results['working']:
            print(f"  {ch['name']} (@{ch['username']})")
            print(f"    RSS: {ch['rss_url']}")
            if ch.get('description'):
                print(f"    Type: {ch['description']}")
            print()

        # Step 3: Add to OpenCTI
        if OPENCTI_TOKEN != "YOUR_OPENCTI_API_TOKEN_HERE":
            add_all_to_opencti(results['working'])
        else:
            print("[!] OpenCTI token not configured. Set OPENCTI_TOKEN to add channels automatically.")
            print("    You can also add them manually using the RSS URLs above.")
    else:
        print("\n[!] No working channels found.")


if __name__ == '__main__':
    main()
