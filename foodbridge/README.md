# FoodBridge: surplus food donation platform (hackday demo)

Donors (wedding halls, caterers, restaurants) post leftover food. Receivers (orphanages, shelters,
community kitchens) claim it. The nearest free volunteer is assigned automatically to carry it across.

## Run it

```bash
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

An internet connection is needed in the browser for the map tiles (OpenStreetMap), place search
(Nominatim) and road routing (OSRM).

## What is real and what is demo

- **Donors and receivers are real.** Register your own accounts (phone + password, location pinned on the map).
  No donor or receiver data is pre-loaded.
- **Volunteers are demo data** (5 seeded around Kochi / Angamaly, edit `DEMO_VOLUNTEERS` in `app.py`).
  Open the Volunteers page, pick one, and use the buttons to mark pickup and delivery.

## Demo script (2 browser windows, one normal and one incognito)

1. Register 2-3 **receivers** a few km apart with small capacities (e.g. 30, 40, 50). Make at least one
   "Veg only" and at least one "Veg and non-veg".
2. Register as a **donor** and post a big non-veg dish (e.g. 120 portions of chicken biryani), marked Non-veg.
   The flash message shows the AI split plan, and the donor map draws blue dashed lines to each planned receiver.
   The veg-only receiver is never offered it.
3. Log in as one receiver: it sees only its suggested share. **Accept** it, or **Decline** and watch the
   donor's plan re-shuffle the portions among the others.
4. Each accepted share gets its own nearest free volunteer. Volunteers tab: "I picked it up", "I delivered it".
5. The home page "meals delivered" counter goes up.

## If the donor and receiver don't connect on the map

- Donor page: under the pickup map it says how many receivers are within 25 km. If it says none, the
  receiver account is pinned somewhere else (or not registered yet). Log in as the receiver, or register
  again with the pin placed in the right locality.
- Use the same area for both pins. When searching a locality name, the search favours the part of the map
  you are looking at, so zoom to your area first. Always check the pin and marker before submitting.
- Use two browsers (or one normal and one incognito) so the donor and receiver logins don't replace each other.
- If the map is grey, tiles couldn't load: check the internet connection (a red notice appears).
- Receivers see a donation only while it is "posted" and still inside its safe-until time.

## Open source used

Flask, SQLite, OR-Tools (CP-SAT solver), Leaflet, OpenStreetMap, OSRM (routing), Nominatim (search).

## The AI part

**Splitting one big donation across several receivers** (`splitter.py`). This is a constrained
optimisation problem solved with Google OR-Tools CP-SAT, an open-source constraint solver:

- Decides, for each receiver, how many portions it gets (integer) and whether it gets a trip at all (yes/no).
- Hard rules: never more than the open portions, never more than a receiver's room, at least 5 portions per
  trip (no sending a volunteer 15 km for 2 plates), at most 4 receivers per donation.
- Objective, in priority order: feed as many people as possible, favour receivers who haven't had food
  today (fairness), then use fewer and shorter trips.
- Before the solver runs, `candidates_for()` in `app.py` filters receivers: veg / non-veg match, within 25 km,
  reachable before the food's safe-until time, not already served or declined.
- Re-plans automatically whenever someone accepts or declines, or a new receiver signs up.
- If OR-Tools isn't installed it falls back to a greedy planner, so the demo still runs.

**Veg / non-veg matching.** Donors must mark each dish Veg or Non-veg. Receivers choose "Veg only" or
"Veg and non-veg" at sign-up (changeable on their dashboard). Non-veg food is never offered to, or accepted
by, a veg-only receiver; the server re-checks this on accept, not just in the UI.

Other smaller pieces: `estimate_safe_until()` sets a food-safety window per food type, and `match_score()`
orders a receiver's offers.

Upgrading from the old version: just run it. An existing `foodbridge.db` is migrated in place. Old receivers
are set to "Veg only" and old donations to "Non-veg" (the safe choices) until changed.

Rule-based parts so far: the shelf-life table and the match score. Next steps: plan one vehicle route that drops several shares in a row (a vehicle routing problem,
also in OR-Tools), train a surplus-prediction model on past event data, and add a vision model that
estimates dish type and portions from a photo.

## Production notes (not done in the demo)

Receiver verification, OTP login, notifications (SMS / WhatsApp), real volunteer accounts with live GPS,
HTTPS, and food-safety compliance checks (for India: FSSAI guidelines).
