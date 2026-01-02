variable "env" {
  description = "Deployment environment name (beta or prod)."
  type        = string
  validation {
    condition     = contains(["beta", "prod"], var.env)
    error_message = "env must be either beta or prod."
  }
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "s3_bucket_name" {
  description = "S3 bucket used for inputs and outputs."
  type        = string
}

variable "target_langs" {
  description = "Languages to translate into (e.g., [\"es\",\"fr\"])."
  type        = list(string)
  default     = ["es", "fr"]
}

variable "polly_voice_map" {
  description = "Map of language code to Polly voice id."
  type        = map(string)
  default = {
    es = "Lupe"
    fr = "Lea"
  }
}

variable "enable_retention" {
  description = "If true, apply S3 lifecycle expiration rules."
  type        = bool
  default     = true
}

variable "retention_days" {
  description = "Days before expiring objects under beta/ and prod/ prefixes."
  type        = number
  default     = 30
}
