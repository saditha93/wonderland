"""Run bounded SSM operations and save diagnostics privately."""

import time
from botocore.exceptions import ClientError
from scripts.aws.credentials import GuardError
from scripts.aws.cli import (
    PRIVATE,
    write_private_json,
)


def run_on_server(aws, deployment_details, commands, timeout=1800, echo=True):
    ssm = aws.client("ssm")
    ready = False
    for _ in range(120):
        nodes = ssm.describe_instance_information(
            Filters=[
                {"Key": "InstanceIds", "Values": [deployment_details["instance_id"]]}
            ]
        )["InstanceInformationList"]
        if nodes and nodes[0]["PingStatus"] == "Online":
            ready = True
            break
        time.sleep(5)
    if not ready:
        raise GuardError("SSM agent is not online; inspect EC2 boot status")
    sent = ssm.send_command(
        InstanceIds=[deployment_details["instance_id"]],
        DocumentName="AWS-RunShellScript",
        Parameters={"commands": commands, "executionTimeout": [str(timeout)]},
        TimeoutSeconds=timeout,
    )
    cid = sent["Command"]["CommandId"]
    print("SSM operation started:", cid, flush=True)
    for n in range(timeout // 5 + 1):
        try:
            result = ssm.get_command_invocation(
                CommandId=cid, InstanceId=deployment_details["instance_id"]
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "InvocationDoesNotExist":
                time.sleep(5)
                continue
            raise
        if result["Status"] in {"Success", "Failed", "TimedOut", "Cancelled"}:
            write_private_json(PRIVATE / ("ssm-" + cid + ".json"), result)
            if result["Status"] != "Success":
                raise GuardError(
                    "SSM operation "
                    + result["Status"]
                    + "; private diagnostic file saved under secrets/simple-cloud"
                )
            if echo:
                print(result.get("StandardOutputContent", ""))
            return result
        if n and n % 12 == 0:
            print("Waiting for server operation...", flush=True)
        time.sleep(5)
    raise GuardError("SSM operation did not complete within the bounded wait")
