FROM python:3.12-slim-bookworm

ARG TARGETPLATFORM

RUN pip install --upgrade pip
RUN adduser worker

USER worker

WORKDIR /home/worker

COPY --chown=worker:worker requirements.txt ./
RUN if [ "${TARGETPLATFORM}" == "linux/arm/v7" ]; then \
  MSGPACK_PUREPYTHON=1 pip install --user --no-cache-dir -r requirements.txt; \
  else \
  pip install --user --no-cache-dir -r requirements.txt; \
  fi

COPY --chown=worker:worker . ./

ENV PATH="/home/worker/.local/bin:${PATH}"

CMD ["python3", "can2mqtt.py"]
