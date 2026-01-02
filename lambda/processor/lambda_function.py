import os
import json
import time
import uuid
import boto3

s3 = boto3.client("s3")
transcribe = boto3.client("transcribe")
translate = boto3.client("translate")
polly = boto3.client("polly")


def _parse_voice_map() -> dict:
    raw = os.environ.get("VOICE_MAP_JSON", "{}")
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _parse_target_languages() -> list[str]:
    raw = os.environ.get("TARGET_LANGUAGES", "es,fr").strip()
    langs = [x.strip() for x in raw.split(",") if x.strip()]
    return langs or ["es", "fr"]


def _env_from_key_or_metadata(bucket: str, key: str) -> str:
    # Preferred: key prefix (beta/... or prod/...)
    if key.startswith("beta/"):
        return "beta"
    if key.startswith("prod/"):
        return "prod"

    # Fallback: object metadata env=beta|prod
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
        meta = head.get("Metadata", {}) or {}
        env = (meta.get("env") or "").strip().lower()
        if env in ("beta", "prod"):
            return env
    except Exception:
        pass

    # Final fallback: default env from Terraform
    return os.environ.get("ENV_DEFAULT", "beta")


def _wait_for_transcribe(job_name: str, timeout_s: int = 120) -> dict:
    start = time.time()
    while True:
        resp = transcribe.get_transcription_job(TranscriptionJobName=job_name)
        status = resp["TranscriptionJob"]["TranscriptionJobStatus"]
        if status in ("COMPLETED", "FAILED"):
            return resp
        if time.time() - start > timeout_s:
            raise TimeoutError(f"Transcribe job timed out: {job_name}")
        time.sleep(2)


def lambda_handler(event, context):
    # Guard: don't crash on test invokes / manual invokes
    if not event or "Records" not in event:
        print(f"Skipping non-S3 event. Keys={list(event.keys()) if isinstance(event, dict) else type(event)}")
        return {"ok": True, "skipped": True}

    record = event["Records"][0]
    bucket = record["s3"]["bucket"]["name"]
    key = record["s3"]["object"]["key"]

    if not key.lower().endswith(".mp3"):
        print(f"Skipping non-mp3 object: s3://{bucket}/{key}")
        return {"ok": True, "skipped": True}

    env = _env_from_key_or_metadata(bucket, key)
    target_languages = _parse_target_languages()
    voice_map = _parse_voice_map()

    # Expect uploads at: {env}/audio_inputs/<file>.mp3
    filename = key.split("/")[-1]
    base = filename.rsplit(".", 1)[0]

    media_uri = f"s3://{bucket}/{key}"

    # Store the transcribe JSON in S3 so we can fetch reliably without external HTTP
    transcript_json_key = f"{env}/transcripts/{base}.json"

    job_name = f"{env}-{base}-{uuid.uuid4().hex[:8]}"
    print(f"Starting transcribe job={job_name} media={media_uri}")

    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        LanguageCode="en-US",
        Media={"MediaFileUri": media_uri},
        OutputBucketName=bucket,
        OutputKey=transcript_json_key,
    )

    job_resp = _wait_for_transcribe(job_name)
    status = job_resp["TranscriptionJob"]["TranscriptionJobStatus"]
    if status != "COMPLETED":
        reason = job_resp["TranscriptionJob"].get("FailureReason", "unknown")
        raise RuntimeError(f"Transcribe failed: {reason}")

    # Read transcript JSON from S3
    obj = s3.get_object(Bucket=bucket, Key=transcript_json_key)
    transcript_doc = json.loads(obj["Body"].read().decode("utf-8"))
    transcript_text = transcript_doc["results"]["transcripts"][0]["transcript"]

    # Write plain transcript text
    transcript_txt_key = f"{env}/transcripts/{base}.txt"
    s3.put_object(
        Bucket=bucket,
        Key=transcript_txt_key,
        Body=transcript_text.encode("utf-8"),
        ContentType="text/plain; charset=utf-8",
    )

    results = {"env": env, "input": key, "transcript": transcript_txt_key, "outputs": []}

    for lang in target_languages:
        print(f"Translating to {lang}...")
        tr = translate.translate_text(
            Text=transcript_text,
            SourceLanguageCode="en",
            TargetLanguageCode=lang,
        )
        translated = tr["TranslatedText"]

        translation_key = f"{env}/translations/{base}_{lang}.txt"
        s3.put_object(
            Bucket=bucket,
            Key=translation_key,
            Body=translated.encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )

        voice_id = voice_map.get(lang, "Joanna")  # safe fallback
        print(f"Polly synthesize lang={lang} voice={voice_id}")

        audio = polly.synthesize_speech(
            Text=translated,
            OutputFormat="mp3",
            VoiceId=voice_id,
            Engine="neural" if voice_id else "standard",
        )

        audio_key = f"{env}/audio_outputs/{base}_{lang}.mp3"
        s3.put_object(
            Bucket=bucket,
            Key=audio_key,
            Body=audio["AudioStream"].read(),
            ContentType="audio/mpeg",
        )

        results["outputs"].append(
            {"lang": lang, "translation": translation_key, "audio": audio_key, "voice": voice_id}
        )

    # Cleanup job (keeps account tidy)
    try:
        transcribe.delete_transcription_job(TranscriptionJobName=job_name)
    except Exception as e:
        print(f"Warning: could not delete transcription job {job_name}: {e}")

    print("Done:", json.dumps(results))
    return {"ok": True, "results": results}
