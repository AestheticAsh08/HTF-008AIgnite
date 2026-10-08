"""FoodBridge - surplus food donation platform (hackday demo).
Flask + SQLite + Leaflet/OpenStreetMap. Donors and receivers are REAL (register yourself);
only the volunteers are seeded demo data.

One donation can now be split across several receivers. The split is planned by an
optimisation model (OR-Tools CP-SAT) in splitter.py, and veg / non-veg food is only
offered to receivers who accept it.
"""
import math
import os
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from splitter import Candidate, plan_split

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-for-real-use")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "foodbridge.db")

# ---------------------------------------------------------------- "AI" layer
# Food-safety shelf life (hours at room temp after cooking). Swap this for a
# trained model / vision model later; the rest of the app does not change.
SHELF_LIFE_HOURS = {
    "Cooked rice / biryani": 4,
    "Curry / gravy dishes": 4,
    "Bread / bakery": 8,
    "Dry snacks": 24,
    "Sweets": 12,
    "Fruits": 12,
    "Salads / raw items": 3,
    "Dairy based": 3,
}

MAX_KM = 25          # receivers further than this never get an offer
CITY_KMPH = 25       # rough city driving speed for the "will it arrive in time" check
HANDLING_MIN = 20    # loading, parking, handing over

DIETS = {"veg": "Veg", "nonveg": "Non-veg"}
RECEIVER_DIETS = {"veg": "Veg only", "both": "Veg and non-veg"}


def estimate_safe_until(category, cooked_at):
    return cooked_at + timedelta(hours=SHELF_LIFE_HOURS.get(category, 3))


def diet_ok(food_diet, receiver_diet):
    """Veg food can go anywhere. Non-veg only to receivers who accept non-veg."""
    return food_diet == "veg" or receiver_diet == "both"


def match_score(distance_km, portions, minutes_left, capacity):
    """Higher is better. Prefers close, enough time, and capacity fit."""
    if minutes_left <= 0:
        return -1
    time_factor = min(minutes_left / 120.0, 1.0)
    dist_factor = 1.0 / (1.0 + distance_km)
    fit = 1.0 if not capacity or portions <= capacity else capacity / portions
    return round(100 * (0.5 * dist_factor + 0.3 * time_factor + 0.2 * fit), 1)


