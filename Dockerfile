FROM python:3.12-slim-bookworm
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY etl ./etl
COPY sql ./sql
COPY tests ./tests
ENTRYPOINT ["python", "-m", "etl"]
CMD ["run"]
