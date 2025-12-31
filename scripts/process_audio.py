import os
import time
import json
import uuid
import requests
import boto3

S3_BUCKET = os.environ["S3_BUCKET"]
ENV_PREFIX = os.environ["ENV_PREFIX"]              # beta or prod
TARGET_LANGS = os.environ.get("TARGET_LANGS", "es,fr").split(",")

INPUT_LOCAL = "audio_inputs/intro_en.mp3"
INPUT_S3_KEY = f"{ENV_PREFIX}/audio_inputs/intro_en.mp3"

def wait_for_transcribe(transcribe, job_name: str, sleep_s=3, timeout_s=300):
    start = time.time()
    while True:
        resp = transcribe.get_transcription_job(TranscriptionJobName=job_name)
        status = resp["TranscriptionJob"]["TranscriptionJobStatus"]
        if status in ("COMPLETED", "FAILED"):
            return resp
        if time.time() - start > timeout_s:
            raise TimeoutError("Transcribe job timed out.")
        time.sleep(sleep_s)

def main():
    s3 = boto3.client("s3")
    transcribe = boto3.client("transcribe")
    translate = boto3.client("translate")
    polly = boto3.client("polly")

    # 1) Upload input mp3
    s3.upload_file(INPUT_LOCAL, S3_BUCKET, INPUT_S3_KEY)
    media_uri = f"s3://{S3_BUCKET}/{INPUT_S3_KEY}"
    print(f"Uploaded input: {media_uri}")

    # 2) Transcribe
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
        raise RuntimeError(f"Transcribe failed: {result}")

    # 3) Fetch transcript text
    transcript_uri = result["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
    transcript_json = requests.get(transcript_uri, timeout=30).json()
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
        tr = translate.translate_text(
            Text=transcript_text,
            SourceLanguageCode="en",
            TargetLanguageCode=lang
        )["TranslatedText"]

        tr_key = f"{ENV_PREFIX}/translations/intro_en_{lang}.txt"
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=tr_key,
            Body=tr.encode("utf-8"),
            ContentType="text/plain",
        )
        print(f"Wrote translation ({lang}): s3://{S3_BUCKET}/{tr_key}")

        # pick a voice per language
        voice = "Lupe" if lang == "es" else ("Lea" if lang == "fr" else "Joanna")

        audio = polly.synthesize_speech(
            Text=tr,
            OutputFormat="mp3",
            VoiceId=voice
        )["AudioStream"].read()

        audio_key = f"{ENV_PREFIX}/audio_outputs/intro_{lang}.mp3"
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=audio_key,
            Body=audio,
            ContentType="audio/mpeg",
        )
        print(f"Wrote audio ({lang}): s3://{S3_BUCKET}/{audio_key}")

    print("Done.")

if __name__ == "__main__":
    main()