# ---------------------------------------------------------------- database
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    db = g.pop("db", None)
    if db:
        db.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  role TEXT NOT NULL CHECK(role IN ('donor','receiver')),
  name TEXT NOT NULL, phone TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
  org_type TEXT, address TEXT, lat REAL NOT NULL, lng REAL NOT NULL,
  capacity INTEGER, diet TEXT DEFAULT 'veg'
);
CREATE TABLE IF NOT EXISTS volunteers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT, phone TEXT, vehicle TEXT, lat REAL, lng REAL, available INTEGER DEFAULT 1
);
-- status: posted (portions still open) | allocated (all claimed) | expired | cancelled
CREATE TABLE IF NOT EXISTS donations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  donor_id INTEGER NOT NULL, dish TEXT NOT NULL, category TEXT NOT NULL,
  diet TEXT NOT NULL DEFAULT 'nonveg',
  portions INTEGER NOT NULL, remaining INTEGER NOT NULL DEFAULT 0,
  notes TEXT, pickup_address TEXT, lat REAL NOT NULL, lng REAL NOT NULL,
  cooked_at TEXT NOT NULL, safe_until TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'posted', created_at TEXT
);
-- one row per receiver's share of a donation = one volunteer trip
-- status: accepted | picked_up | delivered
CREATE TABLE IF NOT EXISTS allocations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  donation_id INTEGER NOT NULL, receiver_id INTEGER NOT NULL, portions INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'accepted', volunteer_id INTEGER,
  accepted_at TEXT, picked_at TEXT, delivered_at TEXT,
  UNIQUE(donation_id, receiver_id)
);
CREATE TABLE IF NOT EXISTS declines (
  donation_id INTEGER NOT NULL, receiver_id INTEGER NOT NULL,
  PRIMARY KEY(donation_id, receiver_id)
);
"""

# Demo volunteers around Kochi / Angamaly (Kerala). Edit freely.
DEMO_VOLUNTEERS = [
    ("Arun K", "9000000001", "Bike", 10.1960, 76.3860),
    ("Meera S", "9000000002", "Scooter", 10.0261, 76.3125),
    ("Joseph T", "9000000003", "Car", 10.1500, 76.4000),
    ("Fathima R", "9000000004", "Bike", 9.9816, 76.2999),
    ("Vishnu P", "9000000005", "Van", 10.0889, 76.3500),
]


def migrate(db):
    """Upgrade a foodbridge.db made by the old single-receiver version, keeping its data."""
    cols = lambda t: {r[1] for r in db.execute(f"PRAGMA table_info({t})")}
    if "diet" not in cols("users"):
        # old receivers are treated as veg-only (the safe choice) until they change it
        db.execute("ALTER TABLE users ADD COLUMN diet TEXT DEFAULT 'veg'")
    dcols = cols("donations")
    if "diet" not in dcols:
        # old donations had no veg/non-veg field, so assume non-veg (never sent to veg-only)
        db.execute("ALTER TABLE donations ADD COLUMN diet TEXT NOT NULL DEFAULT 'nonveg'")
    if "remaining" not in dcols:
        db.execute("ALTER TABLE donations ADD COLUMN remaining INTEGER NOT NULL DEFAULT 0")
        db.execute("UPDATE donations SET remaining=portions WHERE status='posted'")
        if "receiver_id" in dcols:
            db.execute(
                "INSERT OR IGNORE INTO allocations(donation_id,receiver_id,portions,status,volunteer_id,"
                "accepted_at,picked_at,delivered_at) SELECT id,receiver_id,portions,status,volunteer_id,"
                "accepted_at,picked_at,delivered_at FROM donations WHERE receiver_id IS NOT NULL "
                "AND status IN ('accepted','picked_up','delivered')")
            db.execute("UPDATE donations SET status='allocated' "
                       "WHERE status IN ('accepted','picked_up','delivered')")


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA)
    migrate(db)
    if db.execute("SELECT COUNT(*) FROM volunteers").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO volunteers(name,phone,vehicle,lat,lng) VALUES (?,?,?,?,?)",
            DEMO_VOLUNTEERS)
    db.commit()
    db.close()


# ---------------------------------------------------------------- helpers
FMT = "%Y-%m-%dT%H:%M"


def now():
    return datetime.now().replace(microsecond=0)


def parse(ts):
    return datetime.strptime(ts[:16], FMT)


def minutes_left(d):
    return int((parse(d["safe_until"]) - now()).total_seconds() // 60)


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def login_required(role):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            u = current_user()
            if not u:
                return redirect(url_for("login"))
            if u["role"] != role:
                flash(f"That page is for {role}s.", "error")
                return redirect(url_for("index"))
            return fn(*a, **kw)
        return wrapper
    return deco


def expire_old():
    db = get_db()
    db.execute("UPDATE donations SET status='expired' WHERE status='posted' AND safe_until < ?",
               (now().strftime(FMT),))
    db.commit()


def assign_volunteers():
    """Give every accepted-but-unassigned share the nearest free volunteer (one trip each)."""
    db = get_db()
    pending = db.execute(
        "SELECT a.id, d.lat, d.lng FROM allocations a JOIN donations d ON d.id=a.donation_id "
        "WHERE a.status='accepted' AND a.volunteer_id IS NULL ORDER BY a.accepted_at, a.id").fetchall()
    for a in pending:
        free = db.execute("SELECT * FROM volunteers WHERE available=1").fetchall()
        if not free:
            break
        best = min(free, key=lambda v: haversine(a["lat"], a["lng"], v["lat"], v["lng"]))
        db.execute("UPDATE allocations SET volunteer_id=? WHERE id=?", (best["id"], a["id"]))
        db.execute("UPDATE volunteers SET available=0 WHERE id=?", (best["id"],))
    db.commit()


def refresh():
    expire_old()
    assign_volunteers()


# ---------------------------------------------------------------- AI split planning
def receiver_load():
    """Per receiver: portions on the way right now, and portions received today."""
    today = now().strftime("%Y-%m-%dT00:00")
    rows = get_db().execute(
        "SELECT receiver_id,"
        " SUM(CASE WHEN status IN ('accepted','picked_up') THEN portions ELSE 0 END) AS in_flight,"
        " SUM(CASE WHEN accepted_at >= ? THEN portions ELSE 0 END) AS today "
        "FROM allocations GROUP BY receiver_id", (today,)).fetchall()
    return {r["receiver_id"]: (r["in_flight"] or 0, r["today"] or 0) for r in rows}


def candidates_for(d, load=None):
    """Receivers that may get a share of donation d. All the hard filters live here."""
    db = get_db()
    load = load if load is not None else receiver_load()
    left = minutes_left(d)
    skip = {r[0] for r in db.execute(
        "SELECT receiver_id FROM declines WHERE donation_id=? "
        "UNION SELECT receiver_id FROM allocations WHERE donation_id=?", (d["id"], d["id"]))}
    out = []
    for r in db.execute("SELECT * FROM users WHERE role='receiver'").fetchall():
        if r["id"] in skip or not diet_ok(d["diet"], r["diet"] or "veg"):
            continue
        dist = haversine(d["lat"], d["lng"], r["lat"], r["lng"])
        if dist > MAX_KM or dist / CITY_KMPH * 60 + HANDLING_MIN > left:
            continue
        in_flight, got_today = load.get(r["id"], (0, 0))
        cap = r["capacity"]
        room = (cap - in_flight) if cap else d["remaining"]
        if cap:
            need = 1 - min(got_today / cap, 1)
        else:
            need = 1.0 if got_today == 0 else 0.5
        out.append(Candidate(r["id"], r["name"], round(dist, 2), room, need, got_today))
    return out


def plan_for(d, load=None):
    """The AI's current split plan for the open portions of donation d."""
    if d["status"] != "posted" or d["remaining"] <= 0 or minutes_left(d) <= 0:
        return {"method": "none", "shares": [], "unplaced": 0}
    shares, method = plan_split(d["remaining"], candidates_for(d, load))
    placed = sum(p for _, p in shares)
    return {
        "method": method,
        "unplaced": d["remaining"] - placed,
        "shares": [{
            "receiver_id": c.id, "name": c.name, "portions": p, "distance_km": c.distance_km,
            "reason": f"{c.distance_km} km away, room for {c.room}, "
                      + ("no food received yet today" if c.got_today == 0
                         else f"{c.got_today} portions received today"),
        } for c, p in shares],
    }


