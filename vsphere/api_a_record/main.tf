resource "null_resource" "a_record" {
  for_each = toset(var.ip_addresses)
  provisioner "local-exec" {
    command = "echo -e \"update add api.${var.cluster_domain} 86400 IN A ${each.value}\nupdate add api-int.${var.cluster_domain} 86400 IN A ${each.value}\nsend\" | nsupdate -v -d"
  }
}