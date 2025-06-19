import csv
import math
import requests
import google.auth
from googleapiclient.discovery import build

# ---------- CONFIGURATION ----------
GCP_PROJECTS = ['project-1', 'project-2']  # You can update this list dynamically or pass via CLI
DT_API_TOKEN = 'dt_api_token_here'
DT_ENV_URL = 'https://<your-env>.live.dynatrace.com'  # For SaaS, e.g., https://abc123.live.dynatrace.com

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
    try:
        compute = build('compute', 'v1', credentials=credentials)
        type_info = compute.machineTypes().get(project=project_id, zone=zone, machineType=machine_type).execute()
        return type_info.get('memoryMb'), type_info.get('guestCpus')
    except Exception as e:
        print(f"Warning: Could not fetch machine type details for {machine_type} in {project_id}/{zone}: {e}")
        return 0, 0

def enrich_instance_with_specs(instances, credentials):
    for inst in instances:
        ram, vcpus = get_machine_type_details(inst['project'], inst['zone'], inst['machine_type'], credentials)
        inst['ram_mb'] = ram
        inst['vcpus'] = vcpus
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
    try:
        while url:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            entities.extend(data.get('entities', []))
            next_page = data.get('nextPageKey')
            if next_page:
                url = f'{DT_ENV_URL}/api/v2/entities?nextPageKey={next_page}'
                params = None
            else:
                break
    except Exception as e:
        print(f"Error fetching Dynatrace hosts: {e}")
    return entities

def match_instances(gcp_instances, dynatrace_hosts):
    matched, unmatched = [], []
    dynatrace_ips = {ip for h in dynatrace_hosts for ip in h.get('ipAddresses', [])}
    for inst in gcp_instances:
        if inst['internal_ip'] in dynatrace_ips:
            inst['monitored'] = True
            matched.append(inst)
        else:
            inst['monitored'] = False
            if inst['status'] == 'RUNNING':
                inst['ram_gb'] = round(inst['ram_mb'] / 1024, 2)
                inst['required_hu'] = math.ceil(inst['ram_mb'] / 1024 / 16)
                unmatched.append(inst)
    return matched, unmatched

def write_csv(filename, data, fields):
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

print("Writing CSV reports...")

# 1. Full list of all VMs with monitoring info
write_csv(
    'gcp_dynatrace_gap_report.csv',
    enriched_instances,
    ['name', 'internal_ip', 'project', 'zone', 'machine_type', 'vcpus', 'ram_mb', 'status', 'monitored']
)

# 2. Only unmonitored and running VMs
write_csv(
    'gcp_hosts_not_monitored.csv',
    unmonitored,
    ['name', 'internal_ip', 'project', 'zone', 'machine_type', 'vcpus', 'ram_mb', 'ram_gb', 'required_hu', 'status']
)

# 3. Summary report
summary = [{
    'total_gcp_instances': len(enriched_instances),
    'monitored_hosts': len(monitored),
    'unmonitored_hosts': len(unmonitored),
    'total_required_host_units': sum(inst['required_hu'] for inst in unmonitored),
}]

write_csv(
    'gcp_host_unit_summary.csv',
    summary,
    ['total_gcp_instances', 'monitored_hosts', 'unmonitored_hosts', 'total_required_host_units']
)

print("✅ Analysis complete. CSV reports generated:")
print(" - gcp_dynatrace_gap_report.csv")
print(" - gcp_hosts_not_monitored.csv")
print(" - gcp_host_unit_summary.csv")
