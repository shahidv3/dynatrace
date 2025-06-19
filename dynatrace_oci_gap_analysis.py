import oci
import requests
import pandas as pd
from math import ceil

# ===== CONFIGURATION =====
OCI_PROFILE = "DEFAULT"

COMPARTMENTS = [
    {"id": "ocid1.compartment.oc1..aaaa...", "name": "Production"},
    {"id": "ocid1.compartment.oc1..bbbb...", "name": "UAT"}
]

DYNATRACE_API_URL = "https://your-dynatrace-domain.com/api/v1/entity/infrastructure/hosts"
DYNATRACE_API_TOKEN = "<your_api_token>"


# ===== FETCH OCI INSTANCES =====
def get_oci_instances(compartments):
    config = oci.config.from_file(profile_name=OCI_PROFILE)
    compute_client = oci.core.ComputeClient(config)
    virtual_network_client = oci.core.VirtualNetworkClient(config)
    all_instances = []

    for comp in compartments:
        comp_id = comp["id"]
        comp_name = comp["name"]
        print(f"📦 Fetching instances from compartment: {comp_name}")

        try:
            instances = compute_client.list_instances(
                compartment_id=comp_id,
                lifecycle_state="RUNNING"
            ).data

            for instance in instances:
                shape = instance.shape_config
                ram_gb = shape.memory_in_gbs if shape else 16

                os_name = "Unknown"
                try:
                    if instance.image_id:
                        image_details = compute_client.get_image(instance.image_id).data
                        os_name = image_details.operating_system or "Unknown"
                except Exception:
                    pass

                # VNIC info
                vnic_attachments = compute_client.list_vnic_attachments(
                    compartment_id=comp_id, instance_id=instance.id
                ).data

                internal_ip = None
                hostname_label = None

                if vnic_attachments:
                    vnic_id = vnic_attachments[0].vnic_id
                    vnic = virtual_network_client.get_vnic(vnic_id).data
                    internal_ip = vnic.private_ip.strip().lower() if vnic.private_ip else None
                    hostname_label = vnic.hostname_label.strip().lower() if vnic.hostname_label else None

                all_instances.append({
                    "hostname": instance.display_name,
                    "hostname_label": hostname_label,
                    "internal_ip": internal_ip,
                    "os": os_name,
                    "ram_gb": ram_gb,
                    "compartment_name": comp_name
                })

        except Exception as e:
            print(f"❌ Error in {comp_name}: {e}")

    return pd.DataFrame(all_instances)


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
def generate_gap_report(oci_df, dynatrace_ip_set, dynatrace_ip_map):
    def check_monitored(row):
        ip = row.get("internal_ip")
        if ip and ip in dynatrace_ip_set:
            return True, dynatrace_ip_map[ip]
        else:
            return False, None

    oci_df[["monitored_in_dynatrace", "dynatrace_host"]] = oci_df.apply(
        lambda row: pd.Series(check_monitored(row)), axis=1
    )

    oci_df["host_units"] = oci_df["ram_gb"].apply(lambda ram: ceil(ram / 16))

    monitored_df = oci_df[oci_df["monitored_in_dynatrace"]]
    unmonitored_df = oci_df[~oci_df["monitored_in_dynatrace"]]

    oci_df.to_csv("oci_dynatrace_gap_report.csv", index=False)
    unmonitored_df.to_csv("oci_hosts_not_monitored.csv", index=False)

    summary = {
        "total_oci_hosts": len(oci_df),
        "total_host_units_all": oci_df["host_units"].sum(),
        "monitored_hosts": len(monitored_df),
        "host_units_monitored": monitored_df["host_units"].sum(),
        "unmonitored_hosts": len(unmonitored_df),
        "host_units_unmonitored": unmonitored_df["host_units"].sum()
    }

    pd.DataFrame([summary]).to_csv("oci_host_unit_summary.csv", index=False)

    print("\n✅ Gap analysis completed.")
    print(f"🔢 Total OCI hosts: {summary['total_oci_hosts']}")
    print(f"✅ Monitored: {summary['monitored_hosts']} ({summary['host_units_monitored']} HUs)")
    print(f"❌ Not Monitored: {summary['unmonitored_hosts']} ({summary['host_units_unmonitored']} HUs)")
    print("📁 Output files:")
    print("  - oci_dynatrace_gap_report.csv")
    print("  - oci_hosts_not_monitored.csv")
    print("  - oci_host_unit_summary.csv")


# ===== MAIN =====
if __name__ == "__main__":
    print("🔍 Starting OCI-Dynatrace host gap analysis based on IP...")
    oci_df = get_oci_instances(COMPARTMENTS)
    dynatrace_ip_set, dynatrace_ip_map = get_dynatrace_host_ips()
    generate_gap_report(oci_df, dynatrace_ip_set, dynatrace_ip_map)
