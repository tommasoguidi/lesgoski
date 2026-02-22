# webapp/app.py
import csv
import json
import logging
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from lesgoski.webapp.utils import get_country_code, get_booking_links
from lesgoski.webapp.auth import (
    RedirectToLogin, get_current_user, require_user, require_admin,
    verify_password, hash_password, generate_ntfy_topic, generate_invite_token,
    get_broskis, get_pending_broski_requests,
)
from lesgoski.services.airports import get_nearby_set
from fastapi import FastAPI, Depends, Request, Form, BackgroundTasks, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload
from starlette.middleware.sessions import SessionMiddleware
from lesgoski.database.engine import get_db, init_db, SessionLocal
from lesgoski.database.models import Deal, SearchProfile, User, BroskiRequest, InviteToken
from lesgoski.core.schemas import StrategyConfig
from lesgoski.services.orchestrator import update_single_profile
from lesgoski.config import SECRET_KEY, WEBAPP_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

_WEBAPP_DIR = Path(__file__).parent

# Ensure DB tables exist
init_db()
app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=30 * 24 * 3600,
    https_only=False,  # Nginx terminates TLS; cookie still secure via SameSite
    same_site="lax",
)
app.mount("/static", StaticFiles(directory=str(_WEBAPP_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(_WEBAPP_DIR / "templates"))
# Use CDN in dev (no built tailwind.css), pre-built CSS in production (Docker)
_tailwind_css = _WEBAPP_DIR / "static" / "tailwind.css"
templates.env.globals.update(
    booking_links=get_booking_links,
    tailwind_dev=not _tailwind_css.exists(),
)

# Deterministic avatar colour for broski initials
_BROSKI_COLOURS = [
    "#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b",
    "#10b981", "#ef4444", "#06b6d4", "#84cc16",
]

def _broski_color(username: str) -> str:
    return _BROSKI_COLOURS[hash(username) % len(_BROSKI_COLOURS)]

templates.env.filters["broski_color"] = _broski_color


@app.exception_handler(RedirectToLogin)
async def handle_redirect_to_login(request: Request, exc: RedirectToLogin):
    return RedirectResponse("/login", status_code=303)


@lru_cache(maxsize=1)
def _load_airports() -> list[dict]:
    """Load airport data from CSV, keeping only essential fields."""
    csv_path = _WEBAPP_DIR / "data" / "filtered_airports.csv"
    airports = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            iata = row.get("iata_code", "").strip()
            if not iata:
                continue
            airports.append({
                "iata": iata,
                "name": row.get("name", "").strip(),
                "city": row.get("municipality", "").strip(),
                "country": row.get("iso_country", "").strip(),
            })
    return airports

def run_background_update(profile_id: int):
    db = SessionLocal()
    try:
        update_single_profile(db, profile_id)
    except Exception as e:
        logger.error(f"Background update failed: {e}", exc_info=True)
    finally:
        db.close()


def _user_can_access(profile: SearchProfile, user: User) -> bool:
    """Check if user owns the profile or is a viewer."""
    if profile.user_id == user.id:
        return True
    return user in profile.viewers


# --- AUTH ROUTES ---

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user: User = Depends(get_current_user)):
    if user:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
def login(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse("login.html", {
            "request": request, "error": "Invalid username or password",
        })
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request, user: User = Depends(get_current_user), invite: str = None):
    if user:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("signup.html", {"request": request, "invite": invite})


@app.post("/signup")
def signup(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    invite_code: str = Form(...),
):
    from datetime import datetime, timezone, timedelta
    ctx = {"request": request}

    # Validate invite token against the database (single-use, 7-day lifetime)
    token_obj = (
        db.query(InviteToken)
        .filter(
            InviteToken.token == invite_code,
            InviteToken.used_by == None,
            InviteToken.revoked == False,
            InviteToken.created_at >= datetime.now(timezone.utc) - timedelta(days=7),
        )
        .first()
    )
    if not token_obj:
        ctx["error"] = "Invalid or already used invite code"
        return templates.TemplateResponse("signup.html", ctx)
    if password != confirm_password:
        ctx["error"] = "Passwords do not match"
        return templates.TemplateResponse("signup.html", ctx)
    if len(password) < 8:
        ctx["error"] = "Password must be at least 8 characters"
        return templates.TemplateResponse("signup.html", ctx)
    if len(username) < 3:
        ctx["error"] = "Username must be at least 3 characters"
        return templates.TemplateResponse("signup.html", ctx)
    if db.query(User).filter(User.username == username).first():
        ctx["error"] = "Username already taken"
        return templates.TemplateResponse("signup.html", ctx)

    user = User(
        username=username,
        hashed_password=hash_password(password),
        ntfy_topic=generate_ntfy_topic(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Consume the token
    token_obj.used_by = user.id
    token_obj.used_at = datetime.now(timezone.utc)
    db.commit()

    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# --- SETTINGS ROUTES ---

@app.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    success: str = None,
    error: str = None,
):
    # Admin-only: load invite tokens (active + used within last 7 days)
    invite_tokens = []
    if user.is_admin:
        from datetime import datetime, timezone, timedelta
        from sqlalchemy import or_
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        invite_tokens = (
            db.query(InviteToken)
            .filter(
                InviteToken.created_by == user.id,
                InviteToken.revoked == False,
                or_(InviteToken.used_by == None, InviteToken.used_at >= cutoff),
            )
            .order_by(InviteToken.used_at.asc().nullsfirst(), InviteToken.created_at.asc())
            .all()
        )

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "user": user,
        "success": success,
        "error": error,
        "invite_tokens": invite_tokens,
        "webapp_url": WEBAPP_URL,
    })


