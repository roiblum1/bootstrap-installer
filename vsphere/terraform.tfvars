// ID identifying the cluster to create. Use your username so that resources created can be tracked back to you. For example "ocpd-test"
cluster_id = "ocp-mce-five-prep"

// Base domain from which the cluster domain is a subdomain.
base_domain = 

// Domain of the cluster. This should be "${cluster_id}.${base_domain}".
cluster_domain = 

// Name of the vSphere server. The dev cluster is on "vcsa.vmware.devcluster.openshift.com".
vsphere_server = 

// User on the vSphere server.
vsphere_user = 

// Password of the user on the vSphere server.
vsphere_password = 

// Name of the vSphere cluster. The dev cluster is "devel".
vsphere_cluster = 

// Name of the vSphere data center. The dev cluster is "dc1".
vsphere_datacenter = 

// Name of the vSphere datastore cluster to use for the VMs. The dev cluster uses "nvme-ds1".
vsphere_datastore_cluster = 

// Name of the VM template to clone to create VMs for the cluster. The dev cluster has a template named "rhcos-latest".
vm_template = 

// The machine_cidr where IP addresses will be assigned for cluster nodes.
machine_cidr = 

// Name of network in VC.
vm_network = 

// The IP Address of the gateway in this VLAN.
gateway_ip = 

// This is the name of the distributed virtual switch of the relevant networks.
// This is necessary only if you have multiple networks with the same name in your VC.
// If you need it, you MUST uncomment the relevant block in main.tf file in your VC.
vsphere_dvs_name = 

// The IP Addresses of the DNS servers
// Order matters! Use the relevant IP for the site.
vm_dns_addresses = 

// The number of control plane VMs to create. Default is 3.
control_plane_count = 3

// The number of compute VMs to create. Default is 3.
compute_count = 0

// The number of infra VMs to create. Default is 3.
infra_count = 3

// The number of infra VMs to create. Default is 0.
//infra_count = 0

// VM resources - These are the defaults
bootstrap_disk_size = 120

control_plane_num_cpus = 4
control_plane_memory = 16384
control_plane_disk_size = 120

compute_num_cpus = 4
compute_memory = 8192
compute_disk_size = 120

infra_num_cpus = 2
infra_memory = 8192
infra_disk_size = 120

// Ignition Files:
// Ignition config path for the bootstrap machine
bootstrap_ignition_path = "/mnt/roi/ocp4-prep-mce-five/ignition/ocp4-mce-five-prep/bootstrap.ign"

// Ignition config path for the control plane machines
control_plane_ignition_path = "/mnt/roi/ocp4-prep-mce-five/ignition/ocp4-mce-five-prep/master.ign"

// Ignition config path for the compute machines
compute_ignition_path = "/mnt/roi/ocp4-prep-mce-five/ignition/ocp4-mce-five-prep/worker.ign"

// Ignition config path for the infra machines
infra_ignition_path = "/mnt/roi/ocp4-prep-mce-five/ignition/ocp4-mce-five-prep/worker.ign"

// Path for the ssh public key file
ssh_public_key_path = "/root/openshift4-installation/authentication/id_rsa"

// The IP address to assign to the bootstrap VM.
bootstrap_ip = 

// The IP addresses to assign to the control plane VMs. The length of this list
// must match the value of control_plane_count.
control_plane_ips = 

// The IP addresses to assign to the compute VMs. The length of this list
// must match the value of compute_count.
compute_ips = 

// The IP addresses to assign to the infra VMs. The length of this list
// must match the value of infra_count.
infra_ips = 