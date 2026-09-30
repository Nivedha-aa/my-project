import os
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    File,
    UploadFile,
    Form,
    Request,
    status,
)
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import JWTError, jwt

from gemini_utils import (
    get_home_recommendations,
    get_party_recommendations,
    get_jewelry_recommendations,
)

app = FastAPI(title="PocketSmart: AI Budget Planner")

# Security Configurations
SECRET_KEY = os.getenv("SECRET_KEY", "pocketsmart_super_secret_jwt_key_2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# Setup Storage & Directories
os.makedirs("static/uploads", exist_ok=True)
templates = Jinja2Templates(directory="static/templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-Memory Database and Session Storage
users_db: Dict[str, dict] = {}
active_sessions: Dict[str, Any] = {}
blacklisted_tokens = set()
user_recommendations: Dict[str, List[dict]] = {}


# Data Models
class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class UserInDB(BaseModel):
    username: str
    email: str


class HomeBudgetInput(BaseModel):
    total_budget: float
    num_lights: int = 0
    num_fans: int = 0
    num_furniture: int = 0
    num_dining_tables: int = 0
    has_living_room: bool = False
    has_kitchen: bool = False
    has_bedroom: bool = False
    additional_requirements: Optional[str] = None


class PartyBudgetInput(BaseModel):
    total_budget: float
    party_type: str
    num_guests: int
    venue_type: Optional[str] = "Home"
    needs_catering: bool = False
    needs_decoration: bool = False
    needs_entertainment: bool = False
    additional_requirements: Optional[str] = None


# Helper Auth Functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_token_from_request(request: Request) -> Optional[str]:
    # Check Cookie first, then Auth Header
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            token = auth.split(" ")[1]
    return token


async def get_current_user_optional(
    request: Request,
) -> Optional[UserInDB]:
    token = await get_token_from_request(request)
    if not token or token in blacklisted_tokens:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None or username not in users_db:
            return None
        u = users_db[username]
        return UserInDB(username=u["username"], email=u["email"])
    except JWTError:
        return None


async def get_current_user_required(
    request: Request,
) -> UserInDB:
    user = await get_current_user_optional(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def save_to_history(
    username: str, rec_type: str, input_summary: dict, result: dict
):
    if username not in user_recommendations:
        user_recommendations[username] = []

    rec_id = str(uuid.uuid4())
    record = {
        "id": rec_id,
        "timestamp": datetime.now().strftime("%b %d, %Y, %I:%M %p"),
        "recommendation_type": rec_type,
        "input_summary": input_summary,
        "result_summary": {
            "total_budget": result.get("total_budget", 0),
            "remaining_budget": result.get("remaining_budget", 0),
        },
        "full_result": result,
    }
    user_recommendations[username].append(record)


# Background Session Cleanup
@app.on_event("startup")
async def startup_event():
    async def cleanup_expired_sessions():
        while True:
            now = datetime.utcnow()
            expired = [
                uname
                for uname, sess in active_sessions.items()
                if (now - sess["last_activity"]).total_seconds() > 1800
            ]
            for uname in expired:
                del active_sessions[uname]
            await asyncio.sleep(300)

    asyncio.create_task(cleanup_expired_sessions())


# Authentication Routes
@app.post("/register")
async def register(user: UserRegister):
    if user.username in users_db:
        raise HTTPException(
            status_code=400, detail="Username already registered"
        )
    users_db[user.username] = {
        "username": user.username,
        "email": user.email,
        "password": get_password_hash(user.password),
    }
    return {"message": "User registered successfully"}


@app.post("/token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    user = users_db.get(form_data.username)
    if not user or not verify_password(form_data.password, user["password"]):
        raise HTTPException(
            status_code=401, detail="Incorrect username or password"
        )

    access_token = create_access_token(data={"sub": user["username"]})
    active_sessions[user["username"]] = {
        "login_time": datetime.utcnow(),
        "last_activity": datetime.utcnow(),
        "token": access_token,
        "user_data": {},
    }

    response = JSONResponse(
        content={"access_token": access_token, "token_type": "bearer"}
    )
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
    )
    return response


@app.post("/logout")
async def logout(request: Request):
    token = await get_token_from_request(request)
    if token:
        blacklisted_tokens.add(token)
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
            if username in active_sessions:
                del active_sessions[username]
        except JWTError:
            pass
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token")
    return response


# UI Page Web Routes
@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    user = await get_current_user_optional(request)
    return templates.TemplateResponse(
        request, "index.html", {"request": request, "user": user}
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = await get_current_user_optional(request)
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request, "login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    user = await get_current_user_optional(request)
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request, "register.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    user = await get_current_user_optional(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    recent = user_recommendations.get(user.username, [])[-3:]
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"request": request, "user": user, "recent_activity": recent},
    )


@app.get("/home-planner", response_class=HTMLResponse)
async def home_planner_page(request: Request):
    user = await get_current_user_optional(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request, "home_planner.html", {"request": request, "user": user}
    )


@app.get("/party-planner", response_class=HTMLResponse)
async def party_planner_page(request: Request):
    user = await get_current_user_optional(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request, "party_planner.html", {"request": request, "user": user}
    )


@app.get("/jewelry-planner", response_class=HTMLResponse)
async def jewelry_planner_page(request: Request):
    user = await get_current_user_optional(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request, "jewelry_planner.html", {"request": request, "user": user}
    )


@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    user = await get_current_user_optional(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    history = user_recommendations.get(user.username, [])[::-1]
    return templates.TemplateResponse(
        request,
        "history.html",
        {"request": request, "user": user, "history": history},
    )


# Recommendation API Endpoints
@app.post("/home-budget")
async def plan_home_budget(
    input_data: HomeBudgetInput,
    request: Request,
    current_user: UserInDB = Depends(get_current_user_required),
):
    result = get_home_recommendations(input_data.dict())
    save_to_history(
        current_user.username, "Home Interior", input_data.dict(), result
    )
    return result


@app.post("/party-budget")
async def plan_party_budget(
    input_data: PartyBudgetInput,
    request: Request,
    current_user: UserInDB = Depends(get_current_user_required),
):
    result = get_party_recommendations(input_data.dict())
    save_to_history(
        current_user.username, "Party Planning", input_data.dict(), result
    )
    return result


@app.post("/jewelry-budget")
async def plan_jewelry_budget(
    total_budget: float = Form(...),
    occasion: str = Form(...),
    preferences: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    request: Request = None,
    current_user: UserInDB = Depends(get_current_user_required),
):
    image_path = None
    filename = None
    if image and image.filename:
        filename = f"{uuid.uuid4()}_{image.filename}"
        image_path = os.path.join("static/uploads", filename)
        with open(image_path, "wb") as f:
            content = await image.read()
            f.write(content)

    input_summary = {
        "total_budget": total_budget,
        "occasion": occasion,
        "preferences": preferences,
        "image_file": filename,
    }

    result = get_jewelry_recommendations(input_summary, image_path)
    save_to_history(
        current_user.username, "Jewelry", input_summary, result
    )
    return result


@app.get("/recommendation-details/{rec_id}")
async def get_rec_details(
    rec_id: str,
    current_user: UserInDB = Depends(get_current_user_required),
):
    user_recs = user_recommendations.get(current_user.username, [])
    for rec in user_recs:
        if rec["id"] == rec_id:
            return rec
    raise HTTPException(status_code=404, detail="Recommendation not found")


if __name__ == "__main__":
    import uvicorn

    print("Starting PocketSmart: AI Budget Planner...")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)