import json
import logging
import time
from pathlib import Path

from .utils import run_cmd


def approve_csrs(
    kubeconfig: Path,
    logger: logging.Logger,
    timeout_minutes: int = 45,
) -> None:
    """Poll and approve pending CSRs until the cluster is Available."""
    logger.info("=== Waiting for CSR approvals ===")

    env = {"KUBECONFIG": str(kubeconfig)}
    start = time.time()
    deadline = start + (timeout_minutes * 60)

    while time.time() < deadline:
        try:
            result = run_cmd(["oc", "get", "csr", "-o", "json"], logger=None, env=env)
            csrs = json.loads(result.stdout)

            pending = [
                csr["metadata"]["name"]
                for csr in csrs.get("items", [])
                if not csr.get("status", {}).get("conditions")
            ]

            if pending:
                logger.info(f"Approving {len(pending)} pending CSR(s): {pending}")
                for csr_name in pending:
                    try:
                        run_cmd(
                            ["oc", "adm", "certificate", "approve", csr_name],
                            logger=logger,
                            env=env,
                        )
                    except RuntimeError:
                        logger.warning(f"Failed to approve CSR {csr_name}, will retry")

            try:
                result = run_cmd(
                    [
                        "oc", "get", "clusterversion", "version",
                        "-o", 'jsonpath={.status.conditions[?(@.type=="Available")].status}',
                    ],
                    logger=None,
                    env=env,
                )
                if result.stdout.strip() == "True":
                    elapsed = int(time.time() - start)
                    logger.info(f"Cluster is Available! (took {elapsed}s)")
                    return
            except RuntimeError:
                pass

        except (RuntimeError, json.JSONDecodeError) as e:
            logger.debug(f"CSR poll error (expected during bootstrap): {e}")

        logger.info("Cluster not yet available, sleeping 30s...")
        time.sleep(30)

    logger.error(f"Timeout: cluster not available after {timeout_minutes} minutes")
    logger.error("CSRs may still need manual approval. Check with: oc get csr")
