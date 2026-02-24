import logging
import shutil
import subprocess
import sys
from pathlib import Path

from .utils import run_cmd


def run_terraform(
    terraform_bin: str,
    terraform_dir: str,
    tfvars_path: Path,
    logger: logging.Logger,
) -> None:
    """Run terraform init, plan (with live output), prompt for approval, then apply."""
    logger.info("=== Running Terraform ===")

    tf_dir = Path(terraform_dir)
    if not tf_dir.exists():
        logger.error(f"Terraform directory not found: {tf_dir}")
        sys.exit(1)

    dest_tfvars = tf_dir / "terraform.tfvars"
    shutil.copy2(tfvars_path, dest_tfvars)
    logger.info(f"Copied terraform.tfvars -> {dest_tfvars}")

    run_cmd([terraform_bin, "init"], cwd=tf_dir, logger=logger)

    # Run plan with output streamed directly to the terminal so the user can review it
    logger.info("Running terraform plan...")
    plan_result = subprocess.run(
        [terraform_bin, "plan", "-out=tfplan"],
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
    run_cmd([terraform_bin, "apply", "-auto-approve", "tfplan"], cwd=tf_dir, logger=logger)

    logger.info("Terraform apply completed")
