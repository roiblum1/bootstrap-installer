import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict

import yaml

from .constants import DEFAULT_WORK_DIR
from .csr import approve_csrs
from .dns import create_wildcard_dns_via_api
from .installer import create_ignition_configs, create_manifests, inject_v4_internal_subnet
from .network import allocate_vlan, calculate_ips
from .renderer import build_template_context, render_templates
from .site import load_site_profile
from .terraform import run_terraform
from .utils import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap OpenShift 4.20 UPI cluster on vSphere (disconnected)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --cluster-name mce-prod-01 --site site-a
  %(prog)s --cluster-name mce-prod-01 --site site-a --segment 10.0.5.0/24
  %(prog)s --cluster-name mce-prod-01 --site site-a --segment 10.0.5.0/24 --vlan-id 105
        """,
    )

    parser.add_argument("--cluster-name", required=True,
                        help="Cluster name (max 27 chars, alphanumeric/hyphen)")
    parser.add_argument("--site", required=True,
                        help="Site profile name (matches config/sites/<name>.yaml)")
    parser.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR),
                        help=f"Base working directory (default: {DEFAULT_WORK_DIR})")

    # Network - skip VLAN Manager
    parser.add_argument("--segment", default=None,
                        help="Provide segment CIDR directly (skip VLAN Manager)")
    parser.add_argument("--vlan-id", default=None,
                        help="Provide VLAN ID directly (optional when --segment is set)")

    # Wildcard DNS API
    parser.add_argument("--wildcard-dns-url", default=None,
                        help="Endpoint to POST for *.apps wildcard DNS record creation "
                             "(overrides site profile wildcard_dns_api_url)")

    # Skip flags
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
  VLAN ID:          {vlan_id}
  Segment:          {segment}
  Gateway:          {ip_info['gateway']}

  Control Plane:    {', '.join(ip_info['control_plane_ips'])}  (api / api-int)
  Infra Nodes:      {', '.join(ip_info['infra_ips'])}  (*.apps ingress)
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
    validate_cluster_name(args.cluster_name)

    work_dir = Path(args.work_dir)
    cluster_dir = work_dir / args.cluster_name
    install_dir = cluster_dir / "install"
    ignition_dir = cluster_dir / "ignition"

    cluster_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(args.cluster_name, cluster_dir)
    logger.info(f"=== Starting bootstrap for cluster: {args.cluster_name} ===")
    logger.info(f"Site: {args.site} | Work dir: {cluster_dir}")

    # Step 1: Load site profile
    profile = load_site_profile(args.site)
    logger.info(f"Loaded site profile: {args.site}")

    # Step 2: Resolve segment / VLAN
    if args.segment:
        segment = args.segment
        vlan_id = args.vlan_id or "0"
        logger.info(f"Using provided segment={segment}, vlan_id={vlan_id}")
    else:
        segment, vlan_id = allocate_vlan(
            cluster_name=args.cluster_name,
            site=args.site,
            vlan_manager_url=profile["vlan_manager_url"],
            vrf=profile.get("vlan_manager_vrf", "default"),
            logger=logger,
        )

    # Step 3: Calculate IPs
    ip_info = calculate_ips(segment, profile, logger)

    # Step 4: Render templates
    ctx = build_template_context(
        cluster_name=args.cluster_name,
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
        wildcard_dns_url = args.wildcard_dns_url or profile.get("wildcard_dns_api_url")
        if not wildcard_dns_url:
            logger.error(
                "No wildcard DNS endpoint configured. "
                "Set --wildcard-dns-url or wildcard_dns_api_url in the site profile."
            )
            sys.exit(1)
        try:
            create_wildcard_dns_via_api(args.cluster_name, wildcard_dns_url, logger)
        except RuntimeError as e:
            logger.error(str(e))
            logger.error("You can retry later: re-run with --skip-terraform --skip-ignition")
    else:
        logger.info("Skipping DNS record creation (--skip-dns)")

    # Step 7: Terraform
    if not args.skip_terraform:
        run_terraform(
            terraform_bin=profile.get("terraform_bin", "terraform"),
            terraform_dir=profile.get("terraform_dir", "/opt/ocp-terraform"),
            tfvars_path=outputs["terraform.tfvars"],
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
    print_summary(args.cluster_name, profile, ip_info, vlan_id, segment, cluster_dir, logger)

    ctx_dump = {k: v for k, v in ctx.items() if isinstance(v, (str, int, float, list, dict, bool))}
    ctx_file = cluster_dir / "cluster-context.yaml"
    with open(ctx_file, "w") as f:
        yaml.dump(ctx_dump, f, default_flow_style=False)
    logger.info(f"Saved cluster context -> {ctx_file}")
