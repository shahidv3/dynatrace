# 🔍 Cloud Host Monitoring Gap Analysis & Host Unit Planning for OCI and GCP

## Overview

This solution provides a **unified monitoring gap analysis tool** for **Oracle Cloud Infrastructure (OCI)** and **Google Cloud Platform (GCP)** to:

- Identify VMs that are not being monitored by **Dynatrace**
- Estimate required **Host Units (HUs)** based on VM memory
- Generate actionable **CSV reports** for visibility and planning

---

## 🎯 Objectives

- Collect all **running virtual machines (VMs)** across OCI & GCP projects/compartments
- Fetch **monitored hosts** from Dynatrace (via v1 or v2 API)
- Match internal IPs to determine monitoring coverage
- Calculate **RAM**, **CPU**, **OS info**, and estimated **Dynatrace Host Units**
- Export data as structured **CSV reports** for decision making

---

## ☁️ Supported Platforms

- ✅ Oracle Cloud Infrastructure (OCI)
- ✅ Google Cloud Platform (GCP)
- ✅ Dynatrace (Self-Managed or SaaS)

---

## 🚀 Features

- Automatic discovery of **running compute instances**
- Extracts:
  - Internal IP
  - RAM (in GB/MB)
  - CPU count
  - OS type/version
  - Machine type
- Dynatrace integration:
  - Supports v1 API (`entity/infrastructure/hosts`) for monitored IPs
- Outputs:
  - Full instance inventory
  - Monitored vs. unmonitored split
  - Total required **Host Units**
- Exported as 3 detailed **CSV reports** per cloud

---

## 🧱 Prerequisites

### 🔐 Dynatrace API

- Dynatrace API Token with:
  - `entities.read`
  - `Read configuration` access
- Dynatrace Self-Managed or SaaS base URL

### 🔧 GCP

- `gcloud auth login` completed
- IAM role: `Viewer` or `Compute Viewer`
- Python packages:
  ```bash
  pip install google-api-python-client google-auth requests pandas


### 🔧 OCI

- OCI config set under ~/.oci/config or via instance principals
- IAM policy for:

`oci_compute_instance_read`
`oci_identity_compartment_read`

- Python packages:
  ``` bash
  pip install oci requests pandas
