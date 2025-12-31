# scripts/process_audio.py

import os
import time
import json
import uuid
import requests
import boto3

def fetch_transcript_json(url: str, retries: int = 12, sleep_s: int = 2) -> dict:
    last_text = ""
    last_status = None

    for _ in range(retries):
        r = requests.get(url, timeout=30)
        last_status = r.status_code
        last_text = (r.text or "").strip()

        if not last_text:
            time.sleep(sleep_s)
            continue

        # Try JSON parse
        try:
            return r.json()
        except Exception:
            try:
                return json.loads(last_text)
            except Exception:
                time.sleep(sleep_s)

    raise RuntimeError(
        f"Could not fetch/parse transcript JSON. status={last_status} body_preview={last_text[:200]!r}"
    )

# --- Region (explicit) ---
REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
if not REGION:
    raise RuntimeError("Missing AWS region. Set AWS_REGION or AWS_DEFAULT_REGION.")

# --- Required env vars ---
S3_BUCKET = os.environ["S3_BUCKET"]
ENV_PREFIX = os.environ["ENV_PREFIX"]  # beta or prod
TARGET_LANGS = os.environ.get("TARGET_LANGS", "es,fr").split(",")

# --- Local + S3 input locations ---
INPUT_LOCAL = "audio_inputs/intro_en.mp3"
INPUT_S3_KEY = f"{ENV_PREFIX}/audio_inputs/intro_en.mp3"


def wait_for_transcribe(transcribe_client, job_name: str, sleep_s: int = 3, timeout_s: int = 300):
    start = time.time()
    while True:
        resp = transcribe_client.get_transcription_job(TranscriptionJobName=job_name)
        status = resp["TranscriptionJob"]["TranscriptionJobStatus"]

        if status in ("COMPLETED", "FAILED"):
            return resp

        if time.time() - start > timeout_s:
            raise TimeoutError("Transcribe job timed out.")

        time.sleep(sleep_s)


def pick_voice(lang: str) -> str:
    # Simple voice mapping for demo
    if lang == "es":
        return "Lupe"   # Spanish
    if lang == "fr":
        return "Lea"    # French
    return "Joanna"     # Fallback


def main():
    # --- AWS clients with explicit region ---
    s3 = boto3.client("s3", region_name=REGION)
    transcribe = boto3.client("transcribe", region_name=REGION)
    translate = boto3.client("translate", region_name=REGION)
    polly = boto3.client("polly", region_name=REGION)

    # 1) Upload input mp3
    s3.upload_file(INPUT_LOCAL, S3_BUCKET, INPUT_S3_KEY)
    media_uri = f"s3://{S3_BUCKET}/{INPUT_S3_KEY}"
    print(f"Uploaded input: {media_uri}")

    # 2) Transcribe (unique job name)
    job_name = f"{ENV_PREFIX}-intro-{uuid.uuid4().hex[:10]}"
    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        LanguageCode="en-US",
        MediaFormat="mp3",
        Media={"MediaFileUri": media_uri},
        OutputBucketName=S3_BUCKET,
        OutputKey=f"{ENV_PREFIX}/transcribe_raw/{job_name}.json",
    )

    result = wait_for_transcribe(transcribe, job_name)
    status = result["TranscriptionJob"]["TranscriptionJobStatus"]
    if status != "COMPLETED":
        raise RuntimeError(f"Transcribe failed: {json.dumps(result, indent=2, default=str)}")

    # 3) Fetch transcript text from S3 output (avoid HTTPS 403 issues)
    transcribe_out_key = f"{ENV_PREFIX}/transcribe_raw/{job_name}.json"
    print(f"Reading transcript JSON from s3://{S3_BUCKET}/{transcribe_out_key}")

    obj = s3.get_object(Bucket=S3_BUCKET, Key=transcribe_out_key)
    transcript_json = json.loads(obj["Body"].read().decode("utf-8"))

    transcript_text = transcript_json["results"]["transcripts"][0]["transcript"].strip()
    print(f"Transcript: {transcript_text}")

    # 4) Save transcript to S3
    transcript_key = f"{ENV_PREFIX}/transcripts/intro_en.txt"
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=transcript_key,
        Body=transcript_text.encode("utf-8"),
        ContentType="text/plain",
    )
    print(f"Wrote transcript: s3://{S3_BUCKET}/{transcript_key}")

    # 5) Translate + synthesize for each language
    for lang in [l.strip() for l in TARGET_LANGS if l.strip()]:
        # Translate
        translated = translate.translate_text(
            Text=transcript_text,
            SourceLanguageCode="en",
            TargetLanguageCode=lang,
        )["TranslatedText"]

        translation_key = f"{ENV_PREFIX}/translations/intro_en_{lang}.txt"
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=translation_key,
            Body=translated.encode("utf-8"),
            ContentType="text/plain",
        )
        print(f"Wrote translation ({lang}): s3://{S3_BUCKET}/{translation_key}")

        # Polly synthesize
        voice = pick_voice(lang)
        audio_bytes = polly.synthesize_speech(
            Text=translated,
            OutputFormat="mp3",
            VoiceId=voice,
        )["AudioStream"].read()

        audio_key = f"{ENV_PREFIX}/audio_outputs/intro_{lang}.mp3"
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=audio_key,
            Body=audio_bytes,
            ContentType="audio/mpeg",
        )
        print(f"Wrote audio ({lang}): s3://{S3_BUCKET}/{audio_key}")

    print("Done.")


if __name__ == "__main__":
    main()
