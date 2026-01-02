provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project = "multilingual-audio-pipeline"
      Env     = var.env
    }
  }
}
