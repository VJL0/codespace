from fastapi import APIRouter


router = APIRouter()


@router.get("/login")
async def google_login(): ...


@router.get("/callback")
async def google_callback(): ...