def receivers_near(lat, lng, diet=None):
    rows = get_db().execute(
        "SELECT id,name,org_type,address,lat,lng,capacity,diet FROM users WHERE role='receiver'").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["distance_km"] = round(haversine(lat, lng, r["lat"], r["lng"]), 2)
        d["accepts"] = True if diet is None else diet_ok(diet, r["diet"] or "veg")
        out.append(d)
    out.sort(key=lambda x: x["distance_km"])
    return out


# ---------------------------------------------------------------- public pages
@app.route("/")
def index():
    refresh()
    db = get_db()
    stats = {
        "meals": db.execute("SELECT COALESCE(SUM(portions),0) FROM allocations "
                            "WHERE status='delivered'").fetchone()[0],
        "deliveries": db.execute("SELECT COUNT(*) FROM allocations WHERE status='delivered'").fetchone()[0],
        "donors": db.execute("SELECT COUNT(*) FROM users WHERE role='donor'").fetchone()[0],
        "receivers": db.execute("SELECT COUNT(*) FROM users WHERE role='receiver'").fetchone()[0],
    }
    return render_template("index.html", stats=stats, user=current_user())


@app.route("/register/<role>", methods=["GET", "POST"])
def register(role):
    if role not in ("donor", "receiver"):
        return redirect(url_for("index"))
    if request.method == "POST":
        f = request.form
        try:
            lat, lng = float(f["lat"]), float(f["lng"])
        except (KeyError, ValueError):
            flash("Please choose your location on the map.", "error")
            return render_template("register.html", role=role, user=None, form=f, diets=RECEIVER_DIETS)
        phone = f["phone"].strip()
        if len(f["password"]) < 4:
            flash("Password must be at least 4 characters.", "error")
            return render_template("register.html", role=role, user=None, form=f, diets=RECEIVER_DIETS)
        db = get_db()
        if db.execute("SELECT 1 FROM users WHERE phone=?", (phone,)).fetchone():
            flash("That phone number is already registered. Please log in.", "error")
            return render_template("register.html", role=role, user=None, form=f, diets=RECEIVER_DIETS)
        cap = int(f["capacity"]) if f.get("capacity", "").isdigit() and int(f["capacity"]) > 0 else None
        diet = f.get("diet") if f.get("diet") in RECEIVER_DIETS else "veg"
        cur = db.execute(
            "INSERT INTO users(role,name,phone,password_hash,org_type,address,lat,lng,capacity,diet) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (role, f["name"].strip(), phone, generate_password_hash(f["password"]),
             f.get("org_type"), f.get("address", "").strip(), lat, lng, cap, diet))
        db.commit()
        session["uid"] = cur.lastrowid
        return redirect(url_for(role))
    return render_template("register.html", role=role, user=None, form={}, diets=RECEIVER_DIETS)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = get_db().execute("SELECT * FROM users WHERE phone=?",
                             (request.form["phone"].strip(),)).fetchone()
        if u and check_password_hash(u["password_hash"], request.form["password"]):
            session["uid"] = u["id"]
            return redirect(url_for(u["role"]))
        flash("Wrong phone number or password.", "error")
    return render_template("login.html", user=None)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ---------------------------------------------------------------- donor
