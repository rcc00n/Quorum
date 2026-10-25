FROM python:3.12-slim
WORKDIR /app
COPY collectors/requirements.txt collectors/requirements.txt
RUN pip install --no-cache-dir -r collectors/requirements.txt
COPY collectors/ collectors/
COPY agent/ agent/
ENV PYTHONUNBUFFERED=1
# One pass every 15 minutes; the runner is idempotent and skips unchanged documents.
CMD ["python3", "-m", "collectors.run", "--loop", "900"]
