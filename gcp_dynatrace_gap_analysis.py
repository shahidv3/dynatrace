import requests
import pandas as pd
from math import ceil
from googleapiclient import discovery
from google.auth import default

# ==== CONFIGURATION ====
DYNATRACE_API_URL = "https://your-dynatrace-domain.com/api/v1/entity/infrastructure/hosts"
DYNATRACE_API_TOKEN = "<your_dynatrace_api_token>"
GCP_PROJECT = "<your-gcp-project-id>"
GCP_ZONES = ["us-central1-a", "us-central1-b"]  # Add your zones here


# ==== GCP INSTANCE FETCH ====
def get_gcp_instances():
    credentials, _ = default()
    service = discovery.build('compute', 'v1', credentials=credentials)
    all_instances = []

    for zone in GCP_ZONES:
        print(f"📦 Fetching GCP VMs from zone: {zone}")
        result = service.instances().list(project=GCP_PROJECT, zone=zone).execute()
        instances = result.get("items", [])

        for inst in instances:
            name = inst["name"]
            os_name = inst["disks"][0]["licenses"][0].split("/")[-1] if "licenses" in inst["disks"][0] else "Unknown"
            ram_mb = inst["machineType"].split("/")[-1]  # e.g., n1-standard-4
            ram_gb = _estimate_ram_from_machine_type(ram_mb)
            network_interfaces = inst.get("networkInterfaces", [])
            internal_ip = network_interfaces[0].get("networkIP", "").lower() if network_interfaces else None

            all_instances.append({
                "hostname": name,
                "internal_ip": internal_ip,
                "os": os_name,
                "ram_gb": ram_gb,
                "zone": zone
            })

    return pd.DataFrame(all_instances)


def _estimate_ram_from_machine_type(machine_type):
    # This is a simplified RAM estimator. Adjust based on your actual GCP pricing/machine types.
    mapping = {
        "n1-standard-1": 3.75,
        "n1-standard-2": 7.5,
        "n1-standard-4": 15,
        "n1-standard-8": 30,
        "n1-standard-16": 60,
        "n2-standard-4": 16,
        "n2-standard-8": 32,
        "e2-medium": 4,
        "e2-standard-2": 8,
    }
    return mapping.get(machine_type, 16)


# ==== FETCH DYNATRACE MONITORED HOSTS ====
def get_dynatrace_host_ips():
    headers = {
        "Authorization": f"Api-Token {DYNATRACE_API_TOKEN}"
    }

    try:
        response = requests.get(DYNATRACE_API_URL, headers=headers)
        response.raise_for_status()
        hosts = response.json()

        ip_set = set()
        ip_to_hostname = {}

        print("\n📡 Dynatrace monitored hosts:")
        for host in hosts:
            display_name = host.get("displayName", "N/A").strip().lower()
            ip_addresses = host.get("ipAddresses", [])
            if ip_addresses:
                for ip in ip_addresses:
                    ip_clean = ip.strip().lower()
                    ip_set.add(ip_clean)
                    ip_to_hostname[ip_clean] = display_name
                    print(f"🖥️  {display_name} → {ip_clean}")
            else:
                print(f"⚠️  {display_name} has no IPs")

        return ip_set, ip_to_hostname

    except requests.exceptions.RequestException as e:
        print(f"❌ Dynatrace API error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"🔍 Response: {e.response.text}")
        return set(), {}


# ==== GAP ANALYSIS ====
def generate_gap_report(gcp_df, dynatrace_ip_set, dynatrace_ip_map):
    def check_monitored(row):
        ip = row.get("internal_ip")
        if ip and ip in dynatrace_ip_set:
            return True, dynatrace_ip_map[ip]
        else:
            return False, None

    gcp_df[["monitored_in_dynatrace", "dynatrace_host"]] = gcp_df.apply(
        lambda row: pd.Series(check_monitored(row)), axis=1
    )

    gcp_df["host_units"] = gcp_df["ram_gb"].apply(lambda ram: ceil(ram / 16))

    monitored_df = gcp_df[gcp_df["monitored_in_dynatrace"]]
    unmonitored_df = gcp_df[~gcp_df["monitored_in_dynatrace"]]

    gcp_df.to_csv("gcp_dynatrace_gap_report.csv", index=False)
    unmonitored_df.to_csv("gcp_hosts_not_monitored.csv", index=False)

    summary = {
        "total_gcp_hosts": len(gcp_df),
        "total_host_units_all": gcp_df["host_units"].sum(),
        "monitored_hosts": len(monitored_df),
        "host_units_monitored": monitored_df["host_units"].sum(),
        "unmonitored_hosts": len(unmonitored_df),
        "host_units_unmonitored": unmonitored_df["host_units"].sum()
    }

    pd.DataFrame([summary]).to_csv("gcp_host_unit_summary.csv", index=False)

    print("\n✅ Gap analysis completed.")
    print(f"🔢 Total GCP hosts: {summary['total_gcp_hosts']}")
    print(f"✅ Monitored: {summary['monitored_hosts']} ({summary['host_units_monitored']} HUs)")
    print(f"❌ Not Monitored: {summary['unmonitored_hosts']} ({summary['host_units_unmonitored']} HUs)")
    print("📁 Output files:")
    print("  - gcp_dynatrace_gap_report.csv")
    print("  - gcp_hosts_not_monitored.csv")
    print("  - gcp_host_unit_summary.csv")


# ==== MAIN ====
if __name__ == "__main__":
    print("🔍 Starting GCP-Dynatrace host gap analysis based on IP...")
    gcp_df = get_gcp_instances()
    dynatrace_ip_set, dynatrace_ip_map = get_dynatrace_host_ips()
    generate_gap_report(gcp_df, dynatrace_ip_set, dynatrace_ip_map)
