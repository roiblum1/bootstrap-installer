import logging
import shutil
from pathlib import Path

from .utils import run_cmd


def create_manifests(install_bin: str, install_dir: Path, logger: logging.Logger) -> None:
    """Run openshift-install create manifests."""
    logger.info("=== Creating OpenShift manifests ===")
    run_cmd([install_bin, "create", "manifests", f"--dir={install_dir}"], logger=logger)
    logger.info("Manifests created successfully")


def inject_v4_internal_subnet(
    manifest_path: Path, install_dir: Path, logger: logging.Logger
) -> None:
    """Inject v4InternalSubnet manifest into the openshift manifests directory."""
    target = install_dir / "manifests" / "cluster-infrastructure-02-config.yml"
    shutil.copy2(manifest_path, target)
    logger.info(f"Injected v4InternalSubnet manifest -> {target}")


def create_ignition_configs(
    install_bin: str,
    install_dir: Path,
    ignition_dir: Path,
    logger: logging.Logger,
) -> None:
    """Run openshift-install create ignition-configs and copy outputs."""
    logger.info("=== Creating ignition configs ===")
    run_cmd(
        [install_bin, "create", "ignition-configs", f"--dir={install_dir}"],
        logger=logger,
    )

    ignition_dir.mkdir(parents=True, exist_ok=True)
    for ign_file in install_dir.glob("*.ign"):
        dest = ignition_dir / ign_file.name
        shutil.copy2(ign_file, dest)
        logger.info(f"Copied {ign_file.name} -> {dest}")

    auth_src = install_dir / "auth"
    auth_dst = ignition_dir.parent / "auth"
    if auth_src.exists():
        if auth_dst.exists():
            shutil.rmtree(auth_dst)
        shutil.copytree(auth_src, auth_dst)
        logger.info(f"Copied auth directory -> {auth_dst}")
