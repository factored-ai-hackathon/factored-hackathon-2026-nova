# Chat turns and their feedback (decision 18). On-demand: cents at demo volume.
resource "aws_dynamodb_table" "interactions" {
  name         = "${var.prefix}-chat-interactions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "session_id"
  range_key    = "message_id"

  attribute {
    name = "session_id"
    type = "S"
  }

  attribute {
    name = "message_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}
