from flask import Flask, render_template, request, redirect, session, url_for
import pandas as pd
import os

app = Flask(__name__)
app.secret_key = "dev_secret_key"

DATA_FOLDER = "data"

COMPANIES = {
    "Apple": "Apple.csv",
    "Google": "Google.csv",
    "Amazon": "Amazon.csv",
    "Netflix": "Netflix.csv"
}

# ---------------- HELPERS ----------------
def latest_price(company):
    df = pd.read_csv(os.path.join(DATA_FOLDER, COMPANIES[company]))
    row = df.iloc[-1]
    return float(row["Close"]), row["Date"]

def all_prices():
    data = []
    for c in COMPANIES:
        price, date = latest_price(c)
        data.append({"company": c, "price": round(price, 2), "date": date})
    return data

# ---------------- MAIN ----------------
@app.route("/")
def main():
    return render_template("main.html")

# ---------------- AUTH ----------------
@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        session["user"] = request.form["name"]
        session["email"] = request.form["email"]
        session["balance"] = 100000
        session["portfolio"] = {}
        session["watchlist"] = []
        return redirect("/dashboard")
    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        session["user"] = request.form["email"].split("@")[0]
        session["email"] = request.form["email"]
        session.setdefault("balance", 100000)
        session.setdefault("portfolio", {})
        session.setdefault("watchlist", [])
        return redirect("/dashboard")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/login")

    return render_template(
        "dashboard.html",
        stocks=all_prices(),
        user=session["user"],
        balance=session["balance"],
        user_watchlist=session["watchlist"]
    )

# ---------------- BUY ----------------
@app.route("/buy/<company>", methods=["POST"])
def buy(company):
    qty = int(request.form["quantity"])
    price, _ = latest_price(company)
    total = qty * price

    if total > session["balance"]:
        return "Insufficient balance"

    session["balance"] -= total
    session["portfolio"][company] = session["portfolio"].get(company, 0) + qty
    return redirect("/portfolio")

# ---------------- PORTFOLIO ----------------
@app.route("/portfolio")
def portfolio():
    prices = dict((s["company"], s["price"]) for s in all_prices())
    view = []

    for company, qty in session["portfolio"].items():
        view.append({
            "company": company,
            "quantity": qty,
            "buy_price": prices[company],
            "current_price": prices[company],
            "pnl": 0
        })

    return render_template(
        "portfolio.html",
        portfolio=view,
        balance=session["balance"],
        user=session["user"]
    )

# ---------------- WATCHLIST ----------------
@app.route("/add_to_watchlist/<company>")
def add_watchlist(company):
    if company not in session["watchlist"]:
        session["watchlist"].append(company)
    return redirect("/dashboard")

@app.route("/watchlist")
def watchlist():
    prices = all_prices()
    data = [p for p in prices if p["company"] in session["watchlist"]]

    return render_template(
        "watchlist.html",
        watchlist=data,
        balance=session["balance"],
        user=session["user"]
    )

# ---------------- CHART ----------------
@app.route("/chart/<company>")
def chart(company):
    df = pd.read_csv(os.path.join(DATA_FOLDER, COMPANIES[company]))
    return render_template(
        "chart.html",
        company=company,
        data=df.tail(20).to_dict("records")
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
