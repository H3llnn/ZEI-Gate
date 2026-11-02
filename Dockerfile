FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/app/data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt https://github.com/H3llnn/ZEI-Userbot/archive/eb5998e26fc70249a7d349f5d2ff649160ca0ecf.tar.gz && useradd --uid 10001 --create-home zei
COPY --chown=zei:zei . .
RUN mkdir -p /app/data && chown zei:zei /app/data
USER zei
CMD ["python", "main.py"]
