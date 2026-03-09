# Create Object Lifecycle Policy
resource "oci_objectstorage_object_lifecycle_policy" "db_backup_lifecycle_policy" {
  count      = var.create_object_lifecycle_policy ? 1 : 0
  depends_on = [oci_objectstorage_bucket.test_bucket]

  bucket    = var.bucket_name
  namespace = var.bucket_namespace

  dynamic "rules" {
    for_each = var.object_lifecycle_rules
    content {
      action     = rules.value.action
      is_enabled = lookup(rules.value, "is_enabled", true)
      name       = rules.value.name
      time_amount = rules.value.time_amount
      time_unit   = rules.value.time_unit
    }
  }
}

# variables.tf

variable "create_object_lifecycle_policy" {
  type        = bool
  description = "Determines whether object lifecycle policy should be created"
  default     = false
}

variable "object_lifecycle_rules" {
  description = "List of object lifecycle rules"
  type = list(object({
    name        = string
    action      = string
    is_enabled  = optional(bool, true)
    time_amount = number
    time_unit   = string
  }))
  default = []
}

terraform {
  source = "../modules/oci-bucket"
}

# terragrunt.hcl

inputs = {
  create_object_lifecycle_policy = true

  bucket_name      = "your-bucket-name"
  bucket_namespace = "your-namespace"

  object_lifecycle_rules = [
    {
      name        = "archive_after_15_days"
      action      = "ARCHIVE"
      is_enabled  = true
      time_amount = 15
      time_unit   = "DAYS"
    },
    {
      name        = "delete_after_22_days"
      action      = "DELETE"
      is_enabled  = true
      time_amount = 22
      time_unit   = "DAYS"
    }
  ]
}
