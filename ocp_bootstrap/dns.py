import logging

import requests


def create_wildcard_dns_via_api(
    cluster_name: str,
    wildcard_dns_url: str,
    logger: logging.Logger,
) -> None:
    """
    Create the *.apps wildcard DNS record by POSTing to an HTTP API.

    The api and api-int records are created by Terraform (exec provisioner).
    This function handles only the wildcard.

    Request:  POST <wildcard_dns_url>
              Content-Type: application/json
              Body: {"cluster_name": "<cluster_name>"}
    """
    logger.info("=== Creating *.apps wildcard DNS record via API ===")
    logger.info(f"POST {wildcard_dns_url} | cluster_name={cluster_name}")

    try:
        response = requests.post(
            wildcard_dns_url,
            json={"cluster_name": cluster_name},
            timeout=15,
        )
        response.raise_for_status()
        logger.info(f"Wildcard DNS record created (HTTP {response.status_code})")
        try:
            logger.debug(f"Response body: {response.json()}")
        except Exception:
            pass
    except requests.exceptions.RequestException as e:
        logger.error(f"Wildcard DNS API error: {e}")
        raise RuntimeError(f"Failed to create wildcard DNS record: {e}")
