import base64
import json
import logging
import os
import tempfile
import time
from pathlib import Path

import yaml

from .utils import run_cmd


def register_cluster_in_argocd(
    cluster_name: str,
    kubeconfig_path: Path,
    profile: dict,
    logger: logging.Logger,
) -> None:
    """Register the spoke cluster in ArgoCD on the hub cluster.

    Creates an argocd-manager ServiceAccount on the spoke cluster with a
    non-expiring token, then applies the ArgoCD cluster Secret to the hub.
    """
    hub_api_url = profile["argocd_hub_api_url"]
    hub_token = profile.get("argocd_hub_token") or os.environ.get(
        profile.get("argocd_hub_token_env", ""), ""
    )
    if not hub_token:
        logger.error(
            "No hub token found — set argocd_hub_token (plain text) or "
            "argocd_hub_token_env (env var name) in the cluster config"
        )
        return

    argocd_namespace = profile.get("argocd_namespace", "argocd")
    insecure = profile.get("argocd_insecure_skip_tls", False)

    logger.info("=== Registering cluster in ArgoCD hub ===")
    spoke_env = {"KUBECONFIG": str(kubeconfig_path)}

    # Step 1: Create argocd-manager ServiceAccount (idempotent via apply)
    _apply_to_spoke(
        {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {"name": "argocd-manager", "namespace": "kube-system"},
        },
        spoke_env,
        logger,
    )

    # Step 2: Create static SA token Secret (non-expiring, populated by token controller)
    _apply_to_spoke(
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": "argocd-manager-token",
                "namespace": "kube-system",
                "annotations": {"kubernetes.io/service-account.name": "argocd-manager"},
            },
            "type": "kubernetes.io/service-account-token",
        },
        spoke_env,
        logger,
    )

    # Step 3: Bind argocd-manager to cluster-admin
    run_cmd(["oc", "adm", "policy", "add-cluster-role-to-user", "cluster-admin", "-z", "argocd-manager", "-n", "kube-system"], env=spoke_env, logger=logger)

    # Step 4: Wait for token controller to populate the Secret
    sa_token = _wait_for_sa_token(spoke_env, logger)

    # Step 5: Get spoke API server URL
    api_result = run_cmd(["oc", "whoami", "--show-server"], env=spoke_env, logger=logger)
    spoke_api_url = api_result.stdout.strip()

    # Step 6: Get spoke CA cert from kube-root-ca.crt ConfigMap
    ca_result = run_cmd(["oc", "get", "cm", "kube-root-ca.crt", "-n", "kube-system", "-o", r"jsonpath={.data.ca\.crt}"], env=spoke_env, logger=logger)
    ca_data_b64 = base64.b64encode(ca_result.stdout.strip().encode()).decode()

    # Step 7: Build ArgoCD cluster Secret and apply to hub
    argocd_config = {
        "bearerToken": sa_token,
        "tlsClientConfig": {
            "insecure": insecure,
            "caData": "" if insecure else ca_data_b64,
        },
    }
    cluster_secret = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": f"cluster-{cluster_name}",
            "namespace": argocd_namespace,
            "labels": {"argocd.argoproj.io/secret-type": "cluster"},
        },
        "type": "Opaque",
        "stringData": {
            "name": cluster_name,
            "server": spoke_api_url,
            "config": json.dumps(argocd_config),
        },
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(cluster_secret, f)
        tmp_path = f.name

    try:
        hub_cmd = ["oc", f"--server={hub_api_url}", f"--token={hub_token}"]
        if insecure:
            hub_cmd.append("--insecure-skip-tls-verify")
        hub_cmd += ["apply", "-f", tmp_path]
        run_cmd(hub_cmd, logger=logger)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    logger.info(f"Cluster '{cluster_name}' registered in ArgoCD (namespace: {argocd_namespace}, hub: {hub_api_url})")


def _apply_to_spoke(manifest: dict, env: dict, logger: logging.Logger) -> None:
    """Write a manifest to a tempfile and apply it to the spoke cluster."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(manifest, f)
        tmp_path = f.name
    try:
        run_cmd(["oc", "apply", "-f", tmp_path], env=env, logger=logger)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _wait_for_sa_token(env: dict, logger: logging.Logger, retries: int = 10, delay: float = 3.0) -> str:
    """Poll the argocd-manager-token Secret until the token controller populates it."""
    for attempt in range(retries):
        result = run_cmd(["oc", "get", "secret", "argocd-manager-token", "-n", "kube-system", "-o", "jsonpath={.data.token}"], env=env, logger=logger)
        token_b64 = result.stdout.strip()
        if token_b64:
            return base64.b64decode(token_b64).decode()
        logger.info(f"Waiting for SA token to be populated (attempt {attempt + 1}/{retries})...")
        time.sleep(delay)
    raise RuntimeError("Timed out waiting for argocd-manager-token to be populated by the token controller")
