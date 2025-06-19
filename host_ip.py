import requests

# ==== Configuration ====
DYNATRACE_API_TOKEN = "<your_api_token>"
DYNATRACE_BASE_URL = "https://your-dynatrace-domain.com"  # No trailing slash

headers = {
    "Authorization": f"Api-Token {DYNATRACE_API_TOKEN}"
}

url = f"{DYNATRACE_BASE_URL}/api/v1/entity/infrastructure/hosts"

def fetch_hosts_v1():
    print("📡 Fetching monitored hosts and IPs from Dynatrace v1 API...\n")

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        hosts = response.json()

        for host in hosts:
            display_name = host.get("displayName", "N/A")
            ip_addresses = host.get("ipAddresses", [])

            print(f"🖥️  Host: {display_name}")
            if ip_addresses:
                for ip in ip_addresses:
                    print(f"   └─ IP: {ip}")
            else:
                print("   └─ No IPs listed")

    except requests.exceptions.RequestException as e:
        print(f"❌ Error calling Dynatrace API: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"🔍 Response content: {e.response.text}")

# Run
if __name__ == "__main__":
    fetch_hosts_v1()
