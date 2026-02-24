# ocp-bootstrap

Automated OpenShift 4.20 UPI cluster creation on vSphere in disconnected environments.

Replaces the manual 8-step creation process with a single command that takes you from zero to a running cluster ready for ArgoCD.

## What It Does

```
VLAN Manager ──> IP Calculation ──> Template Rendering ──> openshift-install ──> DNS ──> Terraform ──> CSR Approval
     │                │                     │                     │               │          │              │
  allocate        derive IPs          install-config.yaml    create manifests   nsupdate   apply plan    auto-approve
  segment         from subnet         terraform.tfvars       inject v4Subnet               create VMs    until Available
                                      dns-update.sh          create ignition
                                      ifcfg configs
```

## Prerequisites

- Python 3.9+
- `openshift-install-4.20` binary
- `terraform` binary
- `oc` CLI
- `nsupdate` (for DNS record creation)
- Access to VLAN Manager API
- Pull secret with artifactory credentials

## Quick Start

```bash
# Install Python dependencies
pip install -r requirements.txt

# Set required environment variables
export VSPHERE_PASSWORD="your-vcenter-password"
export DNS_TSIG_SECRET="your-dns-key-secret"

# Place your pull secret
cp /path/to/pull-secret.json config/pull-secret.json

# (Optional) Place your org CA bundle
cp /path/to/ca-bundle.pem config/additional-trust-bundle.pem

# Run the full bootstrap
python3 bootstrap.py --cluster-name mce-prod-01 --site site-a
```

## Usage

```bash
# Full automated run
python3 bootstrap.py --cluster-name mce-prod-01 --site site-a

# Generate configs only (no terraform, no DNS)
python3 bootstrap.py --cluster-name mce-prod-01 --site site-a --skip-terraform --skip-dns

# Provide segment directly (skip VLAN Manager)
python3 bootstrap.py --cluster-name mce-prod-01 --site site-a \
  --segment 10.0.5.0/24 --vlan-id 105

# Skip CSR approval (approve manually later)
python3 bootstrap.py --cluster-name mce-prod-01 --site site-a --skip-csr

# Use existing ignition files (re-run terraform only)
python3 bootstrap.py --cluster-name mce-prod-01 --site site-a --skip-ignition
```

## Project Structure

```
ocp-bootstrap/
├── bootstrap.py                 # Main CLI entrypoint
├── requirements.txt
├── config/
│   ├── sites/
│   │   ├── site-a.yaml          # Site profile (vcenter, dns, sizing, etc.)
│   │   └── site-b.yaml
│   ├── pull-secret.json         # Pull secret (with artifactory)
│   └── additional-trust-bundle.pem  # (optional) Org CA cert
└── templates/
    ├── install-config.yaml.j2   # OpenShift install config
    ├── terraform.tfvars.j2      # Terraform variables
    ├── v4-internal-subnet.yaml.j2  # v4InternalSubnet manifest
    ├── dns-update.sh.j2         # DNS record creation script
    └── ifcfg-ens192.j2          # Static network config for VMs
```

## Site Profiles

Each site gets a YAML profile in `config/sites/`. This eliminates hardcoded per-site values:

```yaml
site_name: site-a
vcenter: vcenter.site-a.example.local
datacenter: DC-SiteA
dns_servers: [10.100.0.10, 10.100.0.11]
gateway_offset: 254              # .254 in each subnet
infra_ip_offsets: [1, 2, 3]      # .1-.3 for infra
control_plane_ip_offsets: [4, 5, 6]  # .4-.6 for control plane
```

Sensitive values reference environment variables:
```yaml
vcenter_password_env: VSPHERE_PASSWORD    # reads $VSPHERE_PASSWORD
dns_key_secret_env: DNS_TSIG_SECRET       # reads $DNS_TSIG_SECRET
```

## IP Allocation

From an allocated segment (e.g., `10.0.5.0/24`):

| Offset | Role | Example IP |
|--------|------|------------|
| .1-.3 | Infra nodes | 10.0.5.1 - 10.0.5.3 |
| .4-.6 | Control plane | 10.0.5.4 - 10.0.5.6 |
| .7 | Bootstrap (temporary) | 10.0.5.7 |
| .8 | API VIP | 10.0.5.8 |
| .9 | Ingress VIP | 10.0.5.9 |
| .254 | Gateway | 10.0.5.254 |

All offsets are configurable per site profile.

## Output

After a successful run, you'll find everything under `/opt/ocp-clusters/<cluster-name>/`:

```
/opt/ocp-clusters/mce-prod-01/
├── auth/
│   ├── kubeconfig
│   └── kubeadmin-password
├── ignition/
│   ├── bootstrap.ign
│   ├── master.ign
│   └── worker.ign
├── install/                     # openshift-install working directory
├── install-config.yaml.backup   # Preserved install-config
├── terraform.tfvars             # Generated tfvars
├── dns-update.sh                # DNS creation script
├── v4-internal-subnet.yaml      # Injected manifest
├── cluster-context.yaml         # Full context (for Day2 tooling)
└── mce-prod-01-bootstrap.log    # Full log
```

## What Comes Next

This tool gets you to a running cluster. The next step is the Day2 bootstrap script that installs the OpenShift GitOps operator and configures ArgoCD to point at your GitOps repo, which then manages everything else (infra labeling, LDAP, MCE, operators, etc.).

## Network Configuration Note

The `ifcfg-ens192.j2` template and `terraform.tfvars.j2` both derive their network configuration (netmask, gateway, prefix length) from the single `segment` CIDR returned by the VLAN Manager. This eliminates the previous need to manually update hardcoded values in `ifcfg` files and `main.tf`.
