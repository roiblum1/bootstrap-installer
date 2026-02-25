import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict

import yaml

from .constants import DEFAULT_WORK_DIR, CLUSTERS_DIR, TERRAFORM_DIR
from .csr import approve_csrs
from .dns import create_wildcard_dns_via_api
from .installer import create_ignition_configs, create_manifests, inject_v4_internal_subnet
from .network import allocate_vlan, calculate_ips
from .renderer import build_template_context, render_templates
from .site import load_site_profile
from .terraform import run_terraform, run_terraform_destroy
from .utils import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap OpenShift 4.20 UPI cluster on vSphere (disconnected)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Full bootstrap (ignition + DNS + terraform + CSR approval):
    %(prog)s --config config/clusters/my-cluster-01.yaml

  Generate configs only, skip terraform (useful for review/dry-run):
    %(prog)s --config config/clusters/my-cluster-01.yaml --skip-terraform

  Re-run terraform only (ignition already exists):
    %(prog)s --config config/clusters/my-cluster-01.yaml --skip-ignition --skip-dns

  Re-run with a custom working directory:
    %(prog)s --config config/clusters/my-cluster-01.yaml --work-dir /tmp/ocp-dry-run

  Destroy a previously bootstrapped cluster:
    %(prog)s --config config/clusters/my-cluster-01.yaml --destroy

  Extend the CSR approval window to 60 minutes:
    %(prog)s --config config/clusters/my-cluster-01.yaml --csr-timeout 60
        """,
    )

    parser.add_argument("--config", required=True,
                        help="Path to cluster config YAML (config/clusters/<name>.yaml)")
    parser.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR),
                        help=f"Base working directory (default: {DEFAULT_WORK_DIR})")

    # Destroy
    parser.add_argument("--destroy", action="store_true",
                        help="Destroy the cluster (runs terraform destroy using existing tfvars)")

    # Skip flags (runtime control — not in the cluster config)
    parser.add_argument("--skip-dns", action="store_true",
                        help="Skip DNS record creation")
    parser.add_argument("--skip-terraform", action="store_true",
                        help="Skip terraform apply (generate configs only)")
    parser.add_argument("--skip-csr", action="store_true",
                        help="Skip CSR approval loop")
    parser.add_argument("--skip-ignition", action="store_true",
                        help="Skip openshift-install steps (use existing ignition)")
    parser.add_argument("--csr-timeout", type=int, default=45,
                        help="CSR approval timeout in minutes (default: 45)")

    return parser.parse_args()


def validate_cluster_name(name: str) -> None:
    if len(name) > 27:
        print(f"ERROR: Cluster name '{name}' exceeds 27 characters")
        sys.exit(1)
    if not all(c.isalnum() or c == "-" for c in name):
        print(f"ERROR: Cluster name '{name}' contains invalid characters")
        sys.exit(1)
    if name.startswith("-") or name.endswith("-"):
        print(f"ERROR: Cluster name '{name}' cannot start or end with a hyphen")
        sys.exit(1)


def print_summary(
    cluster_name: str,
    profile: Dict[str, Any],
    ip_info: Dict[str, Any],
    vlan_id: str,
    segment: str,
    cluster_dir: Path,
    logger: logging.Logger,
) -> None:
    summary = f"""
{'='*70}
  CLUSTER BOOTSTRAP COMPLETE: {cluster_name}
{'='*70}

  Site:             {profile['site_name']}
  Segment:          {segment}
  Gateway:          {ip_info['gateway']}

  Control Plane:    {', '.join(ip_info['control_plane_ips'])}  (api / api-int)
  Infra Nodes:      {', '.join(ip_info['infra_ips'])}  (*.apps ingress)
  Compute Nodes:    {', '.join(ip_info['compute_ips']) if ip_info['compute_ips'] else '(none)'}
  Bootstrap:        {ip_info['bootstrap_ip']}

  Kubeconfig:       {cluster_dir}/auth/kubeconfig
  Install Config:   {cluster_dir}/install-config.yaml.backup
  Terraform vars:   {cluster_dir}/terraform.tfvars
  Log file:         {cluster_dir}/{cluster_name}-bootstrap.log

  Next steps:
    1. export KUBECONFIG={cluster_dir}/auth/kubeconfig
    2. oc get nodes
    3. Run Day2 bootstrap (GitOps operator + ArgoCD)
{'='*70}
"""
    logger.info(summary)


def main() -> None:
    args = parse_args()

    # Load cluster config
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: Cluster config not found: {config_path}")
        available = list(CLUSTERS_DIR.glob("*.yaml")) if CLUSTERS_DIR.exists() else []
        if available:
            print(f"Available clusters: {[f.stem for f in available]}")
        sys.exit(1)

    with open(config_path) as f:
        cluster_cfg = yaml.safe_load(f) or {}

    cluster_name = cluster_cfg.get("cluster_name")
    site = cluster_cfg.get("site")
    if not cluster_name:
        print("ERROR: 'cluster_name' is required in the cluster config")
        sys.exit(1)
    if not site:
        print("ERROR: 'site' is required in the cluster config")
        sys.exit(1)

    validate_cluster_name(cluster_name)

    work_dir = Path(args.work_dir)
    cluster_dir = work_dir / cluster_name
    install_dir = cluster_dir / "install"
    ignition_dir = cluster_dir / "ignition"
    tfstate_path = cluster_dir / "terraform.tfstate"
    cluster_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(cluster_name, cluster_dir)
    logger.info(f"=== Starting bootstrap for cluster: {cluster_name} ===")
    logger.info(f"Config: {config_path} | Site: {site} | Work dir: {cluster_dir}")

    # Step 1: Three-layer merge — defaults → site → cluster config
    profile = load_site_profile(site)
    cluster_overrides = {k: v for k, v in cluster_cfg.items() if k not in ("cluster_name", "site")}
    profile.update(cluster_overrides)
    logger.info(f"Profile loaded: defaults → site:{site} → cluster:{cluster_name}")

    # Destroy path — short-circuit before any provisioning steps
    if args.destroy:
        existing_tfvars = cluster_dir / "terraform.tfvars"
        if not existing_tfvars.exists():
            logger.error(
                f"No terraform.tfvars found at {existing_tfvars}. Run bootstrap first."
            )
            sys.exit(1)
        run_terraform_destroy(
            terraform_bin=profile.get("terraform_bin", "terraform"),
            terraform_dir=profile.get("terraform_dir", str(TERRAFORM_DIR)),
            tfvars_path=existing_tfvars,
            tfstate_path=tfstate_path,
            plugin_dir=profile.get("terraform_plugin_dir") or None,
            logger=logger,
        )
        return

    # Step 2: Resolve segment / VLAN (from cluster config or VLAN Manager)
    segment = cluster_cfg.get("segment")
    vlan_id = str(cluster_cfg.get("vlan_id", "0"))
    if segment:
        logger.info(f"Using segment={segment}, vlan_id={vlan_id} from cluster config")
    else:
        segment, vlan_id = allocate_vlan(
            cluster_name=cluster_name,
            site=site,
            vlan_manager_url=profile["vlan_manager_url"],
            vrf=profile.get("vlan_manager_vrf", "default"),
            logger=logger,
        )

    # Step 3: Calculate IPs
    ip_info = calculate_ips(segment, profile, logger)

    # Step 4: Render templates
    ctx = build_template_context(
        cluster_name=cluster_name,
        profile=profile,
        ip_info=ip_info,
        segment=segment,
        vlan_id=vlan_id,
        cluster_dir=cluster_dir,
    )
    outputs = render_templates(ctx, cluster_dir, logger)

    # Step 5: OpenShift installer
    if not args.skip_ignition:
        install_bin = profile.get("openshift_install_bin", "openshift-install-4.20")
        create_manifests(install_bin, install_dir, logger)
        inject_v4_internal_subnet(outputs["v4-internal-subnet"], install_dir, logger)
        create_ignition_configs(install_bin, install_dir, ignition_dir, logger)
    else:
        logger.info("Skipping openshift-install steps (--skip-ignition)")

    # Step 6: Wildcard DNS via API (api/api-int handled by Terraform exec provisioner)
    if not args.skip_dns:
        wildcard_dns_url = profile.get("wildcard_dns_api_url")
        if not wildcard_dns_url:
            logger.error(
                "No wildcard DNS endpoint configured. "
                "Set wildcard_dns_api_url in the site or cluster config."
            )
            sys.exit(1)
        try:
            create_wildcard_dns_via_api(cluster_name, wildcard_dns_url, logger)
        except RuntimeError as e:
            logger.error(str(e))
            logger.error("You can retry later: re-run with --skip-terraform --skip-ignition")
    else:
        logger.info("Skipping DNS record creation (--skip-dns)")

    # Step 7: Terraform
    if not args.skip_terraform:
        run_terraform(
            terraform_bin=profile.get("terraform_bin", "terraform"),
            terraform_dir=profile.get("terraform_dir", str(TERRAFORM_DIR)),
            tfvars_path=outputs["terraform.tfvars"],
            tfstate_path=tfstate_path,
            plugin_dir=profile.get("terraform_plugin_dir") or None,
            logger=logger,
        )

        # Step 8: CSR approval
        kubeconfig = cluster_dir / "auth" / "kubeconfig"
        if not args.skip_csr:
            approve_csrs(kubeconfig, logger, timeout_minutes=args.csr_timeout)
        else:
            logger.info("Skipping CSR approval loop (--skip-csr)")
    else:
        logger.info("Skipping terraform apply (--skip-terraform)")

    # Summary + save context
    print_summary(cluster_name, profile, ip_info, vlan_id, segment, cluster_dir, logger)

    ctx_dump = {k: v for k, v in ctx.items() if isinstance(v, (str, int, float, list, dict, bool))}
    ctx_file = cluster_dir / "cluster-context.yaml"
    with open(ctx_file, "w") as f:
        yaml.dump(ctx_dump, f, default_flow_style=False)
    logger.info(f"Saved cluster context -> {ctx_file}")
