import csv
import math
import requests
import google.auth
from googleapiclient.discovery import build

# ---------- CONFIGURATION ----------
GCP_PROJECTS = ['project-1', 'project-2']
DT_API_TOKEN = 'dt_api_token_here'
DT_ENV_URL = 'https://<your-env>.live.dynatrace.com'  # Replace with your Dynatrace URL

# ---------- FUNCTIONS ----------

def get_gcp_instances(project_id, credentials):
    compute = build('compute', 'v1', credentials=credentials)
    result = []

    request = compute.instances().aggregatedList(project=project_id)
    while request is not None:
        response = request.execute()
        for zone, instances_scoped_list in response.get('items', {}).items():
            for instance in instances_scoped_list.get('instances', []):
                machine_type = instance['machineType'].split('/')[-1]
                metadata = {
                    'name': instance['name'],
                    'zone': instance['zone'].split('/')[-1],
                    'project': project_id,
                    'machine_type': machine_type,
                    'internal_ip': instance['networkInterfaces'][0]['networkIP'],
                    'status': instance['status'],
                    'ram_mb': None,
                    'vcpus': None
                }
                result.append(metadata)
        request = compute.instances().aggregatedList_next(previous_request=request, previous_response=response)
    return result

def get_machine_type_details(project_id, zone, machine_type, credentials):
    compute = build('compute', 'v1', credentials=credentials)
    type_info = compute.machineTypes().get(project=project_id, zone=zone, machineType=machine_type).execute()
    return type_info.get('memoryMb'), type_info.get('guestCpus')

def enrich_instance_with_specs(instances, credentials):
    for inst in instances:
        try:
            ram, vcpus = get_machine_type_details(inst['project'], inst['zone'], inst['machine_type'], credentials)
            inst['ram_mb'] = ram
            inst['vcpus'] = vcpus
        except Exception:
            inst['ram_mb'] = 0
            inst['vcpus'] = 0
    return instances

def fetch_dynatrace_hosts():
    headers = {
        'Authorization': f'Api-Token {DT_API_TOKEN}'
    }
    entities = []
    url = f'{DT_ENV_URL}/api/v2/entities'
    params = {
        'entitySelector': 'type("HOST")',
        'pageSize': 400
    }
    while url:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        entities.extend(data.get('entities', []))
        next_page = data.get('nextPageKey')
        if next_page:
            url = f'{DT_ENV_URL}/api/v2/entities?nextPageKey={next_page}'
            params = None
        else:
            break
    return entities

def match_instances(gcp_instances, dynatrace_hosts):
    dynatrace_ips = {ip for h in dynatrace_hosts for ip in h.get('ipAddresses', [])}
    monitored, unmonitored = [], []

    for inst in gcp_instances:
        if inst['internal_ip'] in dynatrace_ips:
            inst['monitored'] = True
            monitored.append(inst)
        else:
            inst['monitored'] = False
            if inst['status'] == 'RUNNING':
                inst['ram_gb'] = round(inst['ram_mb'] / 1024, 2)
                inst['required_hu'] = math.ceil(inst['ram_mb'] / 1024 / 16)
                unmonitored.append(inst)
    return monitored, unmonitored

def write_csv(filename, data, fields=None):
    if not data:
        print(f"[INFO] No data to write for {filename}")
        return

    # Auto-detect fields if not provided
    if fields is None:
        fields = sorted({k for row in data for k in row.keys()})

    with open(filename, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)

# ---------- MAIN ----------

credentials, _ = google.auth.default()

all_instances = []
for project in GCP_PROJECTS:
    print(f"Fetching instances for project: {project}")
    instances = get_gcp_instances(project, credentials)
    all_instances.extend(instances)

print("Enriching instance specs...")
enriched_instances = enrich_instance_with_specs(all_instances, credentials)

print("Fetching Dynatrace monitored hosts...")
dynatrace_hosts = fetch_dynatrace_hosts()

print("Matching monitored vs unmonitored...")
monitored, unmonitored = match_instances(enriched_instances, dynatrace_hosts)

# Ensure 'monitored' field is populated for all enriched instances
monitored_ips = {h['internal_ip'] for h in monitored}
for inst in enriched_instances:
    inst['monitored'] = inst['internal_ip'] in monitored_ips

print("Writing CSV reports...")

# 1. Full report with monitoring status
write_csv('gcp_dynatrace_gap_report.csv', enriched_instances)

# 2. Unmonitored and running only
write_csv('gcp_hosts_not_monitored.csv', unmonitored)

# 3. Summary report
summary = [{
    'total_instances': len(enriched_instances),
    'monitored_hosts': len(monitored),
    'unmonitored_hosts': len(unmonitored),
    'total_required_host_units': sum(inst.get('required_hu', 0) for inst in unmonitored),
}]
write_csv('gcp_host_unit_summary.csv', summary)

print("✅ Reports generated:")
print(" - gcp_dynatrace_gap_report.csv")
print(" - gcp_hosts_not_monitored.csv")
print(" - gcp_host_unit_summary.csv")
