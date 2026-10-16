resource "aws_amplify_app" "portal" {
  for_each                 = toset(["visitor", "admin"])
  name                     = "${local.name}-${each.key}"
  platform                 = "WEB"
  enable_branch_auto_build = false
}

resource "aws_amplify_branch" "portal" {
  for_each          = aws_amplify_app.portal
  app_id            = each.value.id
  branch_name       = "demo"
  enable_auto_build = false
  stage             = "DEVELOPMENT"
}