@app.get("/goskis", response_class=HTMLResponse)
def goskis_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    success: str = None,
    error: str = None,
):
    own_profiles = (
        db.query(SearchProfile)
        .filter(SearchProfile.user_id == user.id)
        .all()
    )
    shared_profiles = (
        db.query(SearchProfile)
        .filter(
            SearchProfile.is_active == True,
            SearchProfile.viewers.any(User.id == user.id),
        )
        .all()
    )
    broskis = get_broskis(db, user)
    pending_requests = get_pending_broski_requests(db, user)

    return templates.TemplateResponse("goskis.html", {
        "request": request,
        "user": user,
        "success": success,
        "error": error,
        "own_profiles": own_profiles,
        "shared_profiles": shared_profiles,
        "broskis": broskis,
        "pending_requests": pending_requests,
    })


@app.get("/alerts", response_class=HTMLResponse)
def alerts_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    # All accessible profiles (own + shared)
    all_profiles = (
        db.query(SearchProfile)
        .filter(
            SearchProfile.is_active == True,
            (SearchProfile.user_id == user.id) | SearchProfile.viewers.any(User.id == user.id),
        )
        .all()
    )

    alert_items = []
    for profile in all_profiles:
        notify_dests = profile.notify_destinations
        if not notify_dests:
            continue

        # Fetch deals for this profile
        deals = db.query(Deal).options(
            joinedload(Deal.outbound),
            joinedload(Deal.inbound),
            joinedload(Deal.profile),
        ).filter(Deal.profile_id == profile.id).all()
        deals = [d for d in deals if d.outbound and d.inbound]

        # Group deals by destination (metro-area aware) + build name lookup
        grouped = defaultdict(list)
        dest_full_names: dict[str, str] = {}
        for deal in deals:
            out_dest = deal.outbound.destination
            in_origin = deal.inbound.origin if deal.inbound else out_dest
            area_codes = get_nearby_set(out_dest) | get_nearby_set(in_origin)
            for code in area_codes:
                grouped[code].append(deal)
            # Map each IATA code to its full name from flight data
            for code, full_name in [
                (out_dest, deal.outbound.destination_full or out_dest),
                (in_origin, (deal.inbound.origin_full if deal.inbound else None) or in_origin),
            ]:
                if code not in dest_full_names:
                    dest_full_names[code] = full_name

        for dest_code in notify_dests:
            dest_deals = grouped.get(dest_code, [])
            if not dest_deals:
                continue
            # Deduplicate
            seen = set()
            unique = []
            for d in dest_deals:
                if d.id not in seen:
                    seen.add(d.id)
                    unique.append(d)
            unique.sort(key=lambda x: x.total_price_pp)
            best = unique[0]

            full_name = dest_full_names.get(dest_code, best.outbound.destination_full or dest_code)
            country_code = get_country_code(full_name)

            alert_items.append({
                "destination_code": dest_code,
                "destination_name": full_name.split(',')[0].strip(),
                "country_code": country_code,
                "country_flag": f"https://flagsapi.com/{country_code.upper()}/shiny/64.png",
                "best_deal": best,
                "profile": profile,
                "is_shared": profile.user_id != user.id,
                "other_count": len(unique) - 1,
            })

    alert_items.sort(key=lambda x: x["best_deal"].total_price_pp)

    return templates.TemplateResponse("alerts.html", {
        "request": request,
        "user": user,
        "alert_items": alert_items,
    })


