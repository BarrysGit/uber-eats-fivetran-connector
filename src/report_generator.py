"""
Uber Eats Daily Report Generator (Cloud Run Job)
Scheduled to run daily at 7 AM Central Time

This job:
1. Fetches stores from Uber Stores API → stores in UBER_EATS_STORES
2. Triggers report generation via Reports API → returns workflow_id
3. Webhook receiver (separate service) will receive the report when ready

Environment Variables Required:
- UBER_CLIENT_ID, UBER_CLIENT_SECRET (for OAuth; optional if UBER_ACCESS_TOKEN is set)
- UBER_ACCESS_TOKEN (optional): use a manually obtained token to avoid OAuth 403
- SNOWFLAKE_USER, SNOWFLAKE_ACCOUNT, SNOWFLAKE_WAREHOUSE
- SNOWFLAKE_PRIVATE_KEY (or SNOWFLAKE_PASSWORD)
"""

import os
import json
import logging
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
import snowflake.connector
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Uber API Configuration
UBER_CLIENT_ID = os.getenv("UBER_CLIENT_ID", "").strip()
UBER_CLIENT_SECRET = os.getenv("UBER_CLIENT_SECRET", "").strip()
UBER_TOKEN_URL = "https://login.uber.com/oauth/v2/token"
UBER_STORES_API = "https://api.uber.com/v1/eats/stores"
UBER_REPORTS_API = "https://api.uber.com/v1/eats/report"

# Snowflake Configuration (same as webhook receiver)
SNOWFLAKE_USER = os.getenv("SNOWFLAKE_USER", "").strip()
SNOWFLAKE_ACCOUNT = os.getenv("SNOWFLAKE_ACCOUNT", "").strip()
SNOWFLAKE_WAREHOUSE = os.getenv("SNOWFLAKE_WAREHOUSE", "").strip()
SNOWFLAKE_DATABASE = os.getenv("SNOWFLAKE_DATABASE_UBER", "PC_FIVETRAN_DB")
SNOWFLAKE_SCHEMA = os.getenv("SNOWFLAKE_SCHEMA_UBER", "UBER_EATS")
SNOWFLAKE_PASSWORD = os.getenv("SNOWFLAKE_PASSWORD")
SNOWFLAKE_PRIVATE_KEY = os.getenv("SNOWFLAKE_PRIVATE_KEY")

# Report Configuration
REPORT_TYPE = os.getenv("REPORT_TYPE", "FINANCE_SUMMARY_REPORT")
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "7"))  # Default: last 7 days


def get_access_token() -> str:
    """
    Get Uber API access token.
    Uses UBER_ACCESS_TOKEN from env if set (manual token fallback when client credentials returns 403).
    Otherwise uses client credentials flow.
    """
    # Fallback: manual token from Secret Manager (avoids OAuth 403 until Uber enables client credentials)
    manual_token = (os.getenv("UBER_ACCESS_TOKEN") or "").strip()
    if manual_token:
        logger.info("🔑 Using UBER_ACCESS_TOKEN from environment (skip OAuth)")
        return manual_token

    logger.info("🔑 Getting Uber API access token via client credentials...")
    payload = {
        "client_id": UBER_CLIENT_ID,
        "client_secret": UBER_CLIENT_SECRET,
        "grant_type": "client_credentials",
        "scope": "eats.report eats.store"
    }
    response = requests.post(UBER_TOKEN_URL, data=payload, timeout=30)
    response.raise_for_status()
    token_data = response.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise ValueError("No access token received from Uber")
    logger.info("✅ Access token obtained")
    return access_token