@app.route("/donor")
@login_required("donor")
def donor():
    refresh()
    return render_template("donor.html", user=current_user(),
                           categories=SHELF_LIFE_HOURS, hours=SHELF_LIFE_HOURS,
                           now=now().strftime(FMT))


@app.route("/donor/post", methods=["POST"])
@login_required("donor")
def donor_post():
    u, f = current_user(), request.form
    try:
        lat, lng = float(f["lat"]), float(f["lng"])
        portions = int(f["portions"])
        cooked = datetime.strptime(f["cooked_at"], FMT)
        assert portions > 0
    except Exception:
        flash("Please fill all fields correctly and pick the pickup point on the map.", "error")
        return redirect(url_for("donor"))
    diet = f.get("diet")
    if diet not in DIETS:
        flash("Please mark the food as Veg or Non-veg.", "error")
        return redirect(url_for("donor"))
    safe = estimate_safe_until(f["category"], cooked)
    if safe <= now():
        flash("By our food-safety estimate this food is already past its safe window, "
              "so it can't be listed.", "error")
        return redirect(url_for("donor"))
    db = get_db()
    cur = db.execute(
        "INSERT INTO donations(donor_id,dish,category,diet,portions,remaining,notes,pickup_address,"
        "lat,lng,cooked_at,safe_until,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (u["id"], f["dish"].strip(), f["category"], diet, portions, portions,
         f.get("notes", "").strip(), f.get("pickup_address", "").strip(), lat, lng,
         cooked.strftime(FMT), safe.strftime(FMT), now().strftime(FMT)))
    db.commit()
    d = db.execute("SELECT * FROM donations WHERE id=?", (cur.lastrowid,)).fetchone()
    plan = plan_for(d)
    when = safe.strftime('%I:%M %p')
    if plan["shares"]:
        parts = ", ".join(f"{s['name']} ({s['portions']})" for s in plan["shares"])
        msg = f"Listed! Safe until about {when}. AI split plan for {portions} portions: {parts}."
        if plan["unplaced"]:
            msg += (f" {plan['unplaced']} portions have no matching receiver with room yet; "
                    "the plan updates as receivers respond.")
        flash(msg, "ok")
    else:
        flash(f"Listed (safe until about {when}), but no receiver within {MAX_KM} km can take "
              f"{DIETS[diet].lower()} food and be reached in time, so nobody has been offered it yet.",
              "error")
    return redirect(url_for("donor"))


