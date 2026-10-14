variable "azs" {
  type = list(string)
  validation {
    condition     = length(distinct(var.azs)) == 2
    error_message = "Supply exactly two distinct AZs in your region."
  }
}

variable "operator_cidr" {
  type = string
  validation {
    condition     = can(cidrnetmask(var.operator_cidr)) && endswith(var.operator_cidr, "/32")
    error_message = "Use the operator public IPv4 /32; world and broad network access are refused."
  }
}

variable "operator_role_arn" {
  type = string
  validation {
    condition     = startswith(var.operator_role_arn, "arn:aws:iam::${var.account_id}:role/")
    error_message = "Operator role must belong to the configured account."
  }
}

variable "eks_version" {
  type = string
}

variable "rds_engine_version" {
  type = string
  validation {
    condition     = can(regex("^17\\.[0-9]+$", var.rds_engine_version))
    error_message = "Choose an available PostgreSQL 17 patch."
  }
}

variable "node_instance_type" {
  type    = string
  default = "m7g.large"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.small"
}

variable "frontend_origin" {
  type = string
}

variable "alarm_email" {
  type = string
}

variable "allow_database_destroy" {
  type    = bool
  default = false
}
variable "retain_final_snapshot" {
  type    = bool
  default = true
}
variable "final_snapshot_suffix" {
  type    = string
  default = "reviewed-backup"
}
