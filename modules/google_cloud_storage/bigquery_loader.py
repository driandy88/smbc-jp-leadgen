import pandas as pd
from google.cloud import bigquery
from loguru import logger

from config.bq import (
    ASPIRE_CUSTOMERS_TABLE_NAME,
    ASPIRE_PROJECT_ID,
    ASPIRE_SALES_PROJECT_ID,
    ASPIRE_SALES_TABLE_NAME,
    GCP_PROJECT_ID,
)
from config.query import aspire_query, sales_after_2023_query


def load_aspire_customers_table_custom_query() -> pd.DataFrame:
    """Load Aspire customers data from BigQuery."""
    bq_client = bigquery.Client(project=GCP_PROJECT_ID)
    df = bq_client.query(aspire_query).to_dataframe()
    logger.info(f"Loaded table {ASPIRE_PROJECT_ID}.{ASPIRE_CUSTOMERS_TABLE_NAME} ({df.shape[0]} rows)")
    return df


def load_aspire_sales_table() -> pd.DataFrame:
    """Load Aspire customers data from BigQuery."""
    bq_client = bigquery.Client(project=GCP_PROJECT_ID)
    df = bq_client.query(sales_after_2023_query).to_dataframe()
    logger.info(f"Loaded table {ASPIRE_SALES_PROJECT_ID}.{ASPIRE_SALES_TABLE_NAME} ({df.shape[0]} rows)")
    return df
