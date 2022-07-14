import pulumi
import pulumi_oci as oci

# config
config = pulumi.Config()
compartment_ocid = config.require_secret('compartmentOcid')

# artifacts/registry
registry = oci.artifacts.ContainerRepository(
    "container-repo",
    display_name="laura-container-repo",
    compartment_id=compartment_ocid,
    is_public=True
)

# networking
vcn = oci.core.Vcn(
    "vcn",
    cidr_blocks=['10.0.0.0/16'],
    compartment_id=compartment_ocid,
)

nat_gateway = oci.core.NatGateway(
    "nat_gateway",
    compartment_id=compartment_ocid,
    vcn_id=vcn.id
)

internet_gateway = oci.core.InternetGateway(
    "oke_internet_gateway",
    compartment_id=compartment_ocid,
    vcn_id=vcn.id
)

service_gateway = oci.core.ServiceGateway(
    "service_gateway",
    compartment_id=compartment_ocid,
    services=[oci.core.ServiceGatewayServiceArgs(
        service_id=oci.core.get_services().services[1].id,
    )],
    vcn_id=vcn.id
)

svc_lb_seclist = oci.core.SecurityList(
    "svc_lb_security_list",
    compartment_id=compartment_ocid,
    vcn_id=vcn.id
)

node_seclist = oci.core.SecurityList(
    "node_security_list",
    compartment_id=compartment_ocid,
    egress_security_rules=[
        oci.core.SecurityListEgressSecurityRuleArgs(
            description="Worker Nodes access to Internet",
            destination="0.0.0.0/0",
            destination_type="CIDR_BLOCK",
            protocol="all",
        ),
        oci.core.SecurityListEgressSecurityRuleArgs(
            description="Path discovery",
            destination="10.0.0.0/28",
            destination_type="CIDR_BLOCK",
            icmp_options=oci.core.SecurityListEgressSecurityRuleIcmpOptionsArgs(
                code=4,
                type=3,
            ),
            protocol="1",
        ),
    ],
    ingress_security_rules=[
        oci.core.SecurityListIngressSecurityRuleArgs(
            description="Path discovery",
            icmp_options=oci.core.SecurityListIngressSecurityRuleIcmpOptionsArgs(
                code=4,
                type=3,
            ),
            protocol="1",
            source="10.0.0.0/28",
            source_type="CIDR_BLOCK",
        ),
        oci.core.SecurityListIngressSecurityRuleArgs(
            description="Inbound SSH traffic to worker nodes",
            protocol="6",
            source="0.0.0.0/0",
            source_type="CIDR_BLOCK",
            tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                max=22,
                min=22,
            ),
        ),
    ],
    vcn_id=vcn.id
)

node_route_table = oci.core.RouteTable(
    "oke_node_route_table",
    compartment_id=compartment_ocid,
    route_rules=[
        oci.core.RouteTableRouteRuleArgs(
            description="traffic to OCI services",
            destination="all-phx-services-in-oracle-services-network",
            destination_type="SERVICE_CIDR_BLOCK",
            network_entity_id=service_gateway.id,
        ),
        oci.core.RouteTableRouteRuleArgs(
            description="traffic to the internet",
            destination="0.0.0.0/0",
            destination_type="CIDR_BLOCK",
            network_entity_id=nat_gateway.id,
        ),
    ],
    vcn_id=vcn.id
)

svc_lb_route_table = oci.core.RouteTable(
    "oke_svclb_route_table",
    compartment_id=compartment_ocid,
    route_rules=[oci.core.RouteTableRouteRuleArgs(
        description="traffic to/from internet",
        destination="0.0.0.0/0",
        destination_type="CIDR_BLOCK",
        network_entity_id=internet_gateway.id,
    )],
    vcn_id=vcn.id
)

node_subnet = oci.core.Subnet(
    "node_subnet",
    cidr_block="10.0.10.0/24",
    compartment_id=compartment_ocid,
    route_table_id=node_route_table.id,
    security_list_ids=[node_seclist.id],
    vcn_id=vcn.id
)

lb_subnet = oci.core.Subnet(
    "lb_subnet",
    cidr_block="10.0.20.0/24",
    compartment_id=compartment_ocid,
    route_table_id=svc_lb_route_table.id,
    security_list_ids=[svc_lb_seclist.id],
    vcn_id=vcn.id
)

get_ad_name = oci.identity.get_availability_domain(
    compartment_id=compartment_ocid,
    ad_number=1
)

node_image = oci.core.get_images(
    compartment_id=compartment_ocid,
    operating_system="Oracle Linux",
    operating_system_version="7.9",
    shape="VM.Standard.E4.Flex",
    sort_by="TIMECREATED",
    sort_order="DESC"
)

with open(config.require('path_ssh_pubkey'), "r") as f:
    ssh_pub_key = f.read()

instance_oraclelinux = oci.core.Instance(
    "instance_oraclelinux",
    agent_config=oci.core.InstanceAgentConfigArgs(
        plugins_configs=[
            oci.core.InstanceAgentConfigPluginsConfigArgs(
                desired_state="DISABLED",
                name="Vulnerability Scanning",
            ),
            oci.core.InstanceAgentConfigPluginsConfigArgs(
                desired_state="DISABLED",
                name="Oracle Java Management Service",
            ),
            oci.core.InstanceAgentConfigPluginsConfigArgs(
                desired_state="ENABLED",
                name="OS Management Service Agent",
            ),
            oci.core.InstanceAgentConfigPluginsConfigArgs(
                desired_state="DISABLED",
                name="Management Agent",
            ),
            oci.core.InstanceAgentConfigPluginsConfigArgs(
                desired_state="ENABLED",
                name="Custom Logs Monitoring",
            ),
            oci.core.InstanceAgentConfigPluginsConfigArgs(
                desired_state="ENABLED",
                name="Compute Instance Run Command",
            ),
            oci.core.InstanceAgentConfigPluginsConfigArgs(
                desired_state="ENABLED",
                name="Compute Instance Monitoring",
            ),
            oci.core.InstanceAgentConfigPluginsConfigArgs(
                desired_state="DISABLED",
                name="Block Volume Management",
            ),
            oci.core.InstanceAgentConfigPluginsConfigArgs(
                desired_state="DISABLED",
                name="Bastion",
            ),
        ],
    ),
    availability_domain=get_ad_name.__dict__['name'],
    compartment_id=compartment_ocid,
    create_vnic_details=oci.core.InstanceCreateVnicDetailsArgs(
        display_name="oci_ol_instance_pulumi",
        subnet_id=node_subnet.id,
    ),
    display_name="oci_ol_instance_pulumi",
    fault_domain="FAULT-DOMAIN-1",

    metadata={
        "ssh_authorized_keys": ssh_pub_key,
    },
    shape="VM.Standard.E4.Flex",
    shape_config=oci.core.InstanceShapeConfigArgs(
        memory_in_gbs=16,
        ocpus=1,
    ),
    source_details=oci.core.InstanceSourceDetailsArgs(
        boot_volume_size_in_gbs="50",
        source_id=node_image.images[0]['id'],
        source_type="image",
    ),
)

external_endpoint = pulumi.export("endpoint", instance_oraclelinux.public_ip)

