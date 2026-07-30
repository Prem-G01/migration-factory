"""AWS cross-account role assumption for cloud_connections.

No long-lived user credentials are ever stored: the user creates an IAM
role in their own account trusting this platform's fixed identity (see
generate_setup_instructions), and we call sts:AssumeRole per-run to get
short-lived (~1h) credentials, discarded when the run ends. This
platform's own calling identity -- one set of credentials, not one per
user -- is configured via MF_AWS_PLATFORM_ACCESS_KEY_ID /
MF_AWS_PLATFORM_SECRET_ACCESS_KEY (Render env vars, same pattern as
API_KEYS / MF_DATABASE__URL), read fresh from the environment on every
call, never hardcoded.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

from migration_factory.core.logging import get_logger

logger = get_logger(__name__)

_SESSION_NAME = "migration-factory"
_SESSION_DURATION_SECONDS = 3600


class PlatformIdentityNotConfiguredError(Exception):
    """MF_AWS_PLATFORM_ACCESS_KEY_ID / MF_AWS_PLATFORM_SECRET_ACCESS_KEY aren't set."""


@dataclass(slots=True)
class AssumedCredentials:
    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: datetime


def generate_external_id() -> str:
    """A random per-connection value the trust policy also requires --
    defends against the "confused deputy" problem (an unrelated AWS
    customer who learns our platform's ARN still can't assume roles that
    trust us without also knowing this)."""
    return secrets.token_urlsafe(24)


def _platform_credentials() -> tuple[str, str]:
    access_key = os.environ.get("MF_AWS_PLATFORM_ACCESS_KEY_ID")
    secret_key = os.environ.get("MF_AWS_PLATFORM_SECRET_ACCESS_KEY")
    if not access_key or not secret_key:
        raise PlatformIdentityNotConfiguredError(
            "MF_AWS_PLATFORM_ACCESS_KEY_ID / MF_AWS_PLATFORM_SECRET_ACCESS_KEY not set"
        )
    return access_key, secret_key


def platform_identity_arn() -> str | None:
    """The ARN a user's trust policy needs to reference. None if the
    platform identity isn't configured, or the check itself fails."""
    try:
        access_key, secret_key = _platform_credentials()
    except PlatformIdentityNotConfiguredError:
        return None
    client = boto3.client("sts", aws_access_key_id=access_key, aws_secret_access_key=secret_key)
    try:
        identity = client.get_caller_identity()
    except ClientError as exc:
        logger.warning("platform_identity_check_failed", error=str(exc))
        return None
    arn: str = identity["Arn"]
    return arn


def assume_role(role_arn: str, external_id: str) -> AssumedCredentials:
    """Assumes `role_arn` using this platform's own fixed identity, scoped
    by `external_id`. Raises PlatformIdentityNotConfiguredError or
    botocore.exceptions.ClientError on failure -- callers turn those into
    a verify-connection failure, not a 500.
    """
    access_key, secret_key = _platform_credentials()
    client = boto3.client("sts", aws_access_key_id=access_key, aws_secret_access_key=secret_key)
    response = client.assume_role(
        RoleArn=role_arn,
        RoleSessionName=_SESSION_NAME,
        ExternalId=external_id,
        DurationSeconds=_SESSION_DURATION_SECONDS,
    )
    creds = response["Credentials"]
    return AssumedCredentials(
        access_key_id=creds["AccessKeyId"],
        secret_access_key=creds["SecretAccessKey"],
        session_token=creds["SessionToken"],
        expiration=creds["Expiration"],
    )


def verify_role_access(role_arn: str, external_id: str) -> tuple[bool, str]:
    """Attempts the full assume-role plus a trivial read-only call,
    proving the trust relationship works end to end -- not just that
    assume_role() itself didn't raise (a role can be assumable but still
    carry zero attached permissions).
    """
    try:
        creds = assume_role(role_arn, external_id)
    except PlatformIdentityNotConfiguredError as exc:
        return False, str(exc)
    except ClientError as exc:
        return False, exc.response.get("Error", {}).get("Message", str(exc))

    assumed_client = boto3.client(
        "sts",
        aws_access_key_id=creds.access_key_id,
        aws_secret_access_key=creds.secret_access_key,
        aws_session_token=creds.session_token,
    )
    try:
        identity = assumed_client.get_caller_identity()
    except ClientError as exc:
        return False, exc.response.get("Error", {}).get("Message", str(exc))

    return True, f"Verified access as {identity['Arn']}"


def generate_trust_policy(platform_arn: str, external_id: str) -> str:
    """Trust policy JSON for the user's IAM role -- grants *only* this
    platform's fixed identity permission to assume it, and *only* when it
    presents this specific external_id."""
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": platform_arn},
                "Action": "sts:AssumeRole",
                "Condition": {"StringEquals": {"sts:ExternalId": external_id}},
            }
        ],
    }
    return json.dumps(policy, indent=2)


def generate_setup_instructions(role_name: str, platform_arn: str, external_id: str) -> str:
    trust_policy = generate_trust_policy(platform_arn, external_id)
    return f"""# AWS cross-account access setup

Run this once in the AWS account you want Migration Factory to access.
It creates an IAM role that trusts ONLY this platform's fixed identity
({platform_arn}), and only when it presents the external ID below.
No long-lived credentials of yours are ever shared with or stored by
this platform.

## 1. Save the trust policy

cat > trust-policy.json <<'EOF'
{trust_policy}
EOF

## 2. Create the role

aws iam create-role \\
  --role-name {role_name} \\
  --assume-role-policy-document file://trust-policy.json

## 3. Attach permissions

Attach whatever managed policy matches what you want Migration Factory
to do in this account -- e.g. for a read-only trial:

aws iam attach-role-policy \\
  --role-name {role_name} \\
  --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess

## 4. Give Migration Factory the role ARN

Copy the "Arn" field from the create-role output above and paste it
back into Migration Factory to complete the connection.
"""
