# Dynatrace–OCI Monitoring Gap Analysis

This Python script helps identify gaps between **Oracle Cloud Infrastructure (OCI)** compute instances and **Dynatrace-monitored hosts**, and calculates required **host units** for unmonitored systems.

---

## 🔍 What It Does

- Connects to **OCI** and fetches all **running compute instances** from multiple compartments
- Connects to **Dynatrace API** and lists all currently **monitored hosts**
- Compares both lists to identify **unmonitored instances**
- Calculates **host units** required (based on RAM)
- Outputs clean CSV reports for visibility and planning

---

## 📁 Output Files

| File Name | Description |
|-----------|-------------|
| `oci_dynatrace_gap_report.csv` | Full list of OCI compute instances with monitoring status and host unit count |
| `oci_hosts_not_monitored.csv` | Subset of instances missing from Dynatrace |
| `oci_host_unit_summary.csv` | Summary of total/monitored/unmonitored hosts and host units |

---

## ⚙️ Requirements

Install dependencies with:

```bash
pip install -r requirements.txt
