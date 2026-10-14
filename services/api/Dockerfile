FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 1000 api
WORKDIR /app

# Dependencies first: this layer is only rebuilt when requirements.txt changes,
# not every time you edit the code.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/

USER api
EXPOSE 8000
# 0.0.0.0 = listen on every interface, so traffic from outside the container
# (the Service, port-forward) can reach it. 127.0.0.1 would only accept itself.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
