FROM python:3.12-bookworm AS builder

ARG TARGETPLATFORM

COPY requirements.txt .

RUN  apt-get update && apt-get install build-essential -y

RUN pip install --upgrade pip

RUN if [ "${TARGETPLATFORM}" = "linux/arm/v7" ]; then \
  MSGPACK_PUREPYTHON=1 pip install --user --no-cache-dir -r requirements.txt; \
  else \
  pip install --user --no-cache-dir -r requirements.txt; \
  fi

FROM python:3.12-slim-bookworm 

RUN adduser worker
USER worker
WORKDIR /home/worker

COPY --from=builder --chown=worker:worker /root/.local ./
COPY --chown=worker:worker . ./

ENV PATH="/home/worker/.local/bin:${PATH}"

CMD ["python3", "can2mqtt.py"]
