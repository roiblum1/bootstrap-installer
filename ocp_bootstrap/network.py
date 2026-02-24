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
        .1-.3  = infra nodes
        .4-.6  = control plane nodes
        .7     = bootstrap
        .8     = API VIP
        .9     = Ingress VIP
        .254   = gateway (configurable)
    """
    network = ipaddress.ip_network(segment, strict=False)
    net_addr = network.network_address

    gateway = str(net_addr + profile.get("gateway_offset", 254))
    infra_ips = [str(net_addr + o) for o in profile.get("infra_ip_offsets", [1, 2, 3])]
    cp_ips = [str(net_addr + o) for o in profile.get("control_plane_ip_offsets", [4, 5, 6])]
    bootstrap_ip = str(net_addr + profile.get("bootstrap_ip_offset", 7))
    api_vip = str(net_addr + profile.get("api_vip_offset", 8))
    ingress_vip = str(net_addr + profile.get("ingress_vip_offset", 9))

    logger.info(f"Network: {network} | Gateway: {gateway}")
    logger.info(f"Infra IPs:         {infra_ips}")
    logger.info(f"Control Plane IPs: {cp_ips}")
    logger.info(f"Bootstrap IP:      {bootstrap_ip}")
    logger.info(f"API VIP:           {api_vip}")
    logger.info(f"Ingress VIP:       {ingress_vip}")

    return {
        "network": str(network),
        "machine_network_cidr": str(network),
        "prefix_length": network.prefixlen,
        "netmask": str(network.netmask),
        "gateway": gateway,
        "infra_ips": infra_ips,
        "control_plane_ips": cp_ips,
        "bootstrap_ip": bootstrap_ip,
        "api_vip": api_vip,
        "ingress_vip": ingress_vip,
    }
