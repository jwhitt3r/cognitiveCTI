#!/usr/bin/env python3
"""
Add TLP:AMBER marking to all Telegram RSS feeds in OpenCTI
============================================================
Finds all RSS feeds with "Telegram" in the name and patches
them with the TLP:AMBER marking definition.

Usage:
    python3 fix_telegram_tlp.py
"""

import requests
import time

# ============================================================
# CONFIGURATION
# ============================================================

OPENCTI_URL = "https://YOUR_OPENCTI_URL/graphql"
OPENCTI_TOKEN = "YOUR_OPENCTI_TOKEN"  # Replace with your token
DRY_RUN = False # Set to False to apply changes

# ============================================================

HEADERS = {
    "Authorization": f"Bearer {OPENCTI_TOKEN}",
    "Content-Type": "application/json"
}


def get_tlp_amber_id():
    """Find the TLP:AMBER marking definition ID."""
    query = """
    query {
      markingDefinitions {
        edges {
          node {
            id
            definition
            definition_type
          }
        }
      }
    }
    """
    resp = requests.post(
        f"{OPENCTI_URL}/graphql",
        json={"query": query},
        headers=HEADERS,
        timeout=10
    )
    data = resp.json()
    edges = data.get("data", {}).get("markingDefinitions", {}).get("edges", [])

    print("Available markings:")
    for e in edges:
        node = e["node"]
        print(f"  {node['definition']} -> {node['id']}")

    for e in edges:
        node = e["node"]
        if 'amber' in node["definition"].lower():
            return node["id"]

    return None


def get_telegram_feeds():
    """Get all RSS feeds with Telegram in the name."""
    query = """
    query {
      ingestionRsss {
        edges {
          node {
            id
            name
            uri
          }
        }
      }
    }
    """
    resp = requests.post(
        f"{OPENCTI_URL}/graphql",
        json={"query": query},
        headers=HEADERS,
        timeout=10
    )
    data = resp.json()
    edges = data.get("data", {}).get("ingestionRsss", {}).get("edges", [])
    feeds = [e["node"] for e in edges]

    return [f for f in feeds if 'telegram' in f['name'].lower()]


def add_marking(feed_id, marking_id):
    """Patch a feed with the TLP marking."""
    query = """
    mutation FixMarking($id: ID!, $input: [EditInput!]!) {
      ingestionRssFieldPatch(id: $id, input: $input) {
        id
        name
      }
    }
    """
    variables = {
        "id": feed_id,
        "input": [{"key": "object_marking_refs", "value": [marking_id]}]
    }
    resp = requests.post(
        f"{OPENCTI_URL}/graphql",
        json={"query": query, "variables": variables},
        headers=HEADERS,
        timeout=10
    )
    data = resp.json()
    if "errors" in data:
        return False, data["errors"][0].get("message", "Unknown error")
    return True, "Updated"


def main():
    print("=" * 60)
    print("Add TLP:AMBER to Telegram RSS Feeds")
    print(f"Dry run: {DRY_RUN}")
    print("=" * 60)

    # Step 1: Find TLP:AMBER ID
    print("\n[*] Looking up TLP:AMBER marking ID...\n")
    amber_id = get_tlp_amber_id()

    if not amber_id:
        print("\n[!] TLP:AMBER not found. Check your marking definitions.")
        return

    print(f"\n[*] TLP:AMBER ID: {amber_id}\n")

    # Step 2: Find Telegram feeds
    feeds = get_telegram_feeds()
    print(f"[*] Found {len(feeds)} Telegram feeds\n")

    if not feeds:
        print("[!] No Telegram feeds found.")
        return

    if DRY_RUN:
        print("[DRY RUN] Would update:\n")
        for f in feeds:
            print(f"  {f['name']}")
        print(f"\nSet DRY_RUN = False to apply.")
        return

    # Step 3: Patch each feed
    updated = 0
    errors = 0

    for i, f in enumerate(feeds):
        print(f"  [{i+1}/{len(feeds)}] {f['name']}...", end=" ", flush=True)
        success, msg = add_marking(f["id"], amber_id)

        if success:
            print("OK")
            updated += 1
        else:
            print(f"ERROR - {msg}")
            errors += 1

        time.sleep(0.3)

    print(f"\n[*] Done: {updated} updated, {errors} errors")


if __name__ == "__main__":
    main()