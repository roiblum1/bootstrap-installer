import ipaddress
import logging
import sys
from typing import Any, Dict, Tuple

import requests


def allocate_vlan(
    cluster_name: str,
    site: str,
    vlan_manager_url: str,
    vrf: str,
    logger: logging.Logger,
) -> Tuple[str, str]:
    """Allocate VLAN segment via VLAN Manager API."""
    endpoint = f"{vlan_manager_url.rstrip('/')}/api/allocate-vlan"
    payload = {"cluster_name": cluster_name, "site": site, "vrf": vrf}

    logger.info(f"Allocating VLAN from {endpoint} for cluster={cluster_name}, site={site}")

    try:
        response = requests.post(endpoint, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()

        segment = data.get("segment")
        vlan_id = str(data.get("vlan_id"))

        if not segment or not vlan_id:
            logger.error(f"Invalid VLAN Manager response: {data}")
            sys.exit(1)

        logger.info(f"Allocated VLAN {vlan_id} with segment {segment}")
        return segment, vlan_id

    except requests.exceptions.RequestException as e:
        logger.error(f"VLAN Manager API error: {e}")
        sys.exit(1)


def calculate_ips(
    segment: str,
    profile: Dict[str, Any],
    logger: logging.Logger,
) -> Dict[str, Any]:
    """
    Calculate all IPs from the allocated segment and site profile offsets.

    Default convention:
        .1-.3  = infra nodes       (ingress — *.apps DNS round-robin)
        .4-.6  = control plane     (API — api/api-int DNS round-robin)
        .7     = bootstrap
        .254   = gateway
    No VIPs — DNS round-robin across all nodes in each role.
    """
    network = ipaddress.ip_network(segment, strict=False)
    net_addr = network.network_address

    gateway = str(net_addr + profile.get("gateway_offset", 254))
    infra_ips = [str(net_addr + o) for o in profile.get("infra_ip_offsets", [1, 2, 3])]
    cp_ips = [str(net_addr + o) for o in profile.get("control_plane_ip_offsets", [4, 5, 6])]
    bootstrap_ip = str(net_addr + profile.get("bootstrap_ip_offset", 7))
    compute_ips = [str(net_addr + o) for o in profile.get("compute_ip_offsets", [])]

    logger.info(f"Network: {network} | Gateway: {gateway}")
    logger.info(f"Control Plane IPs: {cp_ips}  (api / api-int)")
    logger.info(f"Infra IPs:         {infra_ips}  (*.apps ingress)")
    logger.info(f"Bootstrap IP:      {bootstrap_ip}")
    if compute_ips:
        logger.info(f"Compute IPs:       {compute_ips}")

    return {
        "network": str(network),
        "machine_network_cidr": str(network),
        "prefix_length": network.prefixlen,
        "netmask": str(network.netmask),
        "gateway": gateway,
        "infra_ips": infra_ips,
        "control_plane_ips": cp_ips,
        "bootstrap_ip": bootstrap_ip,
        "compute_ips": compute_ips,
    }
