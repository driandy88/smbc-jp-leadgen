from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import check_login, current_user, initials, issue_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Login(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(body: Login):
    if not check_login(body.email, body.password):
        raise HTTPException(401, "Wrong email or password")
    return {"token": issue_token(body.email.strip().lower()), "email": body.email, "initials": initials(body.email)}


@router.get("/me")
def me(user: str = Depends(current_user)):
    return {"email": user, "initials": initials(user)}
