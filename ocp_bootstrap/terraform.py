import logging
import shutil
import subprocess
import sys
from pathlib import Path

from .utils import run_cmd


def _resolve_plugin_dir(plugin_dir: str | None, terraform_dir: Path) -> str | None:
    """Resolve plugin_dir to an absolute path; relative paths are anchored to terraform_dir."""
    if not plugin_dir:
        return None
    p = Path(plugin_dir)
    if not p.is_absolute():
        p = terraform_dir / p
    return str(p.resolve())


def _write_providers_tfrc(providers_dir: str, terraform_dir: Path) -> Path:
    """Write a Terraform CLI config that uses a local filesystem mirror.

    The generated file tells terraform init to use the packed provider zips in
    providers_dir (created by 'terraform providers mirror') and never hit the
    public registry.  The file is written next to the Terraform code so the
    absolute path is stable for the lifetime of the init call.
    """
    tfrc_path = terraform_dir / ".providers.tfrc"
    tfrc_path.write_text(
        "provider_installation {\n"
        "  filesystem_mirror {\n"
        f'    path    = "{providers_dir}"\n'
        '    include = ["*/*"]\n'
        "  }\n"
        "  direct {\n"
        '    exclude = ["*/*"]\n'
        "  }\n"
        "}\n"
    )
    return tfrc_path


def _build_init_cmd(terraform_bin: str) -> list:
    return [terraform_bin, "init", "-input=false"]


def run_terraform(
    terraform_bin: str,
    terraform_dir: str,
    tfvars_path: Path,
    tfstate_path: Path,
    logger: logging.Logger,
    plugin_dir: str | None = None,
) -> None:
    """Run terraform init, plan (with live output), prompt for approval, then apply.

    Each cluster keeps its own state file at tfstate_path so multiple clusters
    can share the same terraform code directory without overwriting each other's state.

    plugin_dir: path to local provider binaries directory (disconnected environments).
                When set, terraform init uses -plugin-dir=<path> instead of the registry.
    """
    logger.info("=== Running Terraform ===")

    tf_dir = Path(terraform_dir)
    if not tf_dir.exists():
        logger.error(f"Terraform directory not found: {tf_dir}")
        sys.exit(1)

    dest_tfvars = tf_dir / "terraform.tfvars"
    shutil.copy2(tfvars_path, dest_tfvars)
    logger.info(f"Copied terraform.tfvars -> {dest_tfvars}")
    logger.info(f"Using state file: {tfstate_path}")

    plugin_dir = _resolve_plugin_dir(plugin_dir, tf_dir)
    init_env: dict = {}
    if plugin_dir:
        tfrc_path = _write_providers_tfrc(plugin_dir, tf_dir)
        init_env["TF_CLI_CONFIG_FILE"] = str(tfrc_path)
        logger.info(f"Using local provider mirror: {plugin_dir}")
    run_cmd(_build_init_cmd(terraform_bin), cwd=tf_dir, logger=logger, env=init_env or None)

    # Stream plan to terminal so the user can review it; per-cluster state via -state
    logger.info("Running terraform plan...")
    plan_result = subprocess.run(
        [terraform_bin, "plan", f"-state={tfstate_path}", "-out=tfplan"],
        cwd=tf_dir,
    )
    if plan_result.returncode != 0:
        logger.error("Terraform plan failed")
        sys.exit(1)

    # Prompt for approval before applying
    print("\nDo you want to apply this plan? Type 'yes' to proceed, anything else to abort: ",
          end="", flush=True)
    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        logger.info("Terraform apply aborted")
        sys.exit(0)

    if answer != "yes":
        logger.info("Terraform apply aborted by user")
        sys.exit(0)

    logger.info("Running terraform apply...")
    run_cmd(
        [terraform_bin, "apply", f"-state={tfstate_path}", "-auto-approve", "tfplan"],
        cwd=tf_dir,
        logger=logger,
    )

    logger.info("Terraform apply completed")


def run_terraform_destroy(
    terraform_bin: str,
    terraform_dir: str,
    tfvars_path: Path,
    tfstate_path: Path,
    logger: logging.Logger,
    plugin_dir: str | None = None,
) -> None:
    """Copy tfvars and run terraform destroy against the cluster's own state file."""
    logger.info("=== Running Terraform Destroy ===")

    tf_dir = Path(terraform_dir)
    if not tf_dir.exists():
        logger.error(f"Terraform directory not found: {tf_dir}")
        sys.exit(1)

    if not tfstate_path.exists():
        logger.error(f"State file not found: {tfstate_path}. Was this cluster ever applied?")
        sys.exit(1)

    dest_tfvars = tf_dir / "terraform.tfvars"
    shutil.copy2(tfvars_path, dest_tfvars)
    logger.info(f"Copied terraform.tfvars -> {dest_tfvars}")
    logger.info(f"Using state file: {tfstate_path}")

    plugin_dir = _resolve_plugin_dir(plugin_dir, tf_dir)
    init_env: dict = {}
    if plugin_dir:
        tfrc_path = _write_providers_tfrc(plugin_dir, tf_dir)
        init_env["TF_CLI_CONFIG_FILE"] = str(tfrc_path)
        logger.info(f"Using local provider mirror: {plugin_dir}")
    run_cmd(_build_init_cmd(terraform_bin), cwd=tf_dir, logger=logger, env=init_env or None)

    # terraform destroy streams to terminal and prompts for confirmation itself
    result = subprocess.run(
        [terraform_bin, "destroy", f"-state={tfstate_path}"],
        cwd=tf_dir,
    )
    if result.returncode != 0:
        logger.error("Terraform destroy failed or was aborted")
        sys.exit(1)

    logger.info("Terraform destroy completed")
