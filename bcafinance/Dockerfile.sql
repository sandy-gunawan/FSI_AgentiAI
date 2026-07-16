# bcafinance credit-context tools (REST + MCP) over SQL Server 2019.
FROM python:3.13-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/srv
# pymssql needs FreeTDS runtime libs.
RUN apt-get update && apt-get install -y --no-install-recommends freetds-dev freetds-bin && \
    rm -rf /var/lib/apt/lists/*
COPY sql_service/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
COPY sql_service ./sql_service
EXPOSE 8000
CMD ["uvicorn", "sql_service.server:app", "--host", "0.0.0.0", "--port", "8000"]
