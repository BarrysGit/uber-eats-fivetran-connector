"""
Uber Eats Webhook Verifier (Direct to Snowflake)
Receives webhooks from Uber Eats, verifies HMAC signature, and stores directly in Snowflake.
This eliminates the need for the Fivetran Webhooks connector.
"""

import os
import json
import hmac
import hashlib
import logging
import time
import requests
import csv
import io
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from fastapi import FastAPI, Request, Header, HTTPException, status, Query
from fastapi.responses import PlainTextResponse, RedirectResponse, JSONResponse
import snowflake.connector

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Uber Eats Webhook Verifier (Snowflake)")

# Snowflake Configuration - Use same credentials as solidcore-scraper
# User, Account, Warehouse come from secrets (same as solidcore-scraper)
SNOWFLAKE_USER = os.getenv("SNOWFLAKE_USER", "").strip()  # From secret (GITHUB_ACTIONS)
SNOWFLAKE_ACCOUNT = os.getenv("SNOWFLAKE_ACCOUNT", "").strip()  # From secret
SNOWFLAKE_WAREHOUSE = os.getenv("SNOWFLAKE_WAREHOUSE", "").strip()  # From secret

# Database/Schema - read from env vars set on Cloud Run
SNOWFLAKE_DATABASE = os.getenv("SNOWFLAKE_DATABASE", "UBER_EATS_CLOUDRUN")
SNOWFLAKE_SCHEMA = os.getenv("SNOWFLAKE_SCHEMA", "UBER_EATS")

PORT = int(os.getenv("PORT", "8080"))

# ============================================================================
# UBER CREDENTIALS CONFIGURATION
# ============================================================================

# --------------------------------------------------------------------------
# OLD CREDENTIALS - Stores/Reporting Webhook App (DO NOT MODIFY)
# --------------------------------------------------------------------------
# These credentials are for the EXISTING Uber Eats Stores/Reporting application.
# Used ONLY for webhook signature verification.
# Loaded from environment variables / Secret Manager.
# DO NOT change these variable names or the webhook will break.
# --------------------------------------------------------------------------

UBER_CLIENT_SECRET = os.getenv("UBER_CLIENT_SECRET")  # For webhook HMAC verification

# --------------------------------------------------------------------------
# NEW CREDENTIALS - Orders/OAuth App (TEMPORARY HARDCODED)
# --------------------------------------------------------------------------
# These credentials are for the NEW Uber Eats Orders application.
# Used ONLY for OAuth authorization code flow.
# TEMPORARY: Hardcoded for testing. Will move to environment variables later.
# --------------------------------------------------------------------------

UBER_ORDERS_CLIENT_ID = "i1KUU09cNgeeoZzzXsRK1I0ZejG-JYAd"  # TODO: Move to env var
UBER_ORDERS_CLIENT_SECRET = "lVetX2dHhtUliItt8tl9EtuXQ5xt5iX1abFc0cCU"  # TODO: Move to env var
UBER_ORDERS_REDIRECT_URI = os.getenv("UBER_ORDERS_REDIRECT_URI", "").strip()  # Will be set in Cloud Run

# ============================================================================

# Snowflake credentials (shared by both apps)
SNOWFLAKE_PASSWORD = os.getenv("SNOWFLAKE_PASSWORD")
SNOWFLAKE_PRIVATE_KEY = os.getenv("SNOWFLAKE_PRIVATE_KEY")  # Same secret as solidcore-scraper

# Validate required sensitive environment variables
# NOTE: Only validating OLD webhook app credentials here (required for startup)
# NEW Orders OAuth credentials validated only when OAuth endpoints are called
required_vars = {
    "UBER_CLIENT_SECRET": UBER_CLIENT_SECRET,  # OLD webhook app secret
    "SNOWFLAKE_USER": SNOWFLAKE_USER,
    "SNOWFLAKE_ACCOUNT": SNOWFLAKE_ACCOUNT,
    "SNOWFLAKE_WAREHOUSE": SNOWFLAKE_WAREHOUSE,
}

