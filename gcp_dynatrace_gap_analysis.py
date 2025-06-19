import csv
import math
import requests
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

                # OS information
                os_info = (
                    instance.get("disks", [{}])[0]
                    .get("licenses", ["unknown"])[0]
                    .split("/")[-1]
                )

                # RAM & CPU
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
                    "status": status,
                    "internal_ip": internal_ip,
                    "machine_type": machine_type,
                    "os": os_info,
                    "vcpus": vcpus,
                    "ram_mb": ram_mb,
                    "ram_gb": ram_gb
                })

        request = service.instances().aggregatedList_next(
            previous_request=request,
            previous_response=response
        )

    return all_vms


# -------- DYNATRACE FUNCTIONS --------
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


# -------- MATCHING + GAP ANALYSIS --------
def match_and_report(all_instances, dynatrace_ips, dynatrace_map):
    matched = []
    unmatched = []

    for inst in all_instances:
        ip = (inst.get("internal_ip") or "").strip().lower()
        if ip in dynatrace_ips:
            inst["monitored"] = "Yes"
            inst["dynatrace_host"] = dynatrace_map.get(ip)
            matched.append(inst)
        else:
            inst["monitored"] = "No"
            inst["dynatrace_host"] = ""
            inst["required_hu"] = math.ceil(inst["ram_gb"] / 16) if inst["ram_gb"] else 0
            unmatched.append(inst)

    # CSV: Full report
    write_csv("gcp_dynatrace_gap_report.csv", all_instances, [
        "name", "project", "zone", "machine_type", "internal_ip", "status",
        "os", "vcpus", "ram_mb", "ram_gb", "monitored", "dynatrace_host"
    ])

    # CSV: Unmonitored only
    write_csv("gcp_hosts_not_monitored.csv", unmatched, [
        "name", "project", "zone", "machine_type", "internal_ip", "status",
        "os", "vcpus", "ram_mb", "ram_gb", "required_hu"
    ])

    # CSV: Summary
    summary = {
        "total_vms": len(all_instances),
        "monitored_vms": len(matched),
        "unmonitored_vms": len(unmatched),
        "required_hus_unmonitored": sum(i.get("required_hu", 0) for i in unmatched)
    }
    write_csv("gcp_host_unit_summary.csv", [summary], summary.keys())

    print("\n✅ GAP ANALYSIS DONE")
    print(f"🔢 Total VMs: {summary['total_vms']}")
    print(f"✅ Monitored: {summary['monitored_vms']}")
    print(f"❌ Unmonitored: {summary['unmonitored_vms']} (HUs needed: {summary['required_hus_unmonitored']})")


def write_csv(filename, data, fieldnames):
    with open(filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)


# -------- MAIN --------
if __name__ == "__main__":
    print("🔍 Starting GCP-Dynatrace Gap Analysis...\n")
    credentials, _ = google.auth.default()

    all_instances = []
    for project in GCP_PROJECTS:
        print(f"📦 Fetching VMs from {project['name']} ({project['id']})...")
        all_instances += get_gcp_instances(project["id"], credentials)

    print("🌐 Fetching monitored hosts from Dynatrace...")
    dynatrace_ips, dynatrace_ip_map = get_dynatrace_internal_ips()

    print("📊 Matching & generating gap reports...")
    match_and_report(all_instances, dynatrace_ips, dynatrace_ip_map)
