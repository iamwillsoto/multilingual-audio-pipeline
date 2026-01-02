output "bucket_name" {
  value = aws_s3_bucket.pipeline.bucket
}

output "processor_lambda_name" {
  value = aws_lambda_function.processor.function_name
}

output "processor_log_group" {
  value = aws_cloudwatch_log_group.processor_lg.name
}
