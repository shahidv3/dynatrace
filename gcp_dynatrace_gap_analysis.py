import csv
import math
import requests
import pandas as pd
from googleapiclient.discovery import build
import google.auth

# ===== CONFIGURATION =====
GCP_PROJECTS = [
    {"id": "project-1", "name": "Production"},
    {"id": "project-2", "name": "UAT"}
]

DYNATRACE_API_URL = "https://your-dynatrace-domain.com/api/v1/entity/infrastructure/hosts"
DYNATRACE_API_TOKEN = "<your_api_token>"


# ===== FETCH GCP INSTANCES =====
def get_gcp_instances(projects, credentials):
    compute = build('compute', 'v1', credentials=credentials)
    all_instances = []

    for proj in projects:
        project_id = proj["id"]
        project_name = proj["name"]
        print(f"📦 Fetching instances from project: {project_name}")

        request = compute.instances().aggregatedList(project=project_id)
        while request is not None:
            response = request.execute()
            for zone, instances_scoped_list in response.get('items', {}).items():
                for instance in instances_scoped_list.get('instances', []):
                    if instance['status'] != 'RUNNING':
                        continue

                    try:
                        machine_type = instance['machineType'].split('/')[-1]
                        zone_name = instance['zone'].split('/')[-1]
                        internal_ip = instance['networkInterfaces'][0]['networkIP']
                        metadata = {
                            "hostname": instance['name'].lower(),
                            "internal_ip": internal_ip.strip().lower(),
                            "project": project_name,
                            "zone": zone_name,
                            "machine_type": machine_type,
                            "status": instance['status'],
                            "ram_gb": None,
                            "vcpus": None
                        }
                        all_instances.append(metadata)
                    except Exception as e:
                        print(f"⚠️ Error parsing instance: {e}")
            request = compute.instances().aggregatedList_next(previous_request=request, previous_response=response)

    return pd.DataFrame(all_instances)


def get_machine_type_details(df, credentials):
    compute = build('compute', 'v1', credentials=credentials)
    for i, row in df.iterrows():
        try:
            resp = compute.machineTypes().get(
                project=row['project'],
                zone=row['zone'],
                machineType=row['machine_type']
            ).execute()
            df.at[i, 'ram_gb'] = round(resp.get('memoryMb', 0) / 1024, 2)
            df.at[i, 'vcpus'] = resp.get('guestCpus', 0)
        except Exception:
            df.at[i, 'ram_gb'] = 0
            df.at[i, 'vcpus'] = 0
    return df


# ===== FETCH DYNATRACE HOST IPs (v1 API) =====
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


# ===== GAP ANALYSIS BASED ON IP =====
def generate_gap_report(df, dynatrace_ip_set, dynatrace_ip_map):
    def check_monitored(row):
        ip = row.get("internal_ip")
        if ip and ip in dynatrace_ip_set:
            return True, dynatrace_ip_map[ip]
        else:
            return False, None

    df[["monitored_in_dynatrace", "dynatrace_host"]] = df.apply(
        lambda row: pd.Series(check_monitored(row)), axis=1
    )

    df["host_units"] = df["ram_gb"].apply(lambda ram: math.ceil(ram / 16) if ram else 0)

    monitored_df = df[df["monitored_in_dynatrace"]]
    unmonitored_df = df[~df["monitored_in_dynatrace"]]

    df.to_csv("gcp_dynatrace_gap_report.csv", index=False)
    unmonitored_df.to_csv("gcp_hosts_not_monitored.csv", index=False)

    summary = {
        "total_gcp_hosts": len(df),
        "total_host_units_all": df["host_units"].sum(),
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


# ===== MAIN =====
if __name__ == "__main__":
    print("🔍 Starting GCP-Dynatrace host gap analysis based on IP...")

    credentials, _ = google.auth.default()

    gcp_df = get_gcp_instances(GCP_PROJECTS, credentials)
    gcp_df = get_machine_type_details(gcp_df, credentials)

    dynatrace_ip_set, dynatrace_ip_map = get_dynatrace_host_ips()
    generate_gap_report(gcp_df, dynatrace_ip_set, dynatrace_ip_map)
