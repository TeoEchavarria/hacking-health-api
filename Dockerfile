FROM python:3.11-slim

# ffmpeg is required by pydub for audio processing (M4A/3GP decoding, MP3 export)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "src.main:app", "--host=0.0.0.0", "--port=8080"]
