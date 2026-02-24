#!/bin/bash
# Auto-generated DNS records for cluster: ocp4-roi
# Site: site-a | Segment: 192.168.1.0/24

DNS_SERVER="10.100.0.10"
KEY_NAME="ocp-update-key"
KEY_SECRET=""
ZONE="ocp4-roi.ocp.example.local"
TTL=86400

create_record() {
    local fqdn=$1
    local ip=$2
    echo "Creating A record: ${fqdn} -> ${ip}"
    nsupdate -v <<EOF
server ${DNS_SERVER}
key ${KEY_NAME} ${KEY_SECRET}
zone ocp.example.local
update delete ${fqdn} A
update add ${fqdn} ${TTL} A ${ip}
send
EOF
}

create_wildcard() {
    local fqdn=$1
    local ip=$2
    echo "Creating wildcard A record: ${fqdn} -> ${ip}"
    nsupdate -v <<EOF
server ${DNS_SERVER}
key ${KEY_NAME} ${KEY_SECRET}
zone ocp.example.local
update delete ${fqdn} A
update add ${fqdn} ${TTL} A ${ip}
send
EOF
}

echo "=== Creating DNS records for ocp4-roi.ocp.example.local ==="

# API records - point to all control plane nodes (or LB)

create_record "api.${ZONE}" "192.168.1.4"
create_record "api-int.${ZONE}" "192.168.1.4"

create_record "api.${ZONE}" "192.168.1.5"
create_record "api-int.${ZONE}" "192.168.1.5"

create_record "api.${ZONE}" "192.168.1.6"
create_record "api-int.${ZONE}" "192.168.1.6"


# Apps wildcard - point to all infra nodes

create_wildcard "*.apps.${ZONE}" "192.168.1.1"

create_wildcard "*.apps.${ZONE}" "192.168.1.2"

create_wildcard "*.apps.${ZONE}" "192.168.1.3"


# ETCD records

create_record "etcd-0.${ZONE}" "192.168.1.4"

create_record "etcd-1.${ZONE}" "192.168.1.5"

create_record "etcd-2.${ZONE}" "192.168.1.6"


# Node A records

create_record "ocp4-roi-master-0.${ZONE}" "192.168.1.4"

create_record "ocp4-roi-master-1.${ZONE}" "192.168.1.5"

create_record "ocp4-roi-master-2.${ZONE}" "192.168.1.6"


create_record "ocp4-roi-infra-0.${ZONE}" "192.168.1.1"

create_record "ocp4-roi-infra-1.${ZONE}" "192.168.1.2"

create_record "ocp4-roi-infra-2.${ZONE}" "192.168.1.3"

create_record "ocp4-roi-bootstrap.${ZONE}" "192.168.1.7"

# SRV records for etcd
echo "Creating SRV records for etcd..."
nsupdate -v <<EOF
server ${DNS_SERVER}
key ${KEY_NAME} ${KEY_SECRET}
zone ocp.example.local
update delete _etcd-server-ssl._tcp.${ZONE} SRV

update add _etcd-server-ssl._tcp.${ZONE} ${TTL} SRV 0 10 2380 etcd-0.${ZONE}.

update add _etcd-server-ssl._tcp.${ZONE} ${TTL} SRV 0 10 2380 etcd-1.${ZONE}.

update add _etcd-server-ssl._tcp.${ZONE} ${TTL} SRV 0 10 2380 etcd-2.${ZONE}.

send
EOF

echo "=== DNS records created ==="