def get_snowflake_connection():
    """Create and return a Snowflake connection."""
    account = SNOWFLAKE_ACCOUNT
    region = None
    if "." in account:
        parts = account.split(".", 1)
        account = parts[0]
        region = parts[1] if len(parts) > 1 else None
    
    conn_params = {
        "account": account,
        "user": SNOWFLAKE_USER,
        "warehouse": SNOWFLAKE_WAREHOUSE,
        "database": SNOWFLAKE_DATABASE,
        "schema": SNOWFLAKE_SCHEMA,
        "insecure_mode": False,
        "ocsp_fail_open": True,
    }
    
    if region:
        conn_params["region"] = region
    
    # Try private key authentication first
    if SNOWFLAKE_PRIVATE_KEY:
        try:
            private_key_str = SNOWFLAKE_PRIVATE_KEY.strip()
            if not private_key_str.startswith("-----BEGIN"):
                private_key_str = f"-----BEGIN PRIVATE KEY-----\n{private_key_str}\n-----END PRIVATE KEY-----"
            
            private_key_bytes = private_key_str.encode("utf-8")
            p_key = serialization.load_pem_private_key(
                private_key_bytes,
                password=None,
                backend=default_backend()
            )
            
            pkb = p_key.private_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            
            conn_params["private_key"] = pkb
            logger.info("Using private key authentication")
        except Exception as e:
            logger.warning(f"Private key auth failed: {e}, falling back to password")
            if SNOWFLAKE_PASSWORD:
                conn_params["password"] = SNOWFLAKE_PASSWORD
    elif SNOWFLAKE_PASSWORD:
        conn_params["password"] = SNOWFLAKE_PASSWORD
    
    return snowflake.connector.connect(**conn_params)


