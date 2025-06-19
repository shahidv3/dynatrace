from googleapiclient import discovery
from google.auth import default
import pandas as pd

# Replace with your GCP project ID(s)
PROJECT_ID = "your-project-id"

def list_gcp_vms(project_id):
    credentials, _ = default()
    service = discovery.build('compute', 'v1', credentials=credentials)
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

                # Get RAM (in MB) from machine type
                try:
                    mt_response = service.machineTypes().get(
                        project=project_id,
                        zone=zone_name,
                        machineType=machine_type
                    ).execute()
                    ram_mb = mt_response.get("memoryMb", 0)
                    ram_gb = round(ram_mb / 1024, 2)
                except Exception:
                    ram_gb = None

                all_vms.append({
                    "name": name,
                    "zone": zone_name,
                    "status": status,
                    "internal_ip": internal_ip,
                    "machine_type": machine_type,
                    "ram_gb": ram_gb
                })

        request = service.instances().aggregatedList_next(
            previous_request=request,
            previous_response=response
        )

    return pd.DataFrame(all_vms)


if __name__ == "__main__":
    df = list_gcp_vms(PROJECT_ID)
    print(df)
    df.to_csv("gcp_vm_inventory.csv", index=False)
    print("\n✅ VM list saved to gcp_vm_inventory.csv")