# Either password or private key must be provided
if not SNOWFLAKE_PASSWORD and not SNOWFLAKE_PRIVATE_KEY:
    required_vars["SNOWFLAKE_PASSWORD or SNOWFLAKE_PRIVATE_KEY"] = None

missing = [k for k, v in required_vars.items() if not v]
if missing:
    raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

logger.info(f"Webhook verifier initialized (direct to Snowflake - Fivetran schema)")
logger.info(f"Snowflake: {SNOWFLAKE_ACCOUNT}/{SNOWFLAKE_DATABASE}.{SNOWFLAKE_SCHEMA}")
logger.info(f"Snowflake User: {SNOWFLAKE_USER}")
logger.info(f"Auth Method: {'Private Key' if SNOWFLAKE_PRIVATE_KEY else 'Password' if SNOWFLAKE_PASSWORD else 'None'}")


def get_snowflake_connection():
    """Create and return a Snowflake connection."""
    # Parse account and region
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
    
    # Try private key authentication first, then fallback to password
    if SNOWFLAKE_PRIVATE_KEY:
        # Private key authentication (preferred)
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        
        try:
            # Load the private key from PEM format
            private_key_str = SNOWFLAKE_PRIVATE_KEY.strip()
            
            # Log key presence (but not the actual key)
            logger.info(f"Attempting private key authentication for user: {SNOWFLAKE_USER}")
            logger.debug(f"Private key length: {len(private_key_str)} chars")
            
            private_key = serialization.load_pem_private_key(
                private_key_str.encode('utf-8'),
                password=None,
                backend=default_backend()
            )
            
            # Serialize private key to DER format for Snowflake (required format)
            private_key_der = private_key.private_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            
            conn_params["private_key"] = private_key_der
            logger.info("Private key parsed successfully, attempting connection...")
            
            # Try connection with private key
            try:
                conn = snowflake.connector.connect(**conn_params)
                logger.info(f"Successfully connected to Snowflake as {SNOWFLAKE_USER} using private key")
                return conn
            except Exception as key_error:
                # If private key fails with JWT error, try password as fallback
                if "JWT token is invalid" in str(key_error) or "250001" in str(key_error):
                    logger.warning(f"Private key authentication failed (likely wrong user): {str(key_error)}")
                    if SNOWFLAKE_PASSWORD:
                        logger.info(f"Falling back to password authentication for user: {SNOWFLAKE_USER}")
                        # Remove private key and use password instead
                        conn_params.pop("private_key", None)
                        conn_params["password"] = SNOWFLAKE_PASSWORD
                        conn = snowflake.connector.connect(**conn_params)
                        logger.info(f"Successfully connected to Snowflake as {SNOWFLAKE_USER} using password")
                        return conn
                    else:
                        logger.error("Private key failed and no password available for fallback")
                        raise ValueError(f"Private key authentication failed for user {SNOWFLAKE_USER}. "
                                       f"Error: {str(key_error)}. "
                                       f"Note: Each Snowflake user requires their own private key. "
                                       f"If this key is for a different user, use SNOWFLAKE_PASSWORD instead.")
                else:
                    # Re-raise other errors
                    raise
        except Exception as e:
            logger.error(f"Failed to parse private key: {str(e)}", exc_info=True)
            # If parsing fails, try password if available
            if SNOWFLAKE_PASSWORD:
                logger.warning(f"Private key parsing failed, falling back to password: {str(e)}")
                conn_params.pop("private_key", None)
                conn_params["password"] = SNOWFLAKE_PASSWORD
                conn = snowflake.connector.connect(**conn_params)
                logger.info(f"Successfully connected to Snowflake as {SNOWFLAKE_USER} using password")
                return conn
            else:
                raise ValueError(f"Invalid SNOWFLAKE_PRIVATE_KEY format: {str(e)}")
    elif SNOWFLAKE_PASSWORD:
        # Password authentication (fallback)
        conn_params["password"] = SNOWFLAKE_PASSWORD
        logger.info(f"Using password authentication for user: {SNOWFLAKE_USER}")
        conn = snowflake.connector.connect(**conn_params)
        logger.info(f"Successfully connected to Snowflake as {SNOWFLAKE_USER}")
        return conn
    else:
        logger.error("Neither SNOWFLAKE_PASSWORD nor SNOWFLAKE_PRIVATE_KEY is available")
        raise ValueError("Either SNOWFLAKE_PASSWORD or SNOWFLAKE_PRIVATE_KEY must be provided")


