"""
Uber Eats Webhook Verifier
Receives webhooks from Uber Eats, verifies HMAC signature, and forwards to Fivetran.
"""

import os
import hmac
import hashlib
import logging
from typing import Optional
from fastapi import FastAPI, Request, Response, Header, HTTPException, status
from fastapi.responses import PlainTextResponse
import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Uber Eats Webhook Verifier")

# Environment variables
FIVETRAN_URL = os.getenv("FIVETRAN_URL")
UBER_CLIENT_SECRET = os.getenv("UBER_CLIENT_SECRET")
PORT = int(os.getenv("PORT", "8080"))

# Validate required environment variables
if not FIVETRAN_URL:
    raise ValueError("FIVETRAN_URL environment variable is required")
if not UBER_CLIENT_SECRET:
    raise ValueError("UBER_CLIENT_SECRET environment variable is required")

logger.info(f"Webhook verifier initialized")
logger.info(f"Fivetran URL: {FIVETRAN_URL}")


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


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}


@app.post("/uber-webhook")
async def uber_webhook(
    request: Request,
    x_uber_signature: Optional[str] = Header(None, alias="X-Uber-Signature"),
    x_uber_trace_id: Optional[str] = Header(None, alias="X-Uber-Trace-ID"),
    x_api_environment: Optional[str] = Header(None, alias="X-API-Environment"),
    x_environment: Optional[str] = Header(None, alias="X-Environment"),
):
    """
    Receive webhook from Uber Eats, verify signature, and forward to Fivetran.
    
    IMPORTANT: Must read raw body bytes (not parsed JSON) for signature verification.
    """
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
        
        logger.info("✅ Signature validated, forwarding to Fivetran")
        
        # Prepare headers for forwarding
        forward_headers = {
            "Content-Type": request.headers.get("Content-Type", "application/json"),
            "X-Uber-Signature": x_uber_signature,
        }
        
        # Add optional headers if present
        if x_uber_trace_id:
            forward_headers["X-Uber-Trace-ID"] = x_uber_trace_id
        if x_api_environment:
            forward_headers["X-API-Environment"] = x_api_environment
        if x_environment:
            forward_headers["X-Environment"] = x_environment
        
        # Forward to Fivetran
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    FIVETRAN_URL,
                    content=raw_body,  # Send raw bytes
                    headers=forward_headers
                )
                
                if not response.is_success:
                    error_text = response.text[:500]  # Limit error message length
                    logger.error(
                        f"Fivetran forwarding failed: {response.status_code} {error_text}"
                    )
                    # Return 502 so Uber will retry
                    return PlainTextResponse(
                        content=f"Forwarding failed: {response.status_code}",
                        status_code=status.HTTP_502_BAD_GATEWAY
                    )
                
                logger.info("✅ Successfully forwarded to Fivetran")
                return PlainTextResponse(content="OK", status_code=status.HTTP_200_OK)
                
            except httpx.TimeoutException:
                logger.error("Timeout forwarding to Fivetran")
                return PlainTextResponse(
                    content="Timeout forwarding to Fivetran",
                    status_code=status.HTTP_502_BAD_GATEWAY
                )
            except httpx.RequestError as e:
                logger.error(f"Error forwarding to Fivetran: {str(e)}")
                return PlainTextResponse(
                    content=f"Error forwarding to Fivetran: {str(e)}",
                    status_code=status.HTTP_502_BAD_GATEWAY
                )
    
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

