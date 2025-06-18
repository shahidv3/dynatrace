import oci
import requests
import pandas as pd
from math import ceil

# ========== CONFIGURATION ==========
OCI_PROFILE = "DEFAULT"

COMPARTMENTS = [
    {"id": "<compartment-ocid-1>", "name": "Production"},
    {"id": "<compartment-ocid-2>", "name": "UAT"},
    {"id": "<compartment-ocid-3>", "name": "Dev"}
]

DYNATRACE_API_URL = "https://<your-env>.live.dynatrace.com/api/v2/entities"
DYNATRACE_API_TOKEN = "<your-dynatrace-api-token>"


# ========== FETCH OCI INSTANCES ==========
def get_oci_instances(compartments):
    config = oci.config.from_file(profile_name=OCI_PROFILE)
    compute_client = oci.core.ComputeClient(config)
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
                ram_gb = shape.memory_in_gbs if shape else 16  # fallback to 16 GB

                all_instances.append({
                    "hostname": instance.display_name,
                    "ram_gb": ram_gb,
                    "compartment_name": comp_name,
                    "compartment_id": comp_id
                })

        except Exception as e:
            print(f"❌ Error fetching from {comp_name}: {e}")

    return pd.DataFrame(all_instances)


# ========== FETCH DYNATRACE MONITORED HOSTS ==========
def get_dynatrace_hosts():
    headers = {
        "Authorization": f"Api-Token {DYNATRACE_API_TOKEN}"
    }

    response = requests.get(
        f"{DYNATRACE_API_URL}?entitySelector=type(HOST)&pageSize=500",
        headers=headers
    )

    entities = response.json().get("entities", [])
    return set(e.get("displayName") for e in entities)


# ========== GAP REPORT + HOST UNIT SUMMARY ==========
def generate_gap_and_host_unit_report(oci_df, dt_hostnames):
    oci_df["monitored_in_dynatrace"] = oci_df["hostname"].apply(lambda h: h in dt_hostnames)
    oci_df["host_units"] = oci_df["ram_gb"].apply(lambda ram: ceil(ram / 16))

    # Subsets
    monitored_df = oci_df[oci_df["monitored_in_dynatrace"]]
    unmonitored_df = oci_df[~oci_df["monitored_in_dynatrace"]]

    # Save detailed host list
    oci_df.to_csv("oci_dynatrace_gap_report.csv", index=False)
    unmonitored_df.to_csv("oci_hosts_not_monitored.csv", index=False)

    # Host Unit summary
    summary = {
        "total_oci_hosts": len(oci_df),
        "total_host_units_all": oci_df["host_units"].sum(),
        "monitored_hosts": len(monitored_df),
        "host_units_monitored": monitored_df["host_units"].sum(),
        "unmonitored_hosts": len(unmonitored_df),
        "host_units_unmonitored": unmonitored_df["host_units"].sum()
    }

    pd.DataFrame([summary]).to_csv("oci_host_unit_summary.csv", index=False)

    # Display
    print("✅ Gap analysis completed.")
    print(f"📝 Total OCI hosts found: {summary['total_oci_hosts']}")
    print(f"✅ Monitored in Dynatrace: {summary['monitored_hosts']} ({summary['host_units_monitored']} HUs)")
    print(f"❌ Not monitored in Dynatrace: {summary['unmonitored_hosts']} ({summary['host_units_unmonitored']} HUs)")
    print("📁 Files created:")
    print("   - oci_dynatrace_gap_report.csv")
    print("   - oci_hosts_not_monitored.csv")
    print("   - oci_host_unit_summary.csv")


# ========== MAIN ==========
if __name__ == "__main__":
    print("🔍 Starting OCI-Dynatrace gap analysis...")

    oci_hosts_df = get_oci_instances(COMPARTMENTS)
    dynatrace_hosts = get_dynatrace_hosts()

    generate_gap_and_host_unit_report(oci_hosts_df, dynatrace_hosts)
