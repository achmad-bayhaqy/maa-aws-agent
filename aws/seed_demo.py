#!/usr/bin/env python3
"""MAA AWS Agent - Task 7: Seed demo resources (VPC + 2 EC2 t3.micro stopped)."""
import json
import sys
import time

import boto3

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from lib_common import REGION, log, load_state, save_state

st = load_state()
ec2 = boto3.client("ec2", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)


def tags(name):
    return [{"ResourceType": "vpc", "Tags": [{"Key": "Project", "Value": "maa-demo"},
                                             {"Key": "Name", "Value": name}]},
            ]


def find_demo_vpc():
    r = ec2.describe_vpcs(Filters=[{"Name": "tag:Name", "Values": ["maa-demo-vpc"]}])
    return r["Vpcs"][0]["VpcId"] if r["Vpcs"] else None


vpc_id = find_demo_vpc()
if vpc_id:
    log(f"= demo VPC exists: {vpc_id}")
else:
    vpc_id = ec2.create_vpc(CidrBlock="10.42.0.0/16",
                            TagSpecifications=[{"ResourceType": "vpc", "Tags": [
                                {"Key": "Name", "Value": "maa-demo-vpc"},
                                {"Key": "Project", "Value": "maa-demo"}]}])["Vpc"]["VpcId"]
    ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={"Value": True})
    ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={"Value": True})
    az = ec2.describe_availability_zones()["AvailabilityZones"][0]["ZoneName"]
    subnet_id = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.42.1.0/24", AvailabilityZone=az,
                                  TagSpecifications=[{"ResourceType": "subnet", "Tags": [
                                      {"Key": "Name", "Value": "maa-demo-public-a"},
                                      {"Key": "Project", "Value": "maa-demo"}]}])["Subnet"]["SubnetId"]
    igw_id = ec2.create_internet_gateway(TagSpecifications=[{"ResourceType": "internet-gateway", "Tags": [
        {"Key": "Name", "Value": "maa-demo-igw"}, {"Key": "Project", "Value": "maa-demo"}]}])[
        "InternetGateway"]["InternetGatewayId"]
    ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
    rtb_id = ec2.create_route_table(VpcId=vpc_id, TagSpecifications=[
        {"ResourceType": "route-table", "Tags": [{"Key": "Name", "Value": "maa-demo-rt"},
                                                 {"Key": "Project", "Value": "maa-demo"}]}])[
        "RouteTable"]["RouteTableId"]
    ec2.create_route(RouteTableId=rtb_id, DestinationCidrBlock="0.0.0.0/0", GatewayId=igw_id)
    ec2.associate_route_table(RouteTableId=rtb_id, SubnetId=subnet_id)
    sg_id = ec2.create_security_group(GroupName="maa-demo-sg", Description="MAA demo SG (default deny inbound)",
                                      VpcId=vpc_id, TagSpecifications=[
                                          {"ResourceType": "security-group", "Tags": [
                                              {"Key": "Name", "Value": "maa-demo-sg"},
                                              {"Key": "Project", "Value": "maa-demo"}]}])["GroupId"]
    log(f"+ VPC {vpc_id} subnet {subnet_id} igw {igw_id} sg {sg_id}")
st["demo_vpc_id"] = vpc_id
save_state(st)

# ---------------------------------------------------------------- AMI (AL2023 x86)
try:
    ami = ssm.get_parameter(Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64")[
        "Parameter"]["Value"]
    log(f"AMI via SSM: {ami}")
except Exception as e:
    r = ec2.describe_images(Owners=["amazon"], Filters=[
        {"Name": "name", "Values": ["al2023-ami-2023.*-kernel-6.1-x86_64"]},
        {"Name": "state", "Values": ["available"]}])
    ami = sorted(r["Images"], key=lambda x: x["CreationDate"])[-1]["ImageId"]
    log(f"AMI via describe: {ami}")

# ---------------------------------------------------------------- 2 instances
existing = ec2.describe_instances(Filters=[
    {"Name": "tag:Project", "Values": ["maa-demo"]},
    {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]},
])["Reservations"]
have = {t["Value"]: i["InstanceId"] for res in existing for i in res["Instances"]
        for t in i.get("Tags", []) if t["Key"] == "Name"}
ids = []
for name in ["maa-demo-app-01", "maa-demo-app-02"]:
    if name in have:
        ids.append(have[name])
        log(f"= {name} exists: {have[name]}")
        continue
    r = ec2.run_instances(
        ImageId=ami, InstanceType="t3.micro", MinCount=1, MaxCount=1,
        SubnetId=st.get("demo_subnet_id") or next(iter(
            [s["SubnetId"] for s in ec2.describe_subnets(Filters=[
                {"Name": "vpc-id", "Values": [vpc_id]}])["Subnets"]])),
        IamInstanceProfile={"Name": st.get("inst_profile", "maa-demo-instance-profile")},
        TagSpecifications=[{"ResourceType": "instance", "Tags": [
            {"Key": "Name", "Value": name}, {"Key": "Project", "Value": "maa-demo"}]},
            {"ResourceType": "volume", "Tags": [
                {"Key": "Name", "Value": name}, {"Key": "Project", "Value": "maa-demo"}]}],
    )
    ids.append(r["Instances"][0]["InstanceId"])
    log(f"+ {name}: {r['Instances'][0]['InstanceId']}")

log("waiting running...")
ec2.get_waiter("instance_running").wait(InstanceIds=ids)
log("stopping both (hemat biaya - idle Rp0)...")
ec2.stop_instances(InstanceIds=ids)
ec2.get_waiter("instance_stopped").wait(InstanceIds=ids)
st["demo_instances"] = ids
save_state(st)
log("=== SEED DEMO COMPLETE ===")
