# Multilingual Audio Pipeline on AWS (Event-Driven, Terraform)

## Overview

This repository implements an automated multilingual audio transformation pipeline on AWS. The solution converts uploaded `.mp3` files into transcribed text, translated text, and synthesized speech using managed AWS services. All infrastructure is deployed with Terraform, and execution is orchestrated via GitHub Actions with environment-aware outputs.

---

## Architecture Summary

- **GitHub Actions** orchestrates deployments and pipeline execution
- **Amazon S3** stores inputs/outputs and emits events
- **AWS Lambda** runs the processing workflow (Transcribe → Translate → Polly)
- **Terraform** provisions and configures all infrastructure
- **IAM** applies least-privilege permissions

High-level flow:
1. An `.mp3` file is uploaded to S3.
2. An S3 event triggers a Lambda function.
3. Lambda:
   - Transcribes audio to text (Amazon Transcribe)
   - Translates the transcript (Amazon Translate)
   - Synthesizes translated speech (Amazon Polly)
4. Outputs are written back to S3 under structured prefixes.

---

## Repository Structure

```
├── .github/workflows/
│ ├── on_pull_request.yml # PR validation + beta deployment/execution
│ └── on_merge.yml # Production deployment/execution
├── audio_inputs/ # Sample audio files (.mp3)
├── infra/ # Terraform definitions
│ ├── main.tf
│ ├── variables.tf
│ ├── outputs.tf
│ ├── provider.tf
│ └── versions.tf
├── lambda/
│ └── processor/
│ └── lambda_function.py # Transcribe → Translate → Polly
├── scripts/ # Local helper scripts (optional)
├── requirements.txt
└── README.md
```


---

## Environment-Aware Output Layout

Outputs are stored in S3 using an environment prefix (e.g., `beta/` or `prod/`) and consistent subpaths:

```
s3://<bucket>/<env>/transcripts/<filename>.txt
s3://<bucket>/<env>/translations/<filename><lang>.txt
s3://<bucket>/<env>/audio_outputs/<filename><lang>.mp3
```


This enables safe validation in `beta/` before promotion to `prod/`.

---

## Infrastructure as Code (Terraform)

Terraform provisions the full solution, including:
- S3 bucket and event notifications
- Lambda function and execution role
- IAM policies for S3 + Transcribe + Translate + Polly
- Environment-scoped naming and configuration

GitHub Actions can be used to deploy infrastructure per environment:
- Pull request workflows target **beta**
- Merge-to-main workflows target **production**

---

## Security & Credential Management

No credentials are stored in code. Configure repository secrets for GitHub Actions:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION`
- `S3_BUCKET`

IAM is designed for least-privilege access (S3 object read/write for required prefixes and the specific AI service calls required by the pipeline).

---

## How to Run

### 1) Configure GitHub Secrets
Add the required secrets under repository Settings → Secrets and variables → Actions.

### 2) Upload or Provide Audio Inputs
Place `.mp3` files in `audio_inputs/` for testing and/or upload to the S3 input prefix used by the pipeline.

### 3) Trigger Pipeline Execution
- Open a PR to run beta validation/execution (writes to `beta/`)
- Merge to `main` to run production execution (writes to `prod/`)
- Optionally run the merge workflow manually if `workflow_dispatch` is enabled

### 4) Verify Outputs in S3
Confirm that transcripts, translations, and generated audio files exist under the appropriate environment prefix.

---

## Design Rationale

This implementation is designed to be:
- Fully automated and event-driven
- Reproducible via Infrastructure as Code
- Environment-aware without duplicating stacks
- Secure via least-privilege IAM
- Operationally aligned with real-world CI/CD practices

---
