FROM python:3.14-slim AS builder

# No compiler toolchain here on purpose: every runtime dependency (json-cfg,
# parse, python-can, paho-mqtt and their transitive deps) installs from a
# prebuilt wheel, so nothing is built from source. Note that wrapt is a binary
# wheel rather than a pure-Python one, so it only stays source-free while the
# target platforms have wheels published; adding an exotic platform could pull
# build-essential back in.

COPY requirements.txt .

RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.14-slim

RUN adduser worker
RUN install -o worker -g worker -d /config /logs

COPY --chown=worker:worker --from=builder /root/.local /home/worker/.local
COPY --chown=worker:worker can2mqtt/ /app/

VOLUME ["/config","/logs"]
ENV PATH="/home/worker/.local/bin:${PATH}"

USER worker
WORKDIR /app

CMD ["python3", "can2mqtt.py"]
