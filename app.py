from flask import Flask, render_template, request, redirect, url_for, session
import pandas as pd
import os
from werkzeug.security import generate_password_hash, check_password_hash
import random

app = Flask(__name__)
app.secret_key = "dev_secret_key"

DATA_FOLDER = "data"

COMPANIES = {
    "Apple": "Apple.csv",
    "Google": "Google.csv",
    "Amazon": "Amazon.csv",
    "Netflix": "Netflix.csv",
    "Facebook": "Facebook.csv",
    "Microsoft": "Microsoft.csv",
    "Tesla": "Tesla.csv",
    "Uber": "Uber.csv",
    "Walmart": "Walmart.csv",
    "Zoom": "Zoom.csv"
}

# -------- In-memory storage (LOCAL) --------
users = []
watchlists = []
portfolio = []   # NEW


def load_latest_prices():
    prices = []
    for company, file in COMPANIES.items():
        df = pd.read_csv(os.path.join(DATA_FOLDER, file))
        latest = df.iloc[-1]
        prices.append({
            "company": company,
            "price": round(float(latest["Close"]), 2),
            "date": latest["Date"]
        })
    return prices

def get_user():
    return next((u for u in users if u["name"] == session.get("user")), None)


# ---------------- ROUTES ---------------- #
@app.route("/")
def main():
    return render_template("main.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")



@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        users.append({
            "id": len(users) + 1,
            "name": request.form["name"],
            "email": request.form["email"],
            "password": generate_password_hash(request.form["password"]),
            "balance": 100000  # Virtual money
        })
        return redirect(url_for("login"))
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = next(
            (u for u in users if u["email"] == request.form["email"]),
            None
        )
        if user and check_password_hash(user["password"], request.form["password"]):
            session["user"] = user["name"]
            return redirect(url_for("dashboard"))
        return "Invalid login"
    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))

    stocks = load_latest_prices()
    user_watchlist = [w["company"] for w in watchlists if w["user"] == session["user"]]
    user = get_user()

    return render_template(
        "dashboard.html",
        stocks=stocks,
        user=session["user"],
        balance=user["balance"],
        user_watchlist=user_watchlist
    )


@app.route("/buy/<company>", methods=["POST"])
def buy_stock(company):
    if "user" not in session:
        return redirect(url_for("login"))

    qty = int(request.form["quantity"])
    user = get_user()

    stock = next(s for s in load_latest_prices() if s["company"] == company)
    total_cost = qty * stock["price"]

    if user["balance"] < total_cost:
        return "Insufficient balance"

    user["balance"] -= total_cost

    portfolio.append({
        "user": session["user"],
        "company": company,
        "quantity": qty,
        "buy_price": stock["price"]
    })

    return redirect(url_for("portfolio_page"))


@app.route("/sell/<company>", methods=["POST"])
def sell_stock(company):
    if "user" not in session:
        return redirect(url_for("login"))

    qty_to_sell = int(request.form["quantity"])
    sell_price = float(request.form["sell_price"])  # IMPORTANT

    user = get_user()

    holding = next(
        (p for p in portfolio
         if p["user"] == session["user"] and p["company"] == company),
        None
    )

    if not holding or holding["quantity"] < qty_to_sell:
        return "Not enough quantity to sell"

    # Update balance using SAME price user saw
    user["balance"] += sell_price * qty_to_sell

    holding["quantity"] -= qty_to_sell

    if holding["quantity"] == 0:
        portfolio.remove(holding)

    return redirect(url_for("portfolio_page"))

@app.route("/portfolio")
def portfolio_page():
    if "user" not in session:
        return redirect(url_for("login"))

    user = get_user()
    user_portfolio = [p for p in portfolio if p["user"] == session["user"]]

    # get latest prices
    prices = load_latest_prices()

    portfolio_view = []

    for p in user_portfolio:
        stock_price = next(s["price"] for s in prices if s["company"] == p["company"])

        # simulated current price
        current_price = round(stock_price * random.uniform(0.95, 1.05), 2)

        pnl = round((current_price - p["buy_price"]) * p["quantity"], 2)

        portfolio_view.append({
            "company": p["company"],
            "quantity": p["quantity"],
            "buy_price": p["buy_price"],
            "current_price": current_price,
            "pnl": pnl
        })

    return render_template(
        "portfolio.html",
        portfolio=portfolio_view,
        balance=user["balance"],
        user=session["user"]
    )

@app.route("/chart/<company>")
def chart(company):
    if "user" not in session:
        return redirect(url_for("login"))

    file = COMPANIES.get(company)
    if not file:
        return "Company not found"

    df = pd.read_csv(os.path.join(DATA_FOLDER, file))

    # Convert to lists for JS
    dates = df["Date"].tolist()
    prices = df["Close"].tolist()

    return render_template(
        "chart.html",
        company=company,
        dates=dates,
        prices=prices
    )

    

@app.route("/add_to_watchlist/<company>")
def add_to_watchlist(company):
    if not any(w["user"] == session["user"] and w["company"] == company for w in watchlists):
        watchlists.append({"user": session["user"], "company": company})
    return redirect(url_for("dashboard"))


@app.route("/watchlist")
def watchlist():
    if "user" not in session:
        return redirect(url_for("login"))

    user = get_user()  # get logged-in user

    user_companies = [w["company"] for w in watchlists if w["user"] == session["user"]]
    all_prices = load_latest_prices()
    watchlist_data = [s for s in all_prices if s["company"] in user_companies]

    return render_template(
        "watchlist.html",
        watchlist=watchlist_data,
        user=session["user"],
        balance=user["balance"]   
    )


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
