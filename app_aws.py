from flask import Flask, render_template, request, redirect, url_for, session
import pandas as pd
import os
import random
import boto3
from werkzeug.security import generate_password_hash, check_password_hash
from boto3.dynamodb.conditions import Key

app = Flask(__name__)
application = app
app.secret_key = os.environ.get("SECRET_KEY", "fallback_secret")

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

# ---------- AWS ---------- #
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
sns = boto3.client("sns", region_name="us-east-1")

users_table = dynamodb.Table("Users")
portfolio_table = dynamodb.Table("Portfolio")
watchlist_table = dynamodb.Table("Watchlist")

SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN")

# ---------- HELPERS ---------- #
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

def get_stock_price(company):
    file = COMPANIES.get(company)
    df = pd.read_csv(os.path.join(DATA_FOLDER, file))
    return round(float(df.iloc[-1]["Close"]), 2)

def send_notification(msg):
    if SNS_TOPIC_ARN:
        sns.publish(TopicArn=SNS_TOPIC_ARN, Message=msg)

# ---------- AUTH ---------- #
@app.route("/")
def main():
    return render_template("main.html")

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
        user = users_table.get_item(Key={"email": request.form["email"]}).get("Item")
        if user and check_password_hash(user["password"], request.form["password"]):
            session["email"] = user["email"]
            session["user"] = user["name"]
            return redirect("/dashboard")
        return "Invalid login"
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------- DASHBOARD ---------- #
@app.route("/dashboard")
def dashboard():
    if "email" not in session:
        return redirect("/login")

    stocks = load_latest_prices()
    user = users_table.get_item(Key={"email": session["email"]}).get("Item")

    wl = watchlist_table.query(
        KeyConditionExpression=Key("user").eq(session["email"])
    ).get("Items", [])

    watchlist = [i["company"] for i in wl]

    return render_template(
        "dashboard.html",
        stocks=stocks,
        user=session["user"],
        balance=user["balance"],
        user_watchlist=watchlist
    )

# ---------- BUY ---------- #
@app.route("/buy/<company>", methods=["POST"])
def buy_stock(company):
    qty = int(request.form.get("quantity", 1))
    price = get_stock_price(company)
    total = qty * price

    user = users_table.get_item(Key={"email": session["email"]}).get("Item")
    if total > user["balance"]:
        return "Insufficient balance"

    users_table.update_item(
        Key={"email": session["email"]},
        UpdateExpression="SET balance = balance - :amt",
        ExpressionAttributeValues={":amt": total}
    )

    portfolio_table.put_item(Item={
        "user": session["email"],
        "company": company,
        "quantity": qty,
        "buy_price": price
    })

    return redirect("/portfolio")

# ---------- SELL ---------- #
@app.route("/sell/<company>", methods=["POST"])
def sell_stock(company):
    qty = int(request.form["quantity"])
    sell_price = float(request.form["sell_price"])

    holding = portfolio_table.get_item(
        Key={"user": session["email"], "company": company}
    ).get("Item")

    if not holding or holding["quantity"] < qty:
        return "Not enough quantity"

    users_table.update_item(
        Key={"email": session["email"]},
        UpdateExpression="SET balance = balance + :amt",
        ExpressionAttributeValues={":amt": qty * sell_price}
    )

    portfolio_table.delete_item(Key={"user": session["email"], "company": company})
    return redirect("/portfolio")

# ---------- PORTFOLIO ---------- #
@app.route("/portfolio")
def portfolio():
    response = portfolio_table.query(
        KeyConditionExpression=Key("user").eq(session["email"])
    )

    prices = load_latest_prices()
    portfolio = []

    for p in response.get("Items", []):
        cur = next(s["price"] for s in prices if s["company"] == p["company"])
        pnl = round((cur - p["buy_price"]) * p["quantity"], 2)
        portfolio.append({**p, "current_price": cur, "pnl": pnl})

    user = users_table.get_item(Key={"email": session["email"]}).get("Item")

    return render_template("portfolio.html", portfolio=portfolio, balance=user["balance"])

# ---------- WATCHLIST ---------- #
@app.route("/add_to_watchlist/<company>")
def add_to_watchlist(company):
    watchlist_table.put_item(Item={
        "user": session["email"],
        "company": company
    })
    return redirect("/dashboard")

@app.route("/watchlist")
def watchlist():
    response = watchlist_table.query(
        KeyConditionExpression=Key("user").eq(session["email"])
    )
    return render_template("watchlist.html", items=response.get("Items", []))

# ---------- CHART ---------- #
@app.route("/chart/<company>")
def chart(company):
    df = pd.read_csv(os.path.join(DATA_FOLDER, COMPANIES[company]))
    return render_template("chart.html", data=df.to_dict("records"), company=company)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
