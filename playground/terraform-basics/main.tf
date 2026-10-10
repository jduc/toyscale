# Everything in ONE file on purpose, so you can see the whole picture.
# (Terraform would merge it the same way if it were split across several .tf files.)

# 1. Settings: which plugin (provider) we need.
#    "local" = a provider whose resources are plain files on your disk.
terraform {
  required_providers {
    local = {
      source  = "hashicorp/local"
      version = "~> 2.9"
    }
  }
}

# 2. An input.
variable "name" {
  type    = string
  default = "world"
}

# 3. A resource: "this file should exist with this content".
#    TYPE = local_file (from the "local" provider), NAME = greeting (our nickname).
resource "local_file" "hello" {
  filename = "${path.module}/output/hello.txt" # path.module = this folder
  content  = "Hello, ${var.name}!\n"
}

resource "local_file" "goodbye" {
  filename = "${path.module}/output/goodbye.txt" 
  content  = "After saying Hello in in ${local_file.hello.filename}, we say Goodbye, ${var.name}!\n"
}

# 4. An output: printed after apply, readable with `terraform output`.
output "greeting_file" {
  value = local_file.hello.filename
}

output "goodbye_file" {
  value = local_file.goodbye.filename
}
