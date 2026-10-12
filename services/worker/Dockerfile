# Each instruction below creates one LAYER of the image. Layers are cached:
# when you rebuild, Docker reuses every layer up to the first one that changed.

# Start from an official image that already contains Python on a small Debian.
FROM python:3.14-slim

# Print logs immediately instead of buffering them: otherwise `kubectl logs`
# can stay empty until the process exits.
ENV PYTHONUNBUFFERED=1

# Don't run as root inside the container (good habit; some clusters enforce it).
RUN useradd --create-home --uid 1000 worker

WORKDIR /app

# Copy our code last: it changes most often, so only this layer gets rebuilt.
COPY worker.py .

USER worker

# The command the container runs. STEP / ANALYSIS_ID come from env variables.
CMD ["python", "worker.py"]
