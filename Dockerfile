FROM python:3.12-bookworm AS builder

ARG TARGETPLATFORM

COPY requirements.txt .

RUN  apt-get update && apt-get install build-essential -y

RUN pip install --upgrade pip

ARG MSGPACK_PUREPYTHON=1
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.12-slim-bookworm 

RUN adduser worker
COPY --chown=worker:worker --from=builder /root/.local /home/worker/.local

RUN install -o worker -g worker -d /app /conf /logs
VOLUME ["/app","/config","/logs"]

COPY --chown=worker:worker can2mqtt/ /app/

ENV PATH="/home/worker/.local/bin:${PATH}"

USER worker
WORKDIR /app
CMD ["python3", "can2mqtt.py"]
