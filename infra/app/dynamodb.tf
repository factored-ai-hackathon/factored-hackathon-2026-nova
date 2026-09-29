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

# Chat sessions and their conversation history (decision 21), so any Lambda instance can continue
# any conversation. Short TTL: raw conversation text is only kept while the chat is active.
resource "aws_dynamodb_table" "sessions" {
  name         = "${var.prefix}-chat-sessions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "session_id"

  attribute {
    name = "session_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

# Demo customers loaded from the dataset by data/scripts/load_demo_data.py (decision 24). One
# partition per customer: PROFILE (identity for verification), PRODUCT#, TXN#, COMPLAINT# items.
# The document index only holds PROFILE items (sparse), so the agent can look customers up by
# document without scanning. The dataset is fully synthetic. No TTL: reloaded on demand.
resource "aws_dynamodb_table" "demo_customers" {
  name         = "${var.prefix}-demo-customers"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "customer_id"
  range_key    = "sk"

  attribute {
    name = "customer_id"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  attribute {
    name = "document_number"
    type = "S"
  }

  global_secondary_index {
    name            = "by-document"
    hash_key        = "document_number"
    projection_type = "ALL"
  }
}
