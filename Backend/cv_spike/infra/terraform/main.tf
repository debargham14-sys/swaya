data "aws_caller_identity" "current" {}

locals {
  tags = {
    Project   = var.project
    ManagedBy = "terraform"
  }

  # logical table name -> partition-key attribute. MUST match api/db/dynamo.py TABLES.
  dynamo_tables = {
    scans            = "scan_id"
    calibration      = "id"
    vest_scans       = "scan_id"
    vest_calibration = "id"
    users            = "uid"
    personas         = "persona_id"
    orders           = "order_id"
  }
}
