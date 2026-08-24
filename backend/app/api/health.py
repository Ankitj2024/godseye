"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Simple health check for verifying the backend is running."""
    return {"status": "ok", "service": "godseye-backend"}