def verify_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """
    Verify HMAC SHA-256 signature using constant-time comparison.
    
    Args:
        raw_body: Raw request body bytes
        signature: Signature from X-Uber-Signature header
        secret: Uber client secret
        
    Returns:
        True if signature is valid, False otherwise
    """
    # Compute HMAC SHA-256
    computed = hmac.new(
        secret.encode('utf-8'),
        raw_body,
        hashlib.sha256
    ).hexdigest().lower()
    
    # Constant-time comparison to prevent timing attacks
    signature_lower = signature.lower()
    if len(signature_lower) != len(computed):
        return False
    
    return hmac.compare_digest(signature_lower, computed)


def download_csv_from_url(url: str, timeout: int = 60, max_retries: int = 3) -> Optional[List[Dict[str, Any]]]:
    """
    Download and parse CSV from Uber's download URL.
    Retries on transient failures (e.g. 5xx, connection errors).
    
    Args:
        url: CSV download URL from webhook
        timeout: Request timeout in seconds
        max_retries: Number of retry attempts
        
    Returns:
        List of CSV rows as dictionaries, or None if failed
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            logger.info(f"Downloading CSV from URL (attempt {attempt + 1}/{max_retries}): {url[:100]}...")
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            
            # Parse CSV — strip BOM and clean column names
            csv_content = response.content.decode('utf-8-sig')  # utf-8-sig strips BOM
            csv_reader = csv.DictReader(io.StringIO(csv_content))
            raw_rows = list(csv_reader)
            # Clean column names: strip whitespace and newlines
            rows = [
                {k.strip(): v for k, v in row.items()}
                for row in raw_rows
            ]
            
            logger.info(f"✅ Downloaded and parsed CSV: {len(rows)} rows")
            return rows
            
        except requests.exceptions.RequestException as e:
            last_error = e
            status = getattr(e.response, "status_code", None) if hasattr(e, "response") and e.response is not None else None
            if attempt < max_retries - 1 and (status is None or status >= 500):
                wait = (attempt + 1) * 2
                logger.warning(f"Download attempt {attempt + 1} failed ({e}), retrying in {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"Failed to download CSV from URL: {str(e)}")
                return None
        except Exception as e:
            last_error = e
            logger.error(f"Failed to download CSV from URL: {str(e)}")
            return None
    logger.error(f"Failed after {max_retries} attempts: {last_error}")
    return None


def store_webhook_in_snowflake(payload: Dict[str, Any], headers: Dict[str, str]) -> bool:
    """
    Store webhook in Snowflake matching Fivetran's UBER_EATS_REPORTS schema.
    
    Args:
        payload: Parsed webhook payload
        headers: Request headers
        
    Returns:
        True if successful, False otherwise
    """
    try:
        conn = get_snowflake_connection()
        cursor = conn.cursor()
        
        # Extract fields from payload (matching Fivetran structure)
        event_id = payload.get("event_id", "")
        job_id = payload.get("job_id", "")
        event_type = payload.get("event_type", "")
        report_type = payload.get("report_type", "")
        start_time_ms = payload.get("start_time_ms", 0)
        end_time_ms = payload.get("end_time_ms", 0)
        
        # Convert timestamps to dates
        start_date = datetime.fromtimestamp(start_time_ms / 1000, tz=timezone.utc).date() if start_time_ms else None
        end_date = datetime.fromtimestamp(end_time_ms / 1000, tz=timezone.utc).date() if end_time_ms else None
        created_at_utc = datetime.now(timezone.utc)
        
        # Extract download URL and store_uuids from report_metadata
        report_metadata = payload.get("report_metadata", {})
        sections = report_metadata.get("sections", [])
        
        # Get first section's download_url (Fivetran style - single URL)
        download_url = sections[0].get("download_url") if len(sections) > 0 else None
        
        # Store_uuids - from webhook if present, else empty (Fivetran-compatible)
        raw_uuids = report_metadata.get("store_uuids") or payload.get("store_uuids")
        store_uuids = raw_uuids if isinstance(raw_uuids, list) else []
        
        # Current timestamp
        synced_at = datetime.now(timezone.utc)
        
        # Tables are Fivetran-managed and already exist — skip CREATE TABLE

        # Check if we should download CSV immediately
        should_download_csv = event_type == "eats.report.success" and download_url
        downloaded_at_utc = None
        csv_row_count = 0
        
        # Download CSV if this is a report success event
        if should_download_csv:
            logger.info(f"Report success event - attempting to download CSV from: {download_url[:100]}...")
            csv_rows = download_csv_from_url(download_url)
            
            if csv_rows:
                # Store CSV data in UBER_EATS_REPORT_DATA table
                if store_report_data(conn, event_id, csv_rows):
                    downloaded_at_utc = datetime.now(timezone.utc)
                    csv_row_count = len(csv_rows)
                    logger.info(f"✅ Downloaded and stored {csv_row_count} rows in UBER_EATS_REPORT_DATA")
                else:
                    logger.warning(f"Failed to store CSV data")
            else:
                logger.warning(f"Failed to download CSV from URL")
        
        # Use MERGE to prevent duplicates (idempotent - same webhook twice = same result)
        merge_query = f"""
        MERGE INTO {SNOWFLAKE_SCHEMA}.UBER_EATS_REPORTS AS target
        USING (
            SELECT 
                %s AS WORKFLOW_ID,
                %s AS REPORT_TYPE,
                %s AS STATUS,
                %s AS START_DATE,
                %s AS END_DATE,
                PARSE_JSON(%s) AS STORE_UUIDS,
                %s AS DOWNLOAD_URL,
                %s AS CREATED_AT_UTC,
                %s AS DOWNLOADED_AT_UTC,
                %s AS _FIVETRAN_SYNCED,
                %s AS _FIVETRAN_DELETED
        ) AS source
        ON target.WORKFLOW_ID = source.WORKFLOW_ID
        WHEN MATCHED THEN
            UPDATE SET
                REPORT_TYPE = source.REPORT_TYPE,
                STATUS = source.STATUS,
                START_DATE = source.START_DATE,
                END_DATE = source.END_DATE,
                DOWNLOAD_URL = COALESCE(target.DOWNLOAD_URL, source.DOWNLOAD_URL),
                DOWNLOADED_AT_UTC = COALESCE(source.DOWNLOADED_AT_UTC, target.DOWNLOADED_AT_UTC),
                _FIVETRAN_SYNCED = source._FIVETRAN_SYNCED
        WHEN NOT MATCHED THEN
            INSERT (
                WORKFLOW_ID, REPORT_TYPE, STATUS, START_DATE, END_DATE, 
                STORE_UUIDS, DOWNLOAD_URL, CREATED_AT_UTC, DOWNLOADED_AT_UTC,
                _FIVETRAN_SYNCED, _FIVETRAN_DELETED
            ) VALUES (
                source.WORKFLOW_ID, source.REPORT_TYPE, source.STATUS, 
                source.START_DATE, source.END_DATE, source.STORE_UUIDS, 
                source.DOWNLOAD_URL, source.CREATED_AT_UTC, source.DOWNLOADED_AT_UTC,
                source._FIVETRAN_SYNCED, source._FIVETRAN_DELETED
            )
        """
        
        cursor.execute(merge_query, (
            event_id,  # Use event_id as workflow_id (like Fivetran)
            report_type or "",
            "COMPLETED",  # Webhook means report is complete
            start_date,
            end_date,
            json.dumps(store_uuids),  # Empty for now
            download_url or "",
            created_at_utc,
            downloaded_at_utc,
            synced_at,
            False  # Not deleted
        ))
        
        logger.info(f"✅ MERGE into UBER_EATS_REPORTS: workflow_id={event_id}")
        
        cursor.close()
        conn.close()
        
        if downloaded_at_utc:
            logger.info(f"✅ Stored report metadata and CSV data: workflow_id={event_id}, rows={csv_row_count}")
        else:
            logger.info(f"✅ Stored report metadata: workflow_id={event_id}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error storing webhook in Snowflake: {str(e)}", exc_info=True)
        return False


def store_report_data(conn, workflow_id: str, csv_rows: List[Dict[str, Any]]) -> bool:
    """
    Store CSV data in UBER_EATS_REPORT_DATA table (matching Fivetran schema).
    Uses incremental approach - deletes old data for this workflow_id before inserting.
    
    Args:
        conn: Snowflake connection
        workflow_id: Report workflow ID
        csv_rows: Parsed CSV rows
        
    Returns:
        True if successful, False otherwise
    """
    try:
        cursor = conn.cursor()
        synced_at = datetime.now(timezone.utc)
        
        # Tables are Fivetran-managed and already exist — skip CREATE TABLE

        # Incremental approach: Delete existing rows for this workflow_id first
        # This prevents duplicates if webhook is received multiple times
        delete_sql = f"""
        DELETE FROM {SNOWFLAKE_SCHEMA}.UBER_EATS_REPORT_DATA
        WHERE WORKFLOW_ID = %s
        """
        cursor.execute(delete_sql, (workflow_id,))
        deleted_count = cursor.rowcount
        
        if deleted_count > 0:
            logger.info(f"Deleted {deleted_count} existing rows for workflow_id={workflow_id} (deduplication)")
        
        # Insert new CSV rows
        # Store REPORT_DATA as VARCHAR JSON string — avoids PARSE_JSON apostrophe issues
        # The column is VARCHAR; query with PARSE_JSON(REPORT_DATA) when needed in Snowflake
        insert_sql = f"""
        INSERT INTO {SNOWFLAKE_SCHEMA}.UBER_EATS_REPORT_DATA (
            WORKFLOW_ID, REPORT_DATA, _FIVETRAN_SYNCED, _FIVETRAN_DELETED
        ) VALUES (%s, %s, %s, %s)
        """
        for row in csv_rows:
            cursor.execute(insert_sql, (
                workflow_id,
                json.dumps(row, ensure_ascii=False),
                synced_at,
                False
            ))
        
        cursor.close()
        logger.info(f"✅ Stored {len(csv_rows)} rows in UBER_EATS_REPORT_DATA for workflow_id={workflow_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error storing report data: {str(e)}", exc_info=True)
        return False


# ============================================================================
# OAuth 2.0 Authorization Code Flow for Uber Integration Activation
# USES NEW ORDERS APP CREDENTIALS (NOT the old webhook app)
# ============================================================================

def exchange_authorization_code_for_token(code: str) -> Dict[str, Any]:
    """
    Exchange Uber authorization code for access token.
    Uses NEW Orders app credentials (UBER_ORDERS_CLIENT_ID/SECRET).
    
    Args:
        code: Authorization code from Uber callback
        
    Returns:
        Token response from Uber (access_token, scope, expires_in, etc.)
        
    Raises:
        ValueError: If required environment variables are missing
        HTTPException: If token exchange fails
    """
    # Validate required OAuth environment variables for NEW Orders app
    required_oauth_vars = {
        "UBER_ORDERS_CLIENT_ID": UBER_ORDERS_CLIENT_ID,
        "UBER_ORDERS_CLIENT_SECRET": UBER_ORDERS_CLIENT_SECRET,
        "UBER_ORDERS_REDIRECT_URI": UBER_ORDERS_REDIRECT_URI,
    }
    
    missing = [k for k, v in required_oauth_vars.items() if not v]
    if missing:
        raise ValueError(f"Missing required OAuth environment variables: {', '.join(missing)}")
    
    # Prepare token exchange request using NEW Orders app credentials
    # Testing app => sandbox-login.uber.com + test-api.uber.com
    # Production app => auth.uber.com + api.uber.com
    token_url = "https://sandbox-login.uber.com/oauth/v2/token"
    payload = {
        "client_id": UBER_ORDERS_CLIENT_ID,  # NEW Orders app
        "client_secret": UBER_ORDERS_CLIENT_SECRET,  # NEW Orders app
        "grant_type": "authorization_code",
        "redirect_uri": UBER_ORDERS_REDIRECT_URI,
        "code": code,
    }
    
    try:
        logger.info("Exchanging authorization code for access token (Orders app)")
        response = requests.post(token_url, data=payload, timeout=30)
        
        # Parse response
        if response.status_code == 200:
            token_data = response.json()
            logger.info(f"✅ Token exchange successful (Orders app) - scope: {token_data.get('scope', 'N/A')}, expires_in: {token_data.get('expires_in', 'N/A')}s")
            return token_data
        else:
            # Token exchange failed
            error_body = response.text
            logger.error(f"Token exchange failed (Orders app) - status: {response.status_code}, body: {error_body}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "error": "token_exchange_failed",
                    "uber_status_code": response.status_code,
                    "uber_response": error_body
                }
            )
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error during token exchange: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "network_error",
                "message": f"Failed to connect to Uber token endpoint: {str(e)}"
            }
        )


@app.get("/uber/authorize")
async def uber_authorize():
    """
    OAuth 2.0 Authorization Endpoint - Step 1
    Redirects user to Uber's authorization page for integration activation.
    Uses NEW Orders app credentials (not the old webhook app).
    """
    # Validate required OAuth environment variables for NEW Orders app
    if not UBER_ORDERS_CLIENT_ID or not UBER_ORDERS_REDIRECT_URI:
        missing = []
        if not UBER_ORDERS_CLIENT_ID:
            missing.append("UBER_ORDERS_CLIENT_ID")
        if not UBER_ORDERS_REDIRECT_URI:
            missing.append("UBER_ORDERS_REDIRECT_URI")
        
        logger.error(f"OAuth configuration missing for Orders app: {', '.join(missing)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "oauth_configuration_missing",
                "missing_variables": missing,
                "note": "OAuth uses separate Orders app credentials, not the webhook app"
            }
        )
    
    # Build Uber authorization URL using NEW Orders app client ID
    # Testing app => sandbox-login.uber.com + test-api.uber.com
    # Production app => auth.uber.com + api.uber.com
    auth_url = "https://sandbox-login.uber.com/oauth/v2/authorize"
    params = {
        "client_id": UBER_ORDERS_CLIENT_ID,  # NEW Orders app
        "response_type": "code",
        "redirect_uri": UBER_ORDERS_REDIRECT_URI,
        "scope": "eats.pos_provisioning",
    }
    
    # Build query string
    query_string = "&".join([f"{k}={requests.utils.quote(v)}" for k, v in params.items()])
    authorization_url = f"{auth_url}?{query_string}"
    
    logger.info(f"Redirecting to Uber authorization (Orders app, scope: eats.pos_provisioning)")
    
    # Redirect user to Uber's authorization page
    return RedirectResponse(url=authorization_url)


@app.get("/uber/callback")
async def uber_callback(code: Optional[str] = Query(None)):
    """
    OAuth 2.0 Callback Endpoint - Step 2
    Receives authorization code from Uber and exchanges it for access token.
    Uses NEW Orders app credentials (not the old webhook app).
    """
    # Validate authorization code
    if not code:
        logger.warning("OAuth callback received without authorization code (Orders app)")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "missing_authorization_code",
                "message": "Authorization code is required"
            }
        )
    
    logger.info("OAuth callback received with authorization code (Orders app)")
    
    try:
        # Exchange code for token using NEW Orders app credentials
        token_data = exchange_authorization_code_for_token(code)
        
        # Return safe success response
        # TEMPORARY: Including access_token for sandbox testing/debugging
        # TODO: Remove access_token from response before production deployment
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "message": "Authorization successful (Orders app)",
                "access_token": token_data.get("access_token"),  # SANDBOX ONLY - Remove for production
                "scope": token_data.get("scope", "N/A"),
                "expires_in": token_data.get("expires_in", "N/A"),
            }
        )
    
    except ValueError as e:
        # Missing OAuth configuration
        logger.error(f"OAuth configuration error (Orders app): {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "oauth_configuration_error",
                "message": str(e)
            }
        )
    
    except HTTPException as e:
        # Token exchange failed (already logged in helper function)
        return JSONResponse(
            status_code=e.status_code,
            content=e.detail
        )
    
    except Exception as e:
        # Unexpected error
        logger.error(f"Unexpected error in OAuth callback (Orders app): {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "unexpected_error",
                "message": "An unexpected error occurred during authorization"
            }
        )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    # Test Snowflake connection
    try:
        conn = get_snowflake_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()
        return {"status": "ok", "snowflake": "connected"}
    except Exception as e:
        logger.error(f"Snowflake health check failed: {str(e)}")
        return {"status": "ok", "snowflake": "disconnected", "error": str(e)}


# Allow GET/HEAD so dashboard or Uber URL verification doesn't get 405 (some systems ping URL when you save it)
@app.get("/uber-webhook")
@app.head("/uber-webhook")
async def uber_webhook_allow_get():
    """Return 200 so URL verification (e.g. dashboard) succeeds. Real webhooks are POST only."""
    return PlainTextResponse(content="", status_code=status.HTTP_200_OK)


@app.post("/uber-webhook")
async def uber_webhook(
    request: Request,
    x_uber_signature: Optional[str] = Header(None, alias="X-Uber-Signature"),
    x_uber_trace_id: Optional[str] = Header(None, alias="X-Uber-Trace-ID"),
    x_api_environment: Optional[str] = Header(None, alias="X-API-Environment"),
    x_environment: Optional[str] = Header(None, alias="X-Environment"),
):
    """
    Receive webhook from Uber Eats, verify signature, and store directly in Snowflake.
    
    IMPORTANT: Must read raw body bytes (not parsed JSON) for signature verification.
    """
    logger.info("Received POST /uber-webhook (incoming webhook)")
    try:
        # Read raw body bytes (CRITICAL: do not parse JSON before verification)
        raw_body = await request.body()
        
        if not raw_body:
            logger.warning("Received empty request body")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty request body"
            )
        
        # Get signature from header
        if not x_uber_signature:
            logger.warning("Missing X-Uber-Signature header")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing signature"
            )
        
        # Verify signature
        signature_valid = verify_signature(
            raw_body,
            x_uber_signature,
            UBER_CLIENT_SECRET
        )
        
        if not signature_valid:
            logger.warning("Invalid signature")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature"
            )
        
        logger.info("✅ Signature validated, storing in Snowflake")
        
        # Parse payload (now safe to parse after verification)
        try:
            payload = json.loads(raw_body.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse webhook payload: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload"
            )
        
        # Store in Snowflake
        headers = {
            "X-Uber-Signature": x_uber_signature,
            "X-Uber-Trace-ID": x_uber_trace_id or "",
            "X-API-Environment": x_api_environment or "",
            "X-Environment": x_environment or "",
        }
        
        success = store_webhook_in_snowflake(payload, headers)
        
        if not success:
            # Return 502 so Uber will retry
            return PlainTextResponse(
                content="Failed to store webhook in Snowflake",
                status_code=status.HTTP_502_BAD_GATEWAY
            )
        
        logger.info("✅ Successfully stored webhook in Snowflake")
        # Uber docs: "HTTP 200 with an empty response body" to acknowledge receipt
        return PlainTextResponse(content="", status_code=status.HTTP_200_OK)
    
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        return PlainTextResponse(
            content="Internal server error",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)

