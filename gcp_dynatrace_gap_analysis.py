import requests
import pandas as pd
from math import ceil
from googleapiclient import discovery
from google.auth import default

# ==== CONFIGURATION ====
DYNATRACE_API_URL = "https://your-dynatrace-domain.com/api/v1/entity/infrastructure/hosts"
DYNATRACE_API_TOKEN = "<your_dynatrace_api_token>"  # Replace with your token

GCP_PROJECTS = [
    "your-project-id-1",
    "your-project-id-2"
]

# ==== FETCH GCP INSTANCES ACROSS PROJECTS ====
def get_gcp_instances(projects):
    credentials, _ = default()
    all_instances = []

    for project in projects:
        print(f"\n🔄 Setting context to project: {project}")
        service = discovery.build('compute', 'v1', credentials=credentials)

        try:
            request = service.instances().aggregatedList(project=project)
            while request is not None:
                response = request.execute()
                print(f"  Retrieved page of instances for project {project} with {len(response.get('items',{}))} zones")

                for zone, zone_data in response.get('items', {}).items():
                    instances = zone_data.get('instances', [])
                    print(f"    Zone {zone} has {len(instances)} instances")

                    for inst in instances:
                        name = inst.get("name", "")
                        os_name = inst["disks"][0].get("licenses", ["Unknown"])[0].split("/")[-1]
                        network_interfaces = inst.get("networkInterfaces", [])
                        internal_ip = network_interfaces[0].get("networkIP", "").lower() if network_interfaces else None
                        status = inst.get("status", "UNKNOWN")

                        # RAM info
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
                            zone_name = zone_name if 'zone_name' in locals() else "unknown"

                        instance_info = {
                            "project_id": project,
                            "zone": zone_name,
                            "hostname": name,
                            "internal_ip": internal_ip,
                            "os": os_name,
                            "status": status,   # <-- VM status captured here
                            "ram_gb": ram_gb
                        }
                        print(f"      Adding instance: {instance_info}")
                        all_instances.append(instance_info)

                request = service.instances().aggregatedList_next(previous_request=request, previous_response=response)

        except Exception as e:
            print(f"❌ Error retrieving instances for project '{project}': {e}")

    df = pd.DataFrame(all_instances)
    print(f"\n🧮 Total instances collected: {len(df)}")
    print(df.head())
    return df

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

        print(f"\n🔢 Total Dynatrace hosts: {len(ip_set)}")
        return ip_set, ip_to_hostname

    except requests.exceptions.RequestException as e:
        print(f"❌ Dynatrace API error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"🔍 Response: {e.response.text}")
        return set(), {}

# ==== GAP ANALYSIS ====
def generate_gap_report(gcp_df, dynatrace_ip_set, dynatrace_ip_map):
    print("\n🔍 Starting gap analysis...")

    required_cols = [
        "hostname",
        "ram_gb",
        "internal_ip",
        "host_units",
        "monitored_in_dynatrace",
        "dynatrace_host",
        "status"
    ]

    for col in required_cols:
        if col not in gcp_df.columns:
            default_value = None
            if col == "monitored_in_dynatrace":
                default_value = False
            elif col == "dynatrace_host":
                default_value = ""
            gcp_df[col] = default_value
            print(f"⚠️ Column '{col}' missing, added with default {default_value}")

    print(f"Columns after check: {gcp_df.columns.tolist()}")

    print("\nVM status distribution:")
    print(gcp_df["status"].value_counts(dropna=False))

    def check_monitored(row):
        ip = row.get("internal_ip")
        print(f"Checking IP {ip} in Dynatrace IP set")
        if ip and ip in dynatrace_ip_set:
            host_name = dynatrace_ip_map.get(ip, "")
            print(f"  IP {ip} is monitored as {host_name}")
            return True, host_name
        else:
            print(f"  IP {ip} is NOT monitored")
            return False, ""

    monitored_status = gcp_df.apply(lambda row: check_monitored(row), axis=1)
    gcp_df["monitored_in_dynatrace"] = monitored_status.map(lambda x: x[0])
    gcp_df["dynatrace_host"] = monitored_status.map(lambda x: x[1])

    print("\nRAM GB sample values:")
    print(gcp_df["ram_gb"].head())

    def calc_host_units(row):
        ram = row.get("ram_gb", None)
        hostname = row.get("hostname", "<missing>")
        if pd.notnull(ram):
            hu = ceil(ram / 16)
            print(f"Calculating host units for RAM {ram} GB (host: {hostname}): {hu}")
            return hu
        else:
            print(f"No RAM info for row with hostname {hostname}")
            return None

    gcp_df["host_units"] = gcp_df.apply(calc_host_units, axis=1)

    print("\nHost units sample values:")
    print(gcp_df[["hostname", "ram_gb", "host_units"]].head())

    monitored_df = gcp_df[gcp_df["monitored_in_dynatrace"]]
    unmonitored_df = gcp_df[~gcp_df["monitored_in_dynatrace"]]

    summary = {
        "total_gcp_hosts": len(gcp_df),
        "total_host_units_all": gcp_df["host_units"].sum(skipna=True),
        "monitored_hosts": len(monitored_df),
        "host_units_monitored": monitored_df["host_units"].sum(skipna=True),
        "unmonitored_hosts": len(unmonitored_df),
        "host_units_unmonitored": unmonitored_df["host_units"].sum(skipna=True)
    }

    print("\n📝 VM Status Summary:")
    status_summary = gcp_df["status"].value_counts(dropna=False).to_dict()
    for st, count in status_summary.items():
        print(f"  {st}: {count}")

    gcp_df.to_csv("gcp_dynatrace_gap_report.csv", index=False)
    unmonitored_df.to_csv("gcp_hosts_not_monitored.csv", index=False)
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
    print("🚀 Starting GCP–Dynatrace host gap analysis...")
    gcp_df = get_gcp_instances(GCP_PROJECTS)
    dynatrace_ip_set, dynatrace_ip_map = get_dynatrace_host_ips()
    generate_gap_report(gcp_df, dynatrace_ip_set, dynatrace_ip_map)
