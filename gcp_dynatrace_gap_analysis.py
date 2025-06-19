import math
import requests
import pandas as pd
import google.auth
from googleapiclient.discovery import build

# -------- CONFIG --------
GCP_PROJECTS = [
    {"id": "your-project-id-1", "name": "Production"},
    {"id": "your-project-id-2", "name": "UAT"}
]

DYNATRACE_API_URL = "https://<your-env>.live.dynatrace.com/api/v1/entity/infrastructure/hosts"
DYNATRACE_API_TOKEN = "<your-dynatrace-api-token>"

# -------- GCP FUNCTIONS --------
def get_gcp_instances(project_id, credentials):
    service = build('compute', 'v1', credentials=credentials)
    request = service.instances().aggregatedList(project=project_id)
    all_vms = []

    while request is not None:
        response = request.execute()

        for zone, zone_data in response.get("items", {}).items():
            for instance in zone_data.get("instances", []):
                name = instance.get("name")
                status = instance.get("status")
                internal_ip = instance.get("networkInterfaces", [{}])[0].get("networkIP")
                machine_type_url = instance.get("machineType", "")
                machine_type = machine_type_url.split("/")[-1]
                zone_name = machine_type_url.split("/")[-3]

                # OS from license
                os_info = (
                    instance.get("disks", [{}])[0]
                    .get("licenses", ["unknown"])[0]
                    .split("/")[-1]
                )

                # RAM/vCPU info
                try:
                    mt_response = service.machineTypes().get(
                        project=project_id,
                        zone=zone_name,
                        machineType=machine_type
                    ).execute()
                    ram_mb = mt_response.get("memoryMb", 0)
                    ram_gb = round(ram_mb / 1024, 2)
                    vcpus = mt_response.get("guestCpus", 0)
                except Exception:
                    ram_mb = 0
                    ram_gb = 0
                    vcpus = 0

                all_vms.append({
                    "name": name,
                    "project": project_id,
                    "zone": zone_name,
                    "machine_type": machine_type,
                    "status": status,
                    "internal_ip": internal_ip,
                    "os": os_info,
                    "ram_mb": ram_mb,
                    "ram_gb": ram_gb,
                    "vcpus": vcpus
                })

        request = service.instances().aggregatedList_next(
            previous_request=request,
            previous_response=response
        )

    return all_vms

# -------- DYNATRACE --------
def get_dynatrace_internal_ips():
    headers = {"Authorization": f"Api-Token {DYNATRACE_API_TOKEN}"}
    ip_set = set()
    ip_map = {}

    try:
        response = requests.get(DYNATRACE_API_URL, headers=headers)
        response.raise_for_status()
        for host in response.json():
            hostname = host.get("displayName", "").strip().lower()
            for ip in host.get("ipAddresses", []):
                ip_clean = ip.strip().lower()
                ip_set.add(ip_clean)
                ip_map[ip_clean] = hostname
    except Exception as e:
        print(f"❌ Dynatrace API error: {e}")
    return ip_set, ip_map

# -------- MAIN --------
if __name__ == "__main__":
    print("🔍 Starting GCP–Dynatrace Gap Analysis...\n")
    credentials, _ = google.auth.default()

    all_instances = []
    for project in GCP_PROJECTS:
        print(f"📦 Fetching VMs from {project['name']} ({project['id']})...")
        all_instances += get_gcp_instances(project["id"], credentials)

    print("🌐 Fetching monitored hosts from Dynatrace...")
    dynatrace_ips, dynatrace_ip_map = get_dynatrace_internal_ips()

    print("📊 Matching & calculating Host Units...")
    for inst in all_instances:
        ip = (inst.get("internal_ip") or "").strip().lower()
        if ip in dynatrace_ips:
            inst["monitored"] = "Yes"
            inst["dynatrace_host"] = dynatrace_ip_map.get(ip, "")
            inst["required_hu"] = 0
        else:
            inst["monitored"] = "No"
            inst["dynatrace_host"] = ""
            inst["required_hu"] = math.ceil(inst.get("ram_gb", 0) / 16) if inst.get("ram_gb") else 0

    df_all = pd.DataFrame(all_instances)

    df_unmonitored = df_all[df_all["monitored"] == "No"].copy()

    summary_data = {
        "total_vms": len(df_all),
        "monitored_vms": (df_all["monitored"] == "Yes").sum(),
        "unmonitored_vms": (df_all["monitored"] == "No").sum(),
        "required_hus_unmonitored": df_unmonitored["required_hu"].sum()
    }
    df_summary = pd.DataFrame([summary_data])

    # -------- EXPORTS --------
    df_all.to_csv("gcp_dynatrace_gap_report.csv", index=False)
    df_unmonitored.to_csv("gcp_hosts_not_monitored.csv", index=False)
    df_summary.to_csv("gcp_host_unit_summary.csv", index=False)

    print("\n✅ Reports generated:")
    print("📄 gcp_dynatrace_gap_report.csv (all VMs)")
    print("📄 gcp_hosts_not_monitored.csv (unmonitored VMs)")
    print("📄 gcp_host_unit_summary.csv (summary)")
