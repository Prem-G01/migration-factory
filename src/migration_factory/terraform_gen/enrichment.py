"""Optional live-AWS enrichment for Terraform generation accuracy.

Fills in details the source CMDB/tfstate export doesn't carry (AMI platform,
security group rules, IAM policy attachments, EBS volume size, RDS endpoint)
by shelling out to the AWS CLI. Off by default -- see the module docstring
note on TerraformGenerator.enable_aws_enrichment for why.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from migration_factory.core.logging import get_logger

logger = get_logger(__name__)


class AWSEnrichmentEngine:
    """Fetches additional data from AWS CLI to improve Terraform accuracy."""

    def __init__(self, region: str = "ap-south-1") -> None:
        self.region = region
        self._available = self._check_aws_cli()

    def _check_aws_cli(self) -> bool:
        try:
            r = subprocess.run(
                ["aws", "sts", "get-caller-identity"], capture_output=True, text=True, timeout=10
            )
            return r.returncode == 0
        except Exception:
            return False

    def _aws(self, *args: str) -> dict[str, Any] | None:
        if not self._available:
            return None
        try:
            r = subprocess.run(
                ["aws", "--region", self.region, "--output", "json", *args],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if r.returncode == 0:
                parsed: dict[str, Any] = json.loads(r.stdout)
                return parsed
            return None
        except Exception:
            return None

    def get_ami_platform(self, ami_id: str) -> str:
        """Returns 'windows' or 'linux' for a given AMI."""
        if not ami_id or not ami_id.startswith("ami-"):
            return "linux"
        data = self._aws("ec2", "describe-images", "--image-ids", ami_id)
        if not data or not data.get("Images"):
            return "linux"
        img = data["Images"][0]
        platform = str(img.get("Platform", "")).lower()
        name = str(img.get("Name", "")).lower()
        if "windows" in platform or "windows" in name or "win" in name:
            return "windows"
        return "linux"

    def get_sg_rules(self, sg_id: str) -> dict[str, Any]:
        """Returns security group ingress/egress rules."""
        data = self._aws("ec2", "describe-security-groups", "--group-ids", sg_id)
        if not data or not data.get("SecurityGroups"):
            return {}
        result: dict[str, Any] = data["SecurityGroups"][0]
        return result

    def get_iam_role_policies(self, role_name: str) -> list[str]:
        """Returns list of managed policy ARNs attached to a role."""
        data = self._aws("iam", "list-attached-role-policies", "--role-name", role_name)
        if not data:
            return []
        return [p["PolicyArn"] for p in data.get("AttachedPolicies", [])]

    def get_ebs_volume_size(self, volume_id: str) -> int:
        """Returns EBS volume size in GB."""
        if not volume_id:
            return 20
        data = self._aws("ec2", "describe-volumes", "--volume-ids", volume_id)
        if not data or not data.get("Volumes"):
            return 20
        return int(data["Volumes"][0].get("Size", 20))

    def get_rds_endpoint(self, db_id: str) -> str:
        """Returns RDS endpoint address."""
        data = self._aws("rds", "describe-db-instances", "--db-instance-identifier", db_id)
        if not data or not data.get("DBInstances"):
            return ""
        address: str = data["DBInstances"][0].get("Endpoint", {}).get("Address", "")
        return address

    def is_available(self) -> bool:
        return self._available