@app.post("/settings/save")
def save_settings(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    excluded_destinations: str = Form(""),
):
    dest_list = [d.strip().upper() for d in excluded_destinations.split(',') if d.strip()]
    user.excluded_destinations = dest_list
    db.commit()
    return RedirectResponse("/settings?success=Settings+saved", status_code=303)


@app.post("/settings/password")
def change_password(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    if not verify_password(current_password, user.hashed_password):
        return RedirectResponse("/settings?error=Current+password+is+incorrect", status_code=303)
    if new_password != confirm_password:
        return RedirectResponse("/settings?error=New+passwords+do+not+match", status_code=303)
    if len(new_password) < 8:
        return RedirectResponse("/settings?error=Password+must+be+at+least+8+characters", status_code=303)
    user.hashed_password = hash_password(new_password)
    db.commit()
    return RedirectResponse("/settings?success=Password+changed", status_code=303)


# --- ADMIN ROUTES ---

@app.post("/admin/tokens/generate")
def generate_token(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Generate a new single-use invite token."""
    for _ in range(5):
        candidate = generate_invite_token()
        if not db.query(InviteToken).filter(InviteToken.token == candidate).first():
            break
    db.add(InviteToken(token=candidate, created_by=user.id))
    db.commit()
    return RedirectResponse("/settings", status_code=303)


@app.post("/admin/tokens/{token_id}/revoke")
def revoke_token(
    token_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Soft-revoke an unused invite token."""
    token = db.get(InviteToken, token_id)
    if not token or token.used_by is not None:
        return RedirectResponse("/settings", status_code=303)
    token.revoked = True
    db.commit()
    return RedirectResponse("/settings", status_code=303)


# --- API ROUTES ---

@app.get("/api/username-available")
def username_available(username: str = "", db: Session = Depends(get_db)):
    """Returns {"available": bool}. Used by the signup form for live feedback."""
    if len(username) < 3:
        return {"available": None}
    taken = db.query(User).filter(User.username == username).first()
    return {"available": taken is None}


# --- DEAL ROUTES ---

@app.get("/", response_class=HTMLResponse)
def view_deals(
    request: Request,
    profile_id: int = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    all_profiles = (
        db.query(SearchProfile)
        .filter(
            SearchProfile.is_active == True,
            (SearchProfile.user_id == user.id) | SearchProfile.viewers.any(User.id == user.id),
        )
        .all()
    )

    # Logic: No profiles -> Go to create
    if not all_profiles:
        return RedirectResponse("/profile/new", status_code=303)

    # Logic: No specific profile requested -> Use favourite, then first own, then first any
    current_profile = None
    if profile_id:
        current_profile = db.get(SearchProfile, profile_id)
        if current_profile and not _user_can_access(current_profile, user):
            current_profile = None

    if not current_profile:
        # Pick best default: favourite > first own > first accessible
        default_id = None
        if user.favourite_profile_id:
            fav = db.get(SearchProfile, user.favourite_profile_id)
            if fav and fav.is_active and _user_can_access(fav, user):
                default_id = fav.id
        if not default_id:
            own = [p for p in all_profiles if p.user_id == user.id]
            default_id = own[0].id if own else all_profiles[0].id
        return RedirectResponse(f"/?profile_id={default_id}", status_code=303)

    # Fetch deals for this profile
    deals = db.query(Deal).options(
        joinedload(Deal.outbound),
        joinedload(Deal.inbound),
        joinedload(Deal.profile)
    ).filter(Deal.profile_id == current_profile.id).all()

    # Discard deals whose flights were pruned (orphaned FK safety net)
    deals = [d for d in deals if d.outbound and d.inbound]

    # Grouping Data — metro-area aware
    grouped = defaultdict(list)
    unique_countries = set()
    unique_destinations = set()
    dest_full_names: dict[str, str] = {}

    for deal in deals:
        if not deal.outbound:
            continue

        out_dest = deal.outbound.destination
        in_origin = deal.inbound.origin if deal.inbound else out_dest

        area_codes = get_nearby_set(out_dest) | get_nearby_set(in_origin)

        for code in area_codes:
            grouped[code].append(deal)

        for code, full_name in [
            (out_dest, deal.outbound.destination_full or out_dest),
            (in_origin, (deal.inbound.origin_full if deal.inbound else None) or in_origin),
        ]:
            if code not in dest_full_names:
                dest_full_names[code] = full_name
            country_code = get_country_code(full_name)
            unique_countries.add(country_code)
            unique_destinations.add(code)

    direct_codes = set()
    for deal in deals:
        if deal.outbound:
            direct_codes.add(deal.outbound.destination)
        if deal.inbound:
            direct_codes.add(deal.inbound.origin)

    view_data = []
    for dest_code, deal_list in grouped.items():
        if not deal_list:
            continue
        if dest_code not in direct_codes:
            continue

        seen_ids = set()
        unique_deals = []
        for d in deal_list:
            if d.id not in seen_ids:
                seen_ids.add(d.id)
                unique_deals.append(d)
        unique_deals.sort(key=lambda x: x.total_price_pp)

        first = unique_deals[0]
        full_name = dest_full_names.get(dest_code, dest_code)
        country_code = get_country_code(full_name)

        view_data.append({
            "destination_code": dest_code,
            "destination_name": full_name.split(',')[0].strip(),
            "country_code": country_code,
            "country_flag": f"https://flagsapi.com/{country_code.upper()}/shiny/64.png",
            "best_deal": first,
            "other_deals": unique_deals[1:]
        })

    view_data.sort(key=lambda x: x["best_deal"].total_price_pp)

    is_owner = current_profile.user_id == user.id

    return templates.TemplateResponse("deals.html", {
        "request": request,
        "user": user,
        "destinations": view_data,
        "current_profile": current_profile,
        "all_profiles": all_profiles,
        "filter_countries": sorted(list(unique_countries)),
        "filter_destinations": sorted(list(unique_destinations)),
        "notify_destinations": current_profile.notify_destinations if current_profile else [],
        "is_owner": is_owner,
    })


# --- DEAL DETAIL ROUTE ---

@app.get("/deal/{destination_code}", response_class=HTMLResponse)
def deal_detail(
    request: Request,
    destination_code: str,
    profile_id: int = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    # Resolve profile
    current_profile = None
    if profile_id:
        current_profile = db.get(SearchProfile, profile_id)
        if current_profile and not _user_can_access(current_profile, user):
            current_profile = None
    if not current_profile and user.favourite_profile_id:
        fav = db.get(SearchProfile, user.favourite_profile_id)
        if fav and fav.is_active and _user_can_access(fav, user):
            current_profile = fav
    if not current_profile:
        all_p = (
            db.query(SearchProfile)
            .filter(
                SearchProfile.is_active == True,
                (SearchProfile.user_id == user.id) | SearchProfile.viewers.any(User.id == user.id),
            )
            .first()
        )
        current_profile = all_p
    if not current_profile:
        return RedirectResponse("/profile/new", status_code=303)

    deals = (
        db.query(Deal)
        .options(joinedload(Deal.outbound), joinedload(Deal.inbound), joinedload(Deal.profile))
        .filter(Deal.profile_id == current_profile.id)
        .all()
    )
    deals = [d for d in deals if d.outbound and d.inbound]

    # Filter to destination, group by metro area
    from lesgoski.services.airports import get_nearby_set
    matching = []
    for d in deals:
        area = get_nearby_set(d.outbound.destination) | get_nearby_set(d.inbound.origin)
        if destination_code in area:
            matching.append(d)
    matching.sort(key=lambda x: x.total_price_pp)

    if not matching:
        return RedirectResponse(f"/?profile_id={current_profile.id}", status_code=303)

    best_deal = matching[0]
    other_deals = matching[1:]

    full_name = best_deal.outbound.destination_full or destination_code
    destination_name = full_name.split(',')[0].strip()
    country_code = get_country_code(full_name)
    country_flag = f"https://flagsapi.com/{country_code.upper()}/shiny/64.png"
    is_over = best_deal.total_price_pp > best_deal.profile.max_price

    return templates.TemplateResponse("deal_detail.html", {
        "request": request,
        "user": user,
        "destination_code": destination_code,
        "destination_name": destination_name,
        "country_code": country_code,
        "country_flag": country_flag,
        "best_deal": best_deal,
        "other_deals": other_deals,
        "current_profile": current_profile,
        "notify_destinations": current_profile.notify_destinations if current_profile else [],
        "is_over": is_over,
    })


# --- PROFILE ROUTES ---

@app.get("/profile/new", response_class=HTMLResponse)
def new_profile_form(request: Request, user: User = Depends(require_user)):
    return templates.TemplateResponse("profile_form.html", {
        "request": request, "user": user, "profile": None, "is_new": True,
    })


@app.get("/profile/{pid}", response_class=HTMLResponse)
def edit_profile_form(
    request: Request,
    pid: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    profile = db.get(SearchProfile, pid)
    if not profile or profile.user_id != user.id:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("profile_form.html", {
        "request": request, "user": user, "profile": profile, "is_new": False,
    })


@app.post("/profile/save")
async def save_profile(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    profile_id: int = Form(None),
    name: str = Form(...),
    origins: str = Form(...),
    allowed_destinations: str = Form(""),
    max_price: float = Form(...),
    adults: int = Form(...),
    strategy_json: str = Form(...)
):
    # Parse & Validate
    origin_list = [o.strip().upper() for o in origins.split(',') if o.strip()]
    if not origin_list:
        return HTMLResponse("At least one origin airport is required.", status_code=400)
    dest_list = [d.strip().upper() for d in allowed_destinations.split(',') if d.strip()]
    try:
        strategy_dict = json.loads(strategy_json)
        StrategyConfig(**strategy_dict)
    except Exception as e:
        return HTMLResponse(f"Invalid Strategy JSON: {e}", status_code=400)

    if profile_id:
        profile = db.get(SearchProfile, profile_id)
        if not profile or profile.user_id != user.id:
            raise HTTPException(status_code=403)
    else:
        profile = SearchProfile(user_id=user.id)
        db.add(profile)

    profile.name = name
    profile.origins = origin_list
    profile.allowed_destinations = dest_list
    profile.max_price = max_price
    profile.adults = adults
    profile._strategy_object = strategy_json

    db.commit()
    db.refresh(profile)

    # TRIGGER IMMEDIATE UPDATE
    background_tasks.add_task(run_background_update, profile.id)

    return RedirectResponse(f"/?profile_id={profile.id}", status_code=303)


@app.post("/update/{profile_id}")
def trigger_manual_update(
    profile_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    profile = db.get(SearchProfile, profile_id)
    if not profile or not _user_can_access(profile, user):
        raise HTTPException(status_code=404)
    try:
        run_background_update(profile_id)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Manual update failed: {e}", exc_info=True)
        return HTMLResponse(content=f"Update failed: {e}", status_code=500)


@app.post("/profile/{pid}/delete")
def delete_profile(
    pid: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    profile = db.get(SearchProfile, pid)
    if profile and profile.user_id == user.id:
        profile.is_active = False
        db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/profile/{pid}/toggle")
def toggle_profile(
    pid: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    profile = db.get(SearchProfile, pid)
    if not profile or profile.user_id != user.id:
        raise HTTPException(status_code=404)
    profile.is_active = not profile.is_active
    db.commit()
    return RedirectResponse("/goskis", status_code=303)


# --- SHARING ROUTES ---

@app.post("/profile/{pid}/share")
def share_profile(
    pid: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    share_user_id: int = Form(...),
):
    profile = db.get(SearchProfile, pid)
    if not profile or profile.user_id != user.id:
        return RedirectResponse("/goskis?error=Profile+not+found", status_code=303)
    target = db.get(User, share_user_id)
    if not target or target.id == user.id:
        return RedirectResponse("/goskis?error=Invalid+user", status_code=303)
    # Verify they are broskis
    broskis = get_broskis(db, user)
    if target not in broskis:
        return RedirectResponse("/goskis?error=You+can+only+share+with+broskis", status_code=303)
    if target not in profile.viewers:
        profile.viewers.append(target)
        db.commit()
    return RedirectResponse("/goskis?success=Profile+shared", status_code=303)


@app.post("/profile/{pid}/unshare")
def unshare_profile(
    pid: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    unshare_user_id: int = Form(...),
):
    profile = db.get(SearchProfile, pid)
    if not profile or profile.user_id != user.id:
        raise HTTPException(status_code=404)
    target = db.get(User, unshare_user_id)
    if target and target in profile.viewers:
        profile.viewers.remove(target)
        db.commit()
    return RedirectResponse("/goskis?success=Viewer+removed", status_code=303)


# --- BROSKI ROUTES ---

@app.post("/broski/request")
def send_broski_request(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    broski_username: str = Form(...),
):
    target = db.query(User).filter(User.username == broski_username).first()
    if not target or target.id == user.id:
        return RedirectResponse("/goskis?error=User+not+found", status_code=303)

    # Check if already broskis or pending
    from sqlalchemy import or_, and_
    existing = db.query(BroskiRequest).filter(
        or_(
            and_(BroskiRequest.from_user_id == user.id, BroskiRequest.to_user_id == target.id),
            and_(BroskiRequest.from_user_id == target.id, BroskiRequest.to_user_id == user.id),
        )
    ).first()
    if existing:
        msg = "Already+broskis" if existing.status == "accepted" else "Request+already+pending"
        return RedirectResponse(f"/goskis?error={msg}", status_code=303)

    req = BroskiRequest(from_user_id=user.id, to_user_id=target.id)
    db.add(req)
    db.commit()
    return RedirectResponse("/goskis?success=Broski+request+sent", status_code=303)


@app.post("/broski/accept/{request_id}")
def accept_broski_request(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    req = db.get(BroskiRequest, request_id)
    if not req or req.to_user_id != user.id or req.status != "pending":
        raise HTTPException(status_code=404)
    req.status = "accepted"
    db.commit()
    return RedirectResponse("/goskis?success=Broski+accepted", status_code=303)


@app.post("/broski/decline/{request_id}")
def decline_broski_request(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    req = db.get(BroskiRequest, request_id)
    if not req or req.to_user_id != user.id or req.status != "pending":
        raise HTTPException(status_code=404)
    db.delete(req)
    db.commit()
    return RedirectResponse("/goskis?success=Request+declined", status_code=303)


@app.post("/broski/remove/{broski_id}")
def remove_broski(
    broski_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    from sqlalchemy import or_, and_
    req = db.query(BroskiRequest).filter(
        BroskiRequest.status == "accepted",
        or_(
            and_(BroskiRequest.from_user_id == user.id, BroskiRequest.to_user_id == broski_id),
            and_(BroskiRequest.from_user_id == broski_id, BroskiRequest.to_user_id == user.id),
        )
    ).first()
    if not req:
        raise HTTPException(status_code=404)

    # Auto-unshare: remove this broski from all profiles owned by either user
    target = db.get(User, broski_id)
    if target:
        my_profiles = db.query(SearchProfile).filter(SearchProfile.user_id == user.id).all()
        for p in my_profiles:
            if target in p.viewers:
                p.viewers.remove(target)
        their_profiles = db.query(SearchProfile).filter(SearchProfile.user_id == broski_id).all()
        for p in their_profiles:
            if user in p.viewers:
                p.viewers.remove(user)

    db.delete(req)
    db.commit()
    return RedirectResponse("/goskis?success=Broski+removed", status_code=303)


# --- FAVOURITE ROUTE ---

@app.post("/settings/favourite")
def set_favourite_profile(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    profile_id: int = Form(...),
):
    profile = db.get(SearchProfile, profile_id)
    if not profile or not _user_can_access(profile, user):
        raise HTTPException(status_code=404)
    # Toggle: if already favourite, clear it; otherwise set it
    if user.favourite_profile_id == profile_id:
        user.favourite_profile_id = None
    else:
        user.favourite_profile_id = profile_id
    db.commit()
    return RedirectResponse("/goskis?success=Default+profile+updated", status_code=303)


# --- API ROUTES ---

@app.get("/api/airports")
def get_airports():
    return _load_airports()


@app.get("/api/users/search")
def search_users(
    q: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Autocomplete endpoint for broski request username input.

    Returns users whose username contains `q` (case-insensitive),
    excluding: the current user, existing broskis, and users with
    a pending request in either direction.
    """
    query = q.strip().lower()
    if len(query) < 2:
        return []

    # IDs to exclude: self + anyone with an existing broski request (any status)
    from sqlalchemy import or_, and_
    existing_reqs = db.query(BroskiRequest).filter(
        or_(
            BroskiRequest.from_user_id == user.id,
            BroskiRequest.to_user_id == user.id,
        )
    ).all()
    exclude_ids = {user.id}
    for req in existing_reqs:
        exclude_ids.add(req.from_user_id)
        exclude_ids.add(req.to_user_id)

    matches = (
        db.query(User)
        .filter(
            User.username.ilike(f"%{query}%"),
            ~User.id.in_(exclude_ids),
        )
        .limit(8)
        .all()
    )
    return [{"id": u.id, "username": u.username} for u in matches]


@app.post("/api/notify-toggle")
async def toggle_notify_destination(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Toggle immediate notifications for a specific destination."""
    body = await request.json()
    profile_id = body.get("profile_id")
    destination = body.get("destination")

    if not profile_id or not destination:
        return {"error": "profile_id and destination required"}

    profile = db.get(SearchProfile, int(profile_id))
    if not profile or not _user_can_access(profile, user):
        return {"error": "Profile not found"}

    current = profile.notify_destinations
    if destination in current:
        current.remove(destination)
        enabled = False
    else:
        current.append(destination)
        enabled = True

    profile.notify_destinations = current
    db.commit()

    return {"destination": destination, "enabled": enabled}


def main():
    """Entry point for the web application."""
    import os
    import uvicorn
    uvicorn.run(
        "lesgoski.webapp.app:app",
        host=os.getenv("UVICORN_HOST", "127.0.0.1"),
        port=int(os.getenv("UVICORN_PORT", "8000")),
        reload=os.getenv("UVICORN_RELOAD", "true").lower() == "true",
    )


if __name__ == "__main__":
    main()
