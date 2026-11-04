# Uma imagem pequena para CLI e outra com o Airflow, usando o mesmo código.
FROM python:3.12-slim-bookworm AS cli
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY etl ./etl
COPY sql ./sql
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "etl/etl.py"]
CMD ["run"]

FROM apache/airflow:3.3.2-python3.12 AS airflow
WORKDIR /app
COPY --chown=airflow:root requirements.txt ./
# Os providers disponibilizam os tipos Microsoft SQL Server e Postgres na interface.
RUN pip install --no-cache-dir "apache-airflow==3.3.2" "psycopg2-binary==2.9.13" \
    apache-airflow-providers-microsoft-mssql apache-airflow-providers-postgres -r requirements.txt \
    --constraint https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.12.txt
COPY --chown=airflow:root etl ./etl
COPY --chown=airflow:root iniciar_airflow.py ./
COPY --chown=airflow:root sql ./sql
COPY --chown=airflow:root dags ./dags
ENV PYTHONPATH=/app/etl PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["python", "/app/iniciar_airflow.py"]
