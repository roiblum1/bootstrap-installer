resource "null_resource" "a_record" {
  for_each = var.hostnames_ip_addresses

  provisioner "local-exec" {
    command = "echo -e \"update add ${element(split(".", each.key), 0)}.${var.cluster_domain} 86400 IN A ${each.value}\nsend\" | nsupdate -v -d"
  }
}

resource "null_resource" "ptr_records" {
  for_each = var.hostnames_ip_addresses
  provisioner "local-exec" {
    command = "echo -e \"update add ${join(".", reverse(split(".", each.value)))}.in-addr.arpa. 86400 PTR ${element(split(".", each.key), 0)}.${var.cluster_domain}.\nsend\" | nsupdate -v -d"
  }
}