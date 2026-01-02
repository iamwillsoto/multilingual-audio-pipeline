locals {
  processor_name = "multilingual-audio-processor-${var.env}"
  bucket_name    = var.s3_bucket_name

  target_langs_csv = join(",", var.target_langs)
  voice_map_json   = jsonencode(var.polly_voice_map)
}

resource "aws_s3_bucket" "pipeline" {
  bucket = local.bucket_name

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "pipeline" {
  bucket                  = aws_s3_bucket.pipeline.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "pipeline" {
  bucket = aws_s3_bucket.pipeline.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "pipeline" {
  bucket = aws_s3_bucket.pipeline.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "pipeline" {
  count  = var.enable_retention ? 1 : 0
  bucket = aws_s3_bucket.pipeline.id

  rule {
    id     = "expire-beta"
    status = "Enabled"

    filter {
      prefix = "beta/"
    }

    expiration {
      days = var.retention_days
    }
  }

  rule {
    id     = "expire-prod"
    status = "Enabled"

    filter {
      prefix = "prod/"
    }

    expiration {
      days = var.retention_days
    }
  }
}

data "aws_iam_policy_document" "processor_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "processor_role" {
  name               = "lambda-audio-processor-${var.env}"
  assume_role_policy = data.aws_iam_policy_document.processor_assume_role.json
}

data "aws_iam_policy_document" "processor_policy" {
  statement {
    sid     = "S3ReadInputs"
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.pipeline.arn}/audio_inputs/*"
    ]
  }

  statement {
    sid     = "S3WriteOutputs"
    effect  = "Allow"
    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.pipeline.arn}/beta/*",
      "${aws_s3_bucket.pipeline.arn}/prod/*"
    ]
  }

  statement {
    sid     = "Transcribe"
    effect  = "Allow"
    actions = [
      "transcribe:StartTranscriptionJob",
      "transcribe:GetTranscriptionJob",
      "transcribe:DeleteTranscriptionJob"
    ]
    resources = ["*"]
  }

  statement {
    sid     = "Translate"
    effect  = "Allow"
    actions = ["translate:TranslateText"]
    resources = ["*"]
  }

  statement {
    sid     = "Polly"
    effect  = "Allow"
    actions = ["polly:SynthesizeSpeech"]
    resources = ["*"]
  }

  statement {
    sid     = "Logs"
    effect  = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "processor_role_policy" {
  name   = "${aws_iam_role.processor_role.name}-policy"
  role   = aws_iam_role.processor_role.id
  policy = data.aws_iam_policy_document.processor_policy.json
}

resource "aws_cloudwatch_log_group" "processor_lg" {
  name              = "/aws/lambda/${local.processor_name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "processor" {
  function_name = local.processor_name
  role          = aws_iam_role.processor_role.arn
  runtime       = "python3.12"
  handler       = "lambda_function.lambda_handler"
  timeout       = 60
  memory_size   = 256

  filename         = "../lambda/processor/processor.zip"
  source_code_hash = filebase64sha256("../lambda/processor/processor.zip")

  environment {
    variables = {
      BUCKET_NAME      = local.bucket_name
      TARGET_LANGS     = local.target_langs_csv
      POLLY_VOICE_MAP  = local.voice_map_json
    }
  }

  depends_on = [aws_cloudwatch_log_group.processor_lg]
}

resource "aws_lambda_permission" "allow_s3_invoke_processor" {
  statement_id  = "AllowExecutionFromS3-${var.env}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.processor.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.pipeline.arn
}

resource "aws_s3_bucket_notification" "on_audio_upload" {
  bucket = aws_s3_bucket.pipeline.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.processor.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "audio_inputs/"
    filter_suffix       = ".mp3"
  }

  depends_on = [aws_lambda_permission.allow_s3_invoke_processor]
}
