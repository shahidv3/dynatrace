import csv
import math
import requests
import google.auth
from googleapiclient.discovery import build

# ---------- CONFIGURATION ----------
GCP_PROJECTS = ['project-1', 'project-2']  # Your list of GCP projects
DT_API_TOKEN = 'dt_api_token_here'
DT_ENV_URL = 'https://<your-env>.live.dynatrace.com'

# ---------- FUNCTIONS ----------

def get_gcp_instances(project_id, credentials):
    compute = build('compute', 'v1', credentials=credentials)
    result = []

    request = compute.instances().aggregatedList(project=project_id)
    while request is not None:
        response = request.execute()
        for zone, instances_scoped_list in response.get('items', {}).items():
            for instance in instances_scoped_list.get('instances', []):
                if instance['status'] != 'RUNNING':
                    continue
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
    matched, unmatched = [], []
    dynatrace_ips = {ip for h in dynatrace_hosts for ip in h.get('ipAddresses', [])}
    for inst in gcp_instances:
        if inst['internal_ip'] in dynatrace_ips:
            matched.append(inst)
        else:
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

# Use credentials from gcloud auth login
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

print("Writing CSVs...")
write_csv('monitored_hosts.csv', monitored, ['name', 'internal_ip', 'project', 'zone', 'machine_type', 'vcpus', 'ram_mb', 'status'])
write_csv('unmonitored_hosts.csv', unmonitored, ['name', 'internal_ip', 'project', 'zone', 'machine_type', 'vcpus', 'ram_mb', 'ram_gb', 'required_hu', 'status'])

print("✅ Analysis complete. CSVs generated.")
