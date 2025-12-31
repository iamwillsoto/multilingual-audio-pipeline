import boto3
from pathlib import Path

TEXT = "Hi, my name is Will Soto, and this is my multilingual audio pipeline use case."

def main():
    polly = boto3.client("polly")
    resp = polly.synthesize_speech(
        Text=TEXT,
        OutputFormat="mp3",
        VoiceId="Matthew"  # professional English voice
    )

    out_dir = Path("audio_inputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "intro_en.mp3"

    with out_path.open("wb") as f:
        f.write(resp["AudioStream"].read())

    print(f"Created: {out_path}")

if __name__ == "__main__":
    main()
