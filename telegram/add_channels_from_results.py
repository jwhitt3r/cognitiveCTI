#!/usr/bin/env python3
"""
Add Working Telegram Channels to OpenCTI from Saved Results
=============================================================
Reads telegram_channels_results.json (saved by the scanner)
and adds any working channels to OpenCTI. Skips duplicates.

Usage:
    python3 add_channels_from_results.py
"""

import json
import time
import requests
from urllib.parse import quote

# ============================================================
# CONFIGURATION
# ============================================================

OPENCTI_URL = "http://OPENCTI_URL:OPENCTI_PORT"
OPENCTI_TOKEN = ""  # Replace with your opencti token
RESULTS_FILE = "telegram_channels_results.json"
DRY_RUN = False # Set to False to actually add

# ============================================================

HEADERS = {
    "Authorization": f"Bearer {OPENCTI_TOKEN}",
    "Content-Type": "application/json"
}


def add_to_opencti(channel):
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

    # Ensure URL uses host IP not docker hostname
    rss_url = channel.get('rss_url', '')
    rss_url = rss_url.replace('rss-bridge:80', 'HOST IP:3000') # Insert your own Host IP

    variables = {
        "input": {
            "name": feed_name,
            "description": f"Telegram channel: {channel['username']} - {channel.get('description', 'Threat actor channel')}",
            "uri": rss_url,
            "report_types": ["threat-report"],
            "object_marking_refs": [],
            "ingestion_running": True
        }
    }

    try:
        resp = requests.post(
            f"{OPENCTI_URL}/graphql",
            json={"query": query, "variables": variables},
            headers=HEADERS,
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


def main():
    print("=" * 60)
    print("Add Telegram Channels to OpenCTI from Saved Results")
    print(f"Dry run: {DRY_RUN}")
    print("=" * 60)

    try:
        with open(RESULTS_FILE, 'r') as f:
            results = json.load(f)
    except FileNotFoundError:
        print(f"\n[!] {RESULTS_FILE} not found.")
        print("    Run telegram_channel_scanner.py first.")
        return

    working = results.get('working', [])
    print(f"\n[*] Found {len(working)} working channels in {RESULTS_FILE}\n")

    if not working:
        print("[!] No working channels to add.")
        return

    if DRY_RUN:
        print("[DRY RUN] Would add:\n")
        for ch in working:
            url = ch.get('rss_url', '').replace('rss-bridge:80', 'LOCALHOST:3000')
            print(f"  {ch['name']} (@{ch['username']})")
            print(f"    URL: {url}\n")
        print(f"\nSet DRY_RUN = False to apply.")
        return

    created = 0
    existed = 0
    errors = 0

    for i, ch in enumerate(working):
        print(f"  [{i+1}/{len(working)}] {ch['name']}...", end=" ", flush=True)
        status, msg = add_to_opencti(ch)

        if status == 'created':
            print("CREATED")
            created += 1
        elif status == 'exists':
            print("SKIP (already exists)")
            existed += 1
        else:
            print(f"ERROR - {msg}")
            errors += 1

        time.sleep(0.5)

    print(f"\n[*] Done: {created} created, {existed} skipped, {errors} errors")


if __name__ == "__main__":
    main()