@app.route("/donor/cancel/<int:did>", methods=["POST"])
@login_required("donor")
def donor_cancel(did):
    """Cancels the portions nobody has accepted yet. Accepted shares still get delivered."""
    db = get_db()
    db.execute("UPDATE donations SET status='cancelled' WHERE id=? AND donor_id=? AND status='posted'",
               (did, session["uid"]))
    db.commit()
    return redirect(url_for("donor"))


@app.route("/api/donor/donations")
@login_required("donor")
def api_donor_donations():
    refresh()
    db = get_db()
    rows = db.execute("SELECT * FROM donations WHERE donor_id=? ORDER BY id DESC",
                      (session["uid"],)).fetchall()
    allocs = db.execute(
        "SELECT a.*, r.name AS receiver_name, r.phone AS receiver_phone, r.lat AS rlat, r.lng AS rlng,"
        " v.name AS vol_name, v.phone AS vol_phone, v.vehicle AS vol_vehicle, v.lat AS vlat, v.lng AS vlng "
        "FROM allocations a JOIN donations d ON d.id=a.donation_id JOIN users r ON r.id=a.receiver_id "
        "LEFT JOIN volunteers v ON v.id=a.volunteer_id WHERE d.donor_id=? ORDER BY a.id",
        (session["uid"],)).fetchall()
    load = receiver_load()
    pos = {u["id"]: (u["lat"], u["lng"]) for u in db.execute(
        "SELECT id,lat,lng FROM users WHERE role='receiver'")}
    out = []
    for r in rows:
        d = dict(r)
        d["minutes_left"] = minutes_left(r)
        d["allocations"] = []
        for a in allocs:
            if a["donation_id"] == r["id"]:
                a = dict(a)
                a["distance_km"] = round(haversine(r["lat"], r["lng"], a["rlat"], a["rlng"]), 2)
                d["allocations"].append(a)
        d["plan"] = plan_for(r, load)
        for share in d["plan"]["shares"]:
            share["lat"], share["lng"] = pos[share["receiver_id"]]
        out.append(d)
    return jsonify(out)


@app.route("/api/donor/nearby")
@login_required("donor")
def api_donor_nearby():
    u = current_user()
    lat = request.args.get("lat", type=float, default=u["lat"])
    lng = request.args.get("lng", type=float, default=u["lng"])
    diet = request.args.get("diet")
    return jsonify(receivers_near(lat, lng, diet if diet in DIETS else None)[:10])


# ---------------------------------------------------------------- receiver
@app.route("/receiver")
@login_required("receiver")
def receiver():
    refresh()
    return render_template("receiver.html", user=current_user(), diets=RECEIVER_DIETS)


@app.route("/receiver/settings", methods=["POST"])
@login_required("receiver")
def receiver_settings():
    f = request.form
    diet = f.get("diet") if f.get("diet") in RECEIVER_DIETS else "veg"
    cap = int(f["capacity"]) if f.get("capacity", "").isdigit() and int(f["capacity"]) > 0 else None
    db = get_db()
    db.execute("UPDATE users SET diet=?, capacity=? WHERE id=?", (diet, cap, session["uid"]))
    db.commit()
    flash("Saved. New offers will follow these settings.", "ok")
    return redirect(url_for("receiver"))