def fetch_stores(access_token: str) -> List[Dict[str, Any]]:
    """Fetch all stores from Uber Stores API."""
    logger.info("🏪 Fetching stores from Uber API...")
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    all_stores = []
    next_page = None
    page = 1
    
    while True:
        params = {"limit": 100}
        if next_page:
            params["page_token"] = next_page
        
        response = requests.get(UBER_STORES_API, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        stores = data.get("stores", [])
        all_stores.extend(stores)
        
        logger.info(f"  Page {page}: fetched {len(stores)} stores (total: {len(all_stores)})")
        
        next_page = data.get("next_page_token")
        if not next_page:
            break
        
        page += 1
    
    logger.info(f"✅ Fetched {len(all_stores)} stores total")
    return all_stores


def store_stores_in_snowflake(conn, stores: List[Dict[str, Any]]) -> int:
    """Store fetched stores in UBER_EATS_STORES table using MERGE for upsert."""
    if not stores:
        logger.info("No stores to store")
        return 0
    
    logger.info(f"💾 Storing {len(stores)} stores in Snowflake...")
    
    cursor = conn.cursor()
    
    # Tables are managed by Fivetran/admin - skip CREATE TABLE, just MERGE
    # Use MERGE to upsert stores
    synced_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    # Note: RAW_DATA column excluded — Fivetran-created table doesn't have it
    merge_query = f"""
    MERGE INTO {SNOWFLAKE_SCHEMA}.UBER_EATS_STORES AS target
    USING (
        SELECT 
            %s AS STORE_ID,
            %s AS NAME,
            %s AS LOCATION_ADDRESS,
            %s AS LOCATION_CITY,
            %s AS LOCATION_STATE,
            %s AS LOCATION_POSTAL_CODE,
            %s AS LOCATION_COUNTRY,
            %s AS TIMEZONE,
            %s AS STATUS,
            %s AS WEB_URL,
            %s AS _FIVETRAN_SYNCED,
            %s AS _FIVETRAN_DELETED
    ) AS source
    ON target.STORE_ID = source.STORE_ID
    WHEN MATCHED THEN
        UPDATE SET
            NAME = source.NAME,
            LOCATION_ADDRESS = source.LOCATION_ADDRESS,
            LOCATION_CITY = source.LOCATION_CITY,
            LOCATION_STATE = source.LOCATION_STATE,
            LOCATION_POSTAL_CODE = source.LOCATION_POSTAL_CODE,
            LOCATION_COUNTRY = source.LOCATION_COUNTRY,
            TIMEZONE = source.TIMEZONE,
            STATUS = source.STATUS,
            WEB_URL = source.WEB_URL,
            _FIVETRAN_SYNCED = source._FIVETRAN_SYNCED,
            _FIVETRAN_DELETED = source._FIVETRAN_DELETED
    WHEN NOT MATCHED THEN
        INSERT (
            STORE_ID, NAME, LOCATION_ADDRESS, LOCATION_CITY, LOCATION_STATE,
            LOCATION_POSTAL_CODE, LOCATION_COUNTRY, TIMEZONE, STATUS, WEB_URL,
            _FIVETRAN_SYNCED, _FIVETRAN_DELETED
        ) VALUES (
            source.STORE_ID, source.NAME, source.LOCATION_ADDRESS, source.LOCATION_CITY,
            source.LOCATION_STATE, source.LOCATION_POSTAL_CODE, source.LOCATION_COUNTRY,
            source.TIMEZONE, source.STATUS, source.WEB_URL,
            source._FIVETRAN_SYNCED, source._FIVETRAN_DELETED
        )
    """
    
    upserted = 0
    for store in stores:
        store_id = store.get("store_id", "")
        location = store.get("location", {})
        
        cursor.execute(merge_query, (
            store_id,
            store.get("name", ""),
            location.get("address", ""),
            location.get("city", ""),
            location.get("state", ""),
            location.get("postal_code", ""),
            location.get("country", ""),
            store.get("timezone", ""),
            store.get("status", ""),
            store.get("web_url", ""),
            synced_at,
            False
        ))
        upserted += 1
    
    conn.commit()
    logger.info(f"✅ Upserted {upserted} stores into UBER_EATS_STORES")
    return upserted


def trigger_report(access_token: str, store_uuids: List[str]) -> Optional[str]:
    """Trigger report generation via Reports API."""
    logger.info(f"📊 Triggering {REPORT_TYPE} report for {len(store_uuids)} stores...")
    
    # Calculate date range (last N days)
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=LOOKBACK_DAYS)
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "report_type": REPORT_TYPE,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "store_uuids": store_uuids
    }
    
    logger.info(f"  Date range: {start_date} to {end_date}")
    
    response = requests.post(UBER_REPORTS_API, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    
    result = response.json()
    workflow_id = result.get("workflow_id") or result.get("workflow_uuid") or result.get("uuid")
    
    if workflow_id:
        logger.info(f"✅ Report triggered successfully: workflow_id={workflow_id}")
        logger.info(f"   Webhook will be sent to your receiver when report is ready")
        return workflow_id
    else:
        logger.warning(f"⚠️  Report API returned but no workflow_id found: {result}")
        return None


def main():
    """Main execution function."""
    logger.info("=" * 60)
    logger.info("🚀 Starting Uber Eats Daily Report Generator")
    logger.info("=" * 60)
    
    try:
        # Step 1: Get access token
        access_token = get_access_token()
        
        # Step 2: Fetch stores
        stores = fetch_stores(access_token)
        
        # Step 3: Store stores in Snowflake
        conn = get_snowflake_connection()
        store_stores_in_snowflake(conn, stores)
        
        # Step 4: Extract store UUIDs for report
        # Uber API returns "store_id" field (not "id")
        store_uuids = [store.get("store_id") for store in stores if store.get("store_id")]
        
        if not store_uuids:
            logger.error("❌ No store UUIDs found - cannot trigger report")
            return 1
        
        # Step 5: Trigger report generation
        workflow_id = trigger_report(access_token, store_uuids)
        
        if workflow_id:
            logger.info("")
            logger.info("=" * 60)
            logger.info("✅ Job completed successfully!")
            logger.info(f"   - Stores synced: {len(stores)}")
            logger.info(f"   - Report workflow_id: {workflow_id}")
            logger.info("   - Webhook will arrive when report is ready")
            logger.info("=" * 60)
            return 0
        else:
            logger.error("❌ Failed to trigger report")
            return 1
            
    except Exception as e:
        logger.error(f"❌ Job failed: {e}", exc_info=True)
        return 1
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    exit(main())
