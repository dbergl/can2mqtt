FROM python:3.12-slim-bookworm

RUN pip install --upgrade pip
RUN adduser worker

USER worker

WORKDIR /home/worker

COPY --chown=worker:worker requirements.txt ./
RUN pip install --user --no-cache-dir -r requirements.txt
COPY --chown=worker:worker . ./

ENV PATH="/home/worker/.local/bin:${PATH}"

CMD ["python3", "can2mqtt.py"]
