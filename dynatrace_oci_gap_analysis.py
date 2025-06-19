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

DYNATRACE_API_URL = "https://<your-dynatrace-url>/api/v2/entities"
DYNATRACE_API_TOKEN = "<your-api-token>"


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
                instance_details = compute_client.get_instance(instance.id).data
                shape = instance_details.shape_config
                ram_gb = shape.memory_in_gbs if shape else 16

                # Get OS
                os_name = "Unknown"
                try:
                    if instance_details.image_id:
                        image_details = compute_client.get_image(instance_details.image_id).data
                        os_name = image_details.operating_system or "Unknown"
                except Exception:
                    pass

                # VNIC
                vnic_attachments = compute_client.list_vnic_attachments(
                    compartment_id=comp_id, instance_id=instance.id
                ).data

                hostname_label = None
                if vnic_attachments:
                    vnic_id = vnic_attachments[0].vnic_id
                    vnic = virtual_network_client.get_vnic(vnic_id).data
                    hostname_label = vnic.hostname_label.strip().lower() if vnic.hostname_label else None

                all_instances.append({
                    "hostname": instance.display_name,
                    "hostname_label": hostname_label,
                    "os": os_name,
                    "ram_gb": ram_gb,
                    "compartment_name": comp_name
                })

        except Exception as e:
            print(f"❌ Error in {comp_name}: {e}")

    return pd.DataFrame(all_instances)


# ===== FETCH DYNATRACE HOSTNAMES =====
def get_dynatrace_hostnames():
    headers = {
        "Authorization": f"Api-Token {DYNATRACE_API_TOKEN}"
    }

    hostname_set = set()
    try:
        response = requests.get(
            f"{DYNATRACE_API_URL}?entitySelector=type(HOST)&pageSize=500",
            headers=headers
        )
        response.raise_for_status()
        entities = response.json().get("entities", [])
        for entity in entities:
            name = entity.get("displayName", "").strip().lower()
            if name:
                hostname_set.add(name)
        return hostname_set

    except requests.exceptions.RequestException as e:
        print(f"❌ Dynatrace API error: {e}")
        return set()


# ===== GAP ANALYSIS =====
def generate_gap_report(oci_df, dynatrace_hostnames):
    def is_monitored(row):
        label = row.get("hostname_label")
        if label and label in dynatrace_hostnames:
            return True
        print(f"🔍 Not found in Dynatrace: {label}")
        return False

    oci_df["monitored_in_dynatrace"] = oci_df.apply(is_monitored, axis=1)
    oci_df["host_units"] = oci_df["ram_gb"].apply(lambda ram: ceil(ram / 16))

    monitored_df = oci_df[oci_df["monitored_in_dynatrace"]]
    unmonitored_df = oci_df[~oci_df["monitored_in_dynatrace"]]

    oci_df.to_csv("oci_dynatrace_gap_report_hostname.csv", index=False)
    unmonitored_df.to_csv("oci_hosts_not_monitored_hostname.csv", index=False)

    summary = {
        "total_oci_hosts": len(oci_df),
        "total_host_units_all": oci_df["host_units"].sum(),
        "monitored_hosts": len(monitored_df),
        "host_units_monitored": monitored_df["host_units"].sum(),
        "unmonitored_hosts": len(unmonitored_df),
        "host_units_unmonitored": unmonitored_df["host_units"].sum()
    }

    pd.DataFrame([summary]).to_csv("oci_host_unit_summary_hostname.csv", index=False)

    print("\n✅ Hostname-based gap analysis complete.")
    print(f"🔢 Total OCI hosts: {summary['total_oci_hosts']}")
    print(f"✅ Monitored: {summary['monitored_hosts']} ({summary['host_units_monitored']} HUs)")
    print(f"❌ Unmonitored: {summary['unmonitored_hosts']} ({summary['host_units_unmonitored']} HUs)")
    print("📁 Output files:")
    print("  - oci_dynatrace_gap_report_hostname.csv")
    print("  - oci_hosts_not_monitored_hostname.csv")
    print("  - oci_host_unit_summary_hostname.csv")


# ===== MAIN =====
if __name__ == "__main__":
    print("🔍 Starting hostname-based OCI–Dynatrace gap analysis...")
    oci_df = get_oci_instances(COMPARTMENTS)
    dynatrace_hostnames = get_dynatrace_hostnames()
    generate_gap_report(oci_df, dynatrace_hostnames)
