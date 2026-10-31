FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt update && apt install -y adb && rm -rf /var/lib/apt/lists/*

COPY . /app/

CMD ["python3", "web_remote.py"]
