import oci
import requests
import pandas as pd
from math import ceil

# ===== CONFIGURATION =====
OCI_PROFILE = "DEFAULT"  # Use your OCI CLI profile name

COMPARTMENTS = [
    {"id": "ocid1.compartment.oc1..aaaa...", "name": "Production"},
    {"id": "ocid1.compartment.oc1..bbbb...", "name": "UAT"},
    {"id": "ocid1.compartment.oc1..cccc...", "name": "Dev"}
]

DYNATRACE_API_URL = "https://<your-dynatrace-server>/api/v2/entities"
DYNATRACE_API_TOKEN = "<your-dynatrace-api-token>"


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

                # Get OS name via image details
                os_name = "Unknown"
                try:
                    if instance_details.image_id:
                        image_details = compute_client.get_image(instance_details.image_id).data
                        os_name = image_details.operating_system or "Unknown"
                except Exception:
                    pass

                # Get VNIC for internal FQDN
                vnic_attachments = compute_client.list_vnic_attachments(
                    compartment_id=comp_id, instance_id=instance.id
                ).data
                internal_fqdn = None

                if vnic_attachments:
                    vnic_id = vnic_attachments[0].vnic_id
                    vnic = virtual_network_client.get_vnic(vnic_id).data

                    hostname_label = vnic.hostname_label
                    private_ip = vnic.private_ip
                    internal_fqdn = hostname_label if hostname_label else private_ip
                else:
                    internal_fqdn = instance.display_name

                all_instances.append({
                    "hostname": instance.display_name,
                    "internal_fqdn": internal_fqdn.lower() if internal_fqdn else None,
                    "os": os_name,
                    "ram_gb": ram_gb,
                    "compartment_name": comp_name
                })

        except Exception as e:
            print(f"❌ Error in {comp_name}: {e}")

    return pd.DataFrame(all_instances)


# ===== FETCH DYNATRACE HOSTS =====
def get_dynatrace_hosts():
    headers = {
        "Authorization": f"Api-Token {DYNATRACE_API_TOKEN}"
    }

    try:
        response = requests.get(
            f"{DYNATRACE_API_URL}?entitySelector=type(HOST)&pageSize=500",
            headers=headers
        )
        response.raise_for_status()
        entities = response.json().get("entities", [])
        return set(e.get("displayName").lower() for e in entities if e.get("displayName"))

    except requests.exceptions.RequestException as e:
        print(f"❌ Dynatrace API error: {e}")
        return set()


# ===== COMPARE & REPORT =====
def generate_gap_and_host_unit_report(oci_df, dt_hostnames):
    def is_monitored(row):
        target = row["internal_fqdn"] if row["internal_fqdn"] else row["hostname"]
        return target.lower() in dt_hostnames

    oci_df["monitored_in_dynatrace"] = oci_df.apply(is_monitored, axis=1)
    oci_df["host_units"] = oci_df["ram_gb"].apply(lambda ram: ceil(ram / 16))

    monitored_df = oci_df[oci_df["monitored_in_dynatrace"]]
    unmonitored_df = oci_df[~oci_df["monitored_in_dynatrace"]]

    # Save CSVs
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
    print("🔍 Starting Dynatrace–OCI Monitoring Gap Analysis...")
    oci_hosts_df = get_oci_instances(COMPARTMENTS)
    dynatrace_hosts = get_dynatrace_hosts()
    generate_gap_and_host_unit_report(oci_hosts_df, dynatrace_hosts)
