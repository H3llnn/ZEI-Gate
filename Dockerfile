FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/app/data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    https://github.com/H3llnn/ZEI-Userbot/archive/9846ceef3725caf4d843fa239c435e32752a8cdb.tar.gz \
    https://github.com/H3llnn/ZEI-ForceSubs/archive/6ca97f60157588570fb4d9d6661cd041f0fd7708.tar.gz \
    https://github.com/H3llnn/ZEI-Payment/archive/c12cb5d2e550319b87df8295befcc5defba88cf6.tar.gz \
    && useradd --uid 10001 --create-home zei
COPY --chown=zei:zei . .
RUN mkdir -p /app/data && chown zei:zei /app/data
USER zei
CMD ["python", "main.py"]
