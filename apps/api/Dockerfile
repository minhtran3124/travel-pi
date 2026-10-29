FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# psycopg[binary] ships its own libpq, so no apt postgresql-client needed.
# requirements.txt pulls in requirements-ai.txt (the LangChain/LangGraph stack).
COPY requirements.txt requirements-ai.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x docker/entrypoint.sh docker/start-web.sh \
    && useradd --system --create-home --uid 10001 app \
    && chown -R app:app /app
USER app

EXPOSE 8000
ENTRYPOINT ["docker/entrypoint.sh"]
# Production start (gunicorn). Dev compose overrides `command` with uvicorn --reload.
CMD ["docker/start-web.sh"]
