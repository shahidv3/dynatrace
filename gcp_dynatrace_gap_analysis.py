import requests
import pandas as pd
from math import ceil
from googleapiclient import discovery
from google.auth import default

# ==== CONFIGURATION ====
DYNATRACE_API_URL = "https://your-dynatrace-domain.com/api/v1/entity/infrastructure/hosts"
DYNATRACE_API_TOKEN = "<your_dynatrace_api_token>"
GCP_PROJECTS = ["your-project-id-1", "your-project-id-2"]  # Replace with your actual GCP project IDs


# ==== FETCH GCP INSTANCES ACROSS ALL ZONES ====
def get_gcp_instances():
    credentials, _ = default()
    all_instances = []

    for project in GCP_PROJECTS:
        print(f"\n🔎 Fetching instances for project: {project}")
        service = discovery.build('compute', 'v1', credentials=credentials)

        try:
            request = service.instances().aggregatedList(project=project)
            while request is not None:
                response = request.execute()
                for zone, zone_data in response.get('items', {}).items():
                    instances = zone_data.get('instances', [])
                    for inst in instances:
                        name = inst.get("name", "")
                        os_name = inst["disks"][0].get("licenses", ["Unknown"])[0].split("/")[-1]
                        network_interfaces = inst.get("networkInterfaces", [])
                        internal_ip = network_interfaces[0].get("networkIP", "").lower() if network_interfaces else None
                        status = inst.get("status", "UNKNOWN")

                        # RAM info (optional)
                        ram_gb = None
                        try:
                            machine_type_url = inst["machineType"]
                            machine_type_name = machine_type_url.split("/")[-1]
                            zone_name = machine_type_url.split("/")[-3]
                            machine_type = service.machineTypes().get(
                                project=project,
                                zone=zone_name,
                                machineType=machine_type_name
                            ).execute()
                            if "memoryMb" in machine_type:
                                ram_mb = machine_type["memoryMb"]
                                ram_gb = round(ram_mb / 1024, 2)
                        except Exception as e:
                            print(f"⚠️ Could not fetch machine type RAM for {name}: {e}")

                        all_instances.append({
                            "project_id": project,
                            "zone": zone_name,
                            "hostname": name,
                            "internal_ip": internal_ip,
                            "os": os_name,
                            "status": status,
                            "ram_gb": ram_gb
                        })

                request = service.instances().aggregatedList_next(previous_request=request, previous_response=response)

        except Exception as e:
            print(f"❌ Error retrieving instances for {project}: {e}")

    return pd.DataFrame(all_instances)


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
            return True, dynatrace_ip_map.get(ip, "")
        else:
            return False, ""

    monitored_status = gcp_df.apply(lambda row: check_monitored(row), axis=1)
    gcp_df["monitored_in_dynatrace"] = monitored_status.map(lambda x: x[0])
    gcp_df["dynatrace_host"] = monitored_status.map(lambda x: x[1])

    gcp_df["host_units"] = gcp_df["ram_gb"].apply(lambda ram: ceil(ram / 16) if pd.notnull(ram) else None)

    monitored_df = gcp_df[gcp_df["monitored_in_dynatrace"]]
    unmonitored_df = gcp_df[~gcp_df["monitored_in_dynatrace"]]

    gcp_df.to_csv("gcp_dynatrace_gap_report.csv", index=False)
    unmonitored_df.to_csv("gcp_hosts_not_monitored.csv", index=False)

    summary = {
        "total_gcp_hosts": len(gcp_df),
        "total_host_units_all": gcp_df["host_units"].sum(skipna=True),
        "monitored_hosts": len(monitored_df),
        "host_units_monitored": monitored_df["host_units"].sum(skipna=True),
        "unmonitored_hosts": len(unmonitored_df),
        "host_units_unmonitored": unmonitored_df["host_units"].sum(skipna=True)
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
    print("🔍 Starting GCP-Dynatrace host gap analysis using aggregated instance list...")
    gcp_df = get_gcp_instances()
    dynatrace_ip_set, dynatrace_ip_map = get_dynatrace_host_ips()
    generate_gap_report(gcp_df, dynatrace_ip_set, dynatrace_ip_map)
