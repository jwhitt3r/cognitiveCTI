import requests
import json

# --- CONFIGURATION ---
OPENCTI_URL = "https://YOUR_OPENCTI_URL/graphql"
OPENCTI_TOKEN = "YOUR_OPENCTI_TOKEN"
OUTPUT_FILE = "opencti_integrations.txt"
# ---------------------

headers = {
    "Authorization": f"Bearer {OPENCTI_TOKEN}",
    "Content-Type": "application/json"
}

# Define the GraphQL query
query = """
query GetData {
  connectors {
    id
    name
    type
    active
    connector_scope
  }
  feeds(first: 100) {
    edges {
      node {
        name
        type
        url
      }
    }
  }
}
"""

def fetch_data():
    try:
        response = requests.post(OPENCTI_URL, json={'query': query}, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if "errors" in data:
            print("GraphQL Error:", data['errors'])
            return None
            
        return data['data']
    except Exception as e:
        print(f"Connection failed: {e}")
        return None

def write_to_file(data):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        # 1. Dump Connectors
        f.write("=== OPENCTI CONNECTORS ===\n")
        connectors = data.get('connectors', [])
        if connectors:
            for c in connectors:
                status = "Active" if c['active'] else "Inactive"
                scope = ", ".join(c['connector_scope']) if c['connector_scope'] else "No scope"
                f.write(f"- {c['name']} ({c['type']})\n")
                f.write(f"  Status: {status} | Scope: {scope}\n\n")
        else:
            f.write("No connectors found.\n\n")

        # 2. Dump Feeds
        f.write("=== RSS / CSV / TAXII FEEDS ===\n")
        feeds_edges = data.get('feeds', {}).get('edges', [])
        if feeds_edges:
            for edge in feeds_edges:
                feed = edge['node']
                f.write(f"- {feed['name']} ({feed['type']})\n")
                f.write(f"  URL: {feed['url']}\n\n")
        else:
            f.write("No feeds found.\n")

    print(f"Successfully exported to {OUTPUT_FILE}")

if __name__ == "__main__":
    data = fetch_data()
    if data:
        write_to_file(data)