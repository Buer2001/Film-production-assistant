from fastapi import APIRouter
import os

router = APIRouter()


@router.get('/api/health')
def health():
    return {'status': 'ok', 'agent_configured': bool(os.getenv('LLM_API_KEY') and os.getenv('LLM_MODEL'))}


