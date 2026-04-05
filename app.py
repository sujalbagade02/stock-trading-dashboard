from flask import Flask, render_template, request, redirect, url_for, session
import pandas as pd
import os
from werkzeug.security import generate_password_hash, check_password_hash
import random
from pymongo import MongoClient

app = Flask(__name__)
app.secret_key = "dev_secret_key"

#  MONGODB
client = MongoClient("mongodb+srv://sujalb2004_db_user:bunNxn9nHxlaE8yv@cluster0.qsyb4jn.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["stock_app"]

users_collection = db["users"]
watchlist_collection = db["watchlist"]
portfolio_collection = db["portfolio"]

#  DATA 
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

# HELPERS

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
    return users_collection.find_one({"email": session.get("user")})


#  ROUTES 

@app.route("/")
def main():
    return render_template("main.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


#  AUTH 

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        users_collection.insert_one({
            "name": request.form["name"],
            "email": request.form["email"],
            "password": generate_password_hash(request.form["password"]),
            "balance": 100000
        })
        return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = users_collection.find_one({"email": request.form["email"]})

        if user and check_password_hash(user["password"], request.form["password"]):
            session["user"] = user["email"]
            return redirect(url_for("dashboard"))

        return "Invalid login"

    return render_template("login.html")


# DASHBOARD

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))

    user = get_user()

    stocks = load_latest_prices()

    user_watchlist = [
        w["company"] for w in watchlist_collection.find({"user": session["user"]})
    ]

    return render_template(
        "dashboard.html",
        stocks=stocks,
        user=user["name"],
        balance=user["balance"],
        user_watchlist=user_watchlist
    )


#  BUY 

@app.route("/buy/<company>", methods=["POST"])
def buy_stock(company):
    user = get_user()

    qty = int(request.form["quantity"])
    stock = next(s for s in load_latest_prices() if s["company"] == company)

    total_cost = qty * stock["price"]

    if user["balance"] < total_cost:
        return "Insufficient balance"

    users_collection.update_one(
        {"email": session["user"]},
        {"$inc": {"balance": -total_cost}}
    )

    portfolio_collection.insert_one({
        "user": session["user"],
        "company": company,
        "quantity": qty,
        "buy_price": stock["price"]
    })

    return redirect(url_for("portfolio_page"))


# PORTFOLIO

@app.route("/portfolio")
def portfolio_page():
    user = get_user()

    user_portfolio = list(portfolio_collection.find({"user": session["user"]}))
    prices = load_latest_prices()

    portfolio_view = []

    for p in user_portfolio:
        stock_price = next(s["price"] for s in prices if s["company"] == p["company"])
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
        user=user["name"]
    )


#  WATCHLIST

@app.route("/add_to_watchlist/<company>")
def add_to_watchlist(company):
    if not watchlist_collection.find_one({"user": session["user"], "company": company}):
        watchlist_collection.insert_one({
            "user": session["user"],
            "company": company
        })

    return redirect(url_for("dashboard"))


@app.route("/watchlist")
def watchlist():
    user = get_user()

    user_companies = [w["company"] for w in watchlist_collection.find({"user": session["user"]})]
    all_prices = load_latest_prices()

    watchlist_data = [s for s in all_prices if s["company"] in user_companies]

    return render_template(
        "watchlist.html",
        watchlist=watchlist_data,
        user=user["name"],
        balance=user["balance"]
    )


#  LOGOUT 

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)