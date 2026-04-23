import os
import uuid
import json
import csv
import io
import datetime as dt
from collections import defaultdict

from flask import (
    Flask, render_template, request, redirect, url_for,
    jsonify, send_file, flash
)

# --- App setup ---
app = Flask(__name__)
app.secret_key = "dev-secret"  # ok for class project
DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "transactions.json")


# --- Storage helpers (JSON file, no DB) ---
def _ensure_store():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)


def load_tx():
    _ensure_store()
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_tx(items):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)


# --- Utilities ---
def to_date(s):
    # expected "YYYY-MM-DD"
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def month_key(d):
    return d.strftime("%Y-%m")


def safe_amount(val):
    return round(float(val), 2)


# --- "AI-ish" insights (simple, explainable heuristics) ---
def compute_insights(items):
    # normalize and guard
    if not items:
        return {
            "total_income": 0.0,
            "total_expense": 0.0,
            "net": 0.0,
            "expenses_by_category": {},
            "monthly_series": [],
            "forecast_next_month_net": 0.0,
            "avg_burn_rate": 0.0,
            "tips": ["Add a few transactions to see insights!"]
        }

    total_income = sum(x["amount"] for x in items if x["type"] == "income")
    total_expense = sum(x["amount"] for x in items if x["type"] == "expense")
    net = round(total_income - total_expense, 2)

    # Category breakdown (expenses only)
    cat = defaultdict(float)
    for t in items:
        if t["type"] == "expense":
            cat[t["category"]] += t["amount"]
    cat = {k: round(v, 2) for k, v in cat.items()}

    # Monthly aggregates
    monthly = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    for t in items:
        m = month_key(to_date(t["date"]))
        monthly[m][t["type"]] += t["amount"]

    months_sorted = sorted(monthly.keys())
    series = []
    for m in months_sorted:
        inc = round(monthly[m]["income"], 2)
        exp = round(monthly[m]["expense"], 2)
        series.append({
            "month": m,
            "income": inc,
            "expense": exp,
            "net": round(inc - exp, 2)
        })

    # Forecast: average of last up-to-3 monthly nets
    if series:
        last3 = [s["net"] for s in series[-3:]]
        forecast = round(sum(last3) / len(last3), 2)
        last3_exp = [s["expense"] for s in series[-3:]]
        burn_rate = round(sum(last3_exp) / len(last3_exp), 2)
    else:
        forecast = 0.0
        burn_rate = 0.0

    # Tips (very simple rules)
    tips = []
    if total_expense > total_income:
        tips.append("Your expenses exceed income. Aim to reduce variable costs or increase income sources.")
    if cat:
        # dominant category check
        total_exp = sum(cat.values())
        top_cat, top_val = max(cat.items(), key=lambda kv: kv[1])
        if total_exp > 0 and (top_val / total_exp) > 0.4:
            tips.append(f"'{top_cat}' is over 40% of your expenses. Consider setting a cap for this category.")
    if len(series) >= 3:
        # simple rising-expenses pattern
        last3e = [s["expense"] for s in series[-3:]]
        if last3e[0] < last3e[1] < last3e[2]:
            tips.append("Expenses have risen 3 months in a row—review subscriptions or renegotiate bills.")
    if not tips:
        tips.append("Nice balance! Keep tracking to strengthen your trend insights.")

    return {
        "total_income": round(total_income, 2),
        "total_expense": round(total_expense, 2),
        "net": net,
        "expenses_by_category": cat,
        "monthly_series": series,
        "forecast_next_month_net": forecast,
        "avg_burn_rate": burn_rate,
        "tips": tips
    }


# --- Routes ---
@app.route("/", methods=["GET"])
def dashboard():
    items = load_tx()
    insights = compute_insights(items)
    # Pass data to the template; Jinja will JSON-serialize
    today = dt.date.today().isoformat()
    return render_template("index.html", items=items, insights=insights, today=today)


@app.route("/add", methods=["POST"])
def add():
    # form fields: date, description, category, type, amount
    form = request.form
    try:
        record = {
            "id": str(uuid.uuid4()),
            "date": form["date"],  # validate format
            "description": form.get("description", "").strip() or "—",
            "category": form.get("category", "").strip() or "General",
            "type": form["type"],  # "income" or "expense"
            "amount": safe_amount(form["amount"])
        }
        # basic sanity
        _ = to_date(record["date"])
        assert record["type"] in ("income", "expense")
        if record["amount"] < 0:
            record["amount"] = -record["amount"]  # make positive
    except Exception as e:
        flash(f"Invalid input: {e}", "error")
        return redirect(url_for("dashboard"))

    items = load_tx()
    items.append(record)
    save_tx(items)
    flash("Transaction added.", "ok")
    return redirect(url_for("dashboard"))


@app.route("/delete/<tx_id>", methods=["POST"])
def delete(tx_id):
    items = load_tx()
    new_items = [x for x in items if x["id"] != tx_id]
    save_tx(new_items)
    flash("Transaction deleted.", "ok")
    return redirect(url_for("dashboard"))


@app.route("/export.csv", methods=["GET"])
def export_csv():
    items = load_tx()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "date", "description", "category", "type", "amount"])
    for t in items:
        writer.writerow([t["id"], t["date"], t["description"], t["category"], t["type"], t["amount"]])
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8")),
        as_attachment=True,
        download_name="transactions.csv",
        mimetype="text/csv"
    )


@app.route("/import", methods=["POST"])
def import_csv():
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("Please choose a CSV file.", "error")
        return redirect(url_for("dashboard"))

    try:
        text = file.read().decode("utf-8", errors="ignore")
        reader = csv.DictReader(io.StringIO(text))
        items = load_tx()
        for row in reader:
            # Accept both our header or a minimal set
            date = row.get("date") or row.get("Date")
            desc = (row.get("description") or row.get("Description") or "").strip() or "—"
            category = (row.get("category") or row.get("Category") or "").strip() or "General"
            typ = (row.get("type") or row.get("Type") or "expense").lower()
            amount = row.get("amount") or row.get("Amount")

            # validate
            _ = to_date(date)
            if typ not in ("income", "expense"):
                typ = "expense"
            amt = safe_amount(amount)

            items.append({
                "id": str(uuid.uuid4()),
                "date": date,
                "description": desc,
                "category": category,
                "type": typ,
                "amount": amt
            })
        save_tx(items)
        flash("Import complete.", "ok")
    except Exception as e:
        flash(f"Import failed: {e}", "error")

    return redirect(url_for("dashboard"))


# Simple JSON APIs (optional, used if you want to extend)
@app.route("/api/transactions", methods=["GET"])
def api_transactions():
    return jsonify(load_tx())


@app.route("/api/insights", methods=["GET"])
def api_insights():
    return jsonify(compute_insights(load_tx()))


if __name__ == "__main__":
    # For local dev
    app.run(debug=True)
