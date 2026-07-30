# Neo4j connection details, injected into the task as individual env vars.
resource "aws_secretsmanager_secret" "neo4j" {
  name        = "${local.name}/neo4j"
  description = "Neo4j connection details for ${local.name}."
}

resource "aws_secretsmanager_secret_version" "neo4j" {
  secret_id = aws_secretsmanager_secret.neo4j.id
  secret_string = jsonencode({
    uri      = var.neo4j_uri
    username = var.neo4j_username
    password = var.neo4j_password
  })
}
