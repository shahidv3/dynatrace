import requests

# ===== Configuration =====
DYNATRACE_API_TOKEN = "<your_api_token>"
DYNATRACE_BASE_URL = "https://your-dynatrace-domain.com"  # No trailing slash

# ===== Headers =====
headers = {
    "Authorization": f"Api-Token {DYNATRACE_API_TOKEN}"
}

# ===== Dynatrace API Endpoint =====
url = f"{DYNATRACE_BASE_URL}/api/v2/entities"

params = {
    "entitySelector": "type(HOST)",
    "fields": "properties.ipAddresses,displayName",
    "pageSize": 500
}

# ===== Fetch and Print Hosts =====
def fetch_host_ips():
    print("📡 Fetching monitored hosts and IP addresses from Dynatrace...\n")

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        entities = response.json().get("entities", [])
        if not entities:
            print("⚠️  No hosts found.")
            return

        for entity in entities:
            hostname = entity.get("displayName", "N/A")
            ip_list = entity.get("properties", {}).get("ipAddresses", [])

            print(f"🖥️  Host: {hostname}")
            if ip_list:
                for ip in ip_list:
                    print(f"   └─ IP: {ip}")
            else:
                print("   └─ No IPs found")

    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching data from Dynatrace API: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"🔍 Response content: {e.response.text}")

# ===== Main =====
if __name__ == "__main__":
    fetch_host_ips()