@app.route("/api/receiver/open")
@login_required("receiver")
def api_receiver_open():
    """Donations where the AI plan currently gives THIS receiver a share."""
    refresh()
    u = current_user()
    rows = get_db().execute(
        "SELECT d.*, du.name AS donor_name, du.phone AS donor_phone FROM donations d "
        "JOIN users du ON du.id=d.donor_id WHERE d.status='posted' AND d.remaining>0").fetchall()
    load = receiver_load()
    out = []
    for r in rows:
        plan = plan_for(r, load)
        mine = next((s for s in plan["shares"] if s["receiver_id"] == u["id"]), None)
        if not mine:
            continue
        d = dict(r)
        d["minutes_left"] = minutes_left(r)
        d["distance_km"] = mine["distance_km"]
        d["my_share"] = mine["portions"]
        d["reason"] = mine["reason"]
        d["split_between"] = len(plan["shares"])
        d["method"] = plan["method"]
        d["score"] = match_score(d["distance_km"], d["my_share"], d["minutes_left"], u["capacity"])
        out.append(d)
    out.sort(key=lambda d: -d["score"])
    return jsonify(out)


@app.route("/api/receiver/mine")
@login_required("receiver")
def api_receiver_mine():
    refresh()
    u = current_user()
    rows = get_db().execute(
        "SELECT a.id, a.portions, a.status, a.delivered_at, d.dish, d.diet, d.lat, d.lng,"
        " du.name AS donor_name, du.phone AS donor_phone, v.name AS vol_name,"
        " v.phone AS vol_phone, v.vehicle AS vol_vehicle, v.lat AS vlat, v.lng AS vlng "
        "FROM allocations a JOIN donations d ON d.id=a.donation_id JOIN users du ON du.id=d.donor_id "
        "LEFT JOIN volunteers v ON v.id=a.volunteer_id "
        "WHERE a.receiver_id=? ORDER BY a.id DESC", (u["id"],)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["distance_km"] = round(haversine(u["lat"], u["lng"], r["lat"], r["lng"]), 2)
        out.append(d)
    return jsonify(out)


@app.route("/receiver/accept/<int:did>", methods=["POST"])
@login_required("receiver")
def receiver_accept(did):
    """Accept a share. The plan is advice; the hard rules are re-checked here."""
    db = get_db()
    u = current_user()
    want = (request.get_json(silent=True) or {}).get("portions")
    d = db.execute("SELECT * FROM donations WHERE id=? AND status='posted' AND remaining>0",
                   (did,)).fetchone()
    if not d or minutes_left(d) <= 0:
        return jsonify(ok=False, msg="Sorry, this donation was just taken or has expired."), 409
    if db.execute("SELECT 1 FROM allocations WHERE donation_id=? AND receiver_id=?", (did, u["id"])).fetchone():
        return jsonify(ok=False, msg="You already accepted a share of this donation."), 409
    me = next((c for c in candidates_for(d) if c.id == u["id"]), None)
    if not me:
        return jsonify(ok=False, msg="This food isn't a match for you any more "
                                     "(diet, distance, time or capacity)."), 409
    try:
        want = int(want)
    except (TypeError, ValueError):
        want = me.room
    give = min(max(want, 1), me.room, d["remaining"])
    # atomic claim: two receivers can't take the same portions
    cur = db.execute("UPDATE donations SET remaining=remaining-? WHERE id=? AND status='posted' "
                     "AND remaining>=?", (give, did, give))
    if cur.rowcount == 0:
        db.rollback()
        return jsonify(ok=False, msg="Someone just took part of this. Refresh to see the new plan."), 409
    try:
        db.execute("INSERT INTO allocations(donation_id,receiver_id,portions,accepted_at) VALUES (?,?,?,?)",
                   (did, u["id"], give, now().strftime(FMT)))
    except sqlite3.IntegrityError:
        db.rollback()
        return jsonify(ok=False, msg="You already accepted a share of this donation."), 409
    db.execute("UPDATE donations SET status='allocated' WHERE id=? AND remaining=0", (did,))
    db.commit()
    assign_volunteers()
    return jsonify(ok=True, portions=give)


@app.route("/receiver/decline/<int:did>", methods=["POST"])
@login_required("receiver")
def receiver_decline(did):
    """Say no; the AI re-plans the portions among the other receivers."""
    db = get_db()
    db.execute("INSERT OR IGNORE INTO declines(donation_id,receiver_id) VALUES (?,?)",
               (did, session["uid"]))
    db.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- volunteers
@app.route("/volunteer")
def volunteer_home():
    refresh()
    vols = get_db().execute("SELECT * FROM volunteers").fetchall()
    return render_template("volunteer.html", vols=vols, vid=None, user=current_user())


@app.route("/volunteer/<int:vid>")
def volunteer_view(vid):
    refresh()
    db = get_db()
    vols = db.execute("SELECT * FROM volunteers").fetchall()
    return render_template("volunteer.html", vols=vols, vid=vid, user=current_user())


@app.route("/api/volunteer/<int:vid>/task")
def api_volunteer_task(vid):
    refresh()
    row = get_db().execute(
        "SELECT a.id, a.portions, a.status, d.dish, d.diet, d.notes, d.pickup_address, d.safe_until,"
        " d.lat, d.lng, du.name AS donor_name, du.phone AS donor_phone, r.name AS receiver_name,"
        " r.phone AS receiver_phone, r.address AS receiver_address, r.lat AS rlat, r.lng AS rlng,"
        " v.lat AS vlat, v.lng AS vlng "
        "FROM allocations a JOIN donations d ON d.id=a.donation_id JOIN users du ON du.id=d.donor_id "
        "JOIN users r ON r.id=a.receiver_id JOIN volunteers v ON v.id=a.volunteer_id "
        "WHERE a.volunteer_id=? AND a.status IN ('accepted','picked_up') ORDER BY a.id DESC LIMIT 1",
        (vid,)).fetchone()
    return jsonify(dict(row) if row else None)


@app.route("/volunteer/<int:vid>/advance/<int:aid>", methods=["POST"])
def volunteer_advance(vid, aid):
    db = get_db()
    a = db.execute("SELECT a.*, d.lat, d.lng FROM allocations a JOIN donations d ON d.id=a.donation_id "
                   "WHERE a.id=? AND a.volunteer_id=?", (aid, vid)).fetchone()
    if not a:
        return jsonify(ok=False), 404
    if a["status"] == "accepted":
        db.execute("UPDATE allocations SET status='picked_up', picked_at=? WHERE id=?",
                   (now().strftime(FMT), aid))
        # volunteer is now at the donor's location
        db.execute("UPDATE volunteers SET lat=?, lng=? WHERE id=?", (a["lat"], a["lng"], vid))
    elif a["status"] == "picked_up":
        r = db.execute("SELECT lat,lng FROM users WHERE id=?", (a["receiver_id"],)).fetchone()
        db.execute("UPDATE allocations SET status='delivered', delivered_at=? WHERE id=?",
                   (now().strftime(FMT), aid))
        db.execute("UPDATE volunteers SET available=1, lat=?, lng=? WHERE id=?",
                   (r["lat"], r["lng"], vid))
    db.commit()
    assign_volunteers()
    return jsonify(ok=True)


@app.route("/api/volunteers")
def api_volunteers():
    return jsonify([dict(v) for v in get_db().execute("SELECT * FROM volunteers").fetchall()])


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
