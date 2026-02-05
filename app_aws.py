from flask import Flask, render_template, request, redirect, url_for, session
import pandas as pd
import os
import boto3
from werkzeug.security import generate_password_hash, check_password_hash
from boto3.dynamodb.conditions import Key

app = Flask(__name__)
application = app
app.secret_key = "dev_secret_key"

DATA_FOLDER = "data"

COMPANIES = {
    "Apple": "Apple.csv",
    "Google": "Google.csv",
    "Amazon": "Amazon.csv",
    "Netflix": "Netflix.csv"
}

# ---------- AWS ----------
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
users_table = dynamodb.Table("Users")
portfolio_table = dynamodb.Table("Portfolio")
watchlist_table = dynamodb.Table("Watchlist")

# ---------- HELPERS ----------
def get_latest_price(company):
    try:
        df = pd.read_csv(os.path.join(DATA_FOLDER, COMPANIES[company]))
        row = df.iloc[-1]
        return round(float(row["Close"]), 2), row["Date"]
    except Exception as e:
        print("PRICE ERROR:", e)
        return None, None

def get_all_prices():
    data = []
    for c in COMPANIES:
        price, date = get_latest_price(c)
        if price:
            data.append({"company": c, "price": price, "date": date})
    return data

# ---------- MAIN ----------
@app.route("/")
def main():
    return render_template("main.html")

# ---------- AUTH ----------
@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        users_table.put_item(Item={
            "email": request.form["email"],
            "name": request.form["name"],
            "password": generate_password_hash(request.form["password"]),
            "balance": 100000
        })
        return redirect("/login")
    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        user = users_table.get_item(
            Key={"email": request.form["email"]}
        ).get("Item")

        if user and check_password_hash(user["password"], request.form["password"]):
            session["email"] = user["email"]
            session["user"] = user["name"]
            return redirect("/dashboard")
        return "Invalid credentials"

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------- DASHBOARD ----------
@app.route("/dashboard")
def dashboard():
    if "email" not in session:
        return redirect("/login")

    stocks = get_all_prices()
    user = users_table.get_item(Key={"email": session["email"]}).get("Item")

    wl = watchlist_table.query(
        KeyConditionExpression=Key("email").eq(session["email"])
    ).get("Items", [])

    watchlist = [i["company"] for i in wl]

    return render_template(
        "dashboard.html",
        stocks=stocks,
        user=session["user"],
        balance=user["balance"],
        user_watchlist=watchlist
    )

# ---------- BUY ----------
@app.route("/buy/<company>", methods=["]()
