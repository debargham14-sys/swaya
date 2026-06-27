# Four single-key tables replacing the former MongoDB collections. On-demand
# billing (PAY_PER_REQUEST) — no capacity to manage, scales to zero cost at rest.
resource "aws_dynamodb_table" "tables" {
  for_each = local.dynamo_tables

  name         = "${var.dynamo_table_prefix}_${each.key}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = each.value

  attribute {
    name = each.value
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = merge(local.tags, { Table = each.key })
}
