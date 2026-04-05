from flask import Flask, render_template, request, redirect, session
import pandas as pd
import os
import boto3
from decimal import Decimal
from werkzeug.security import generate_password_hash, check_password_hash
from boto3.dynamodb.conditions import Key
import random

app = Flask(__name__)
application = app
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

# ---------- AWS ----------
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
sns = boto3.client("sns", region_name="us-east-1")

SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:794038220422:aws_toppic"

users_table = dynamodb.Table("Users")
portfolio_table = dynamodb.Table("Portfolio")
watchlist_table = dynamodb.Table("Watchlist")

# ---------- EMAIL ----------
def send_email_notification(subject, message):
    sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=message)

# ---------- HELPERS ----------
def get_latest_price(company):
    df = pd.read_csv(os.path.join(DATA_FOLDER, COMPANIES[company]))
    row = df.iloc[-1]
    base_price = float(row["Close"])
    new_price = base_price * random.uniform(0.95, 1.05)
    return Decimal(str(round(new_price, 2))), row["Date"]

def get_all_prices():
    data = []
    for c in COMPANIES:
        price, date = get_latest_price(c)
        data.append({"company": c, "price": float(price), "date": date})
    return data

# ---------- MAIN ----------
@app.route("/")
def main():
    return render_template("main.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        user = users_table.get_item(Key={"email": request.form["email"]}).get("Item")
        if user and check_password_hash(user["password"], request.form["password"]):
            session["email"] = user["email"]
            session["user"] = user["name"]
            return redirect("/dashboard")
        return "Invalid credentials"
    return render_template("login.html")

@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        users_table.put_item(Item={
            "email": request.form["email"],
            "name": request.form["name"],
            "password": generate_password_hash(request.form["password"]),
            "balance": Decimal("100000")
        })
        return redirect("/login")
    return render_template("signup.html")

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
        balance=float(user["balance"]),
        user_watchlist=watchlist
    )

# ---------- WATCHLIST FIX ----------
@app.route("/add_to_watchlist/<company>")
def add_to_watchlist(company):

    if "email" not in session:
        return redirect("/login")

    # prevent duplicate
    existing = watchlist_table.get_item(
        Key={"email": session["email"], "company": company}
    ).get("Item")

    if not existing:
        watchlist_table.put_item(Item={
            "email": session["email"],
            "company": company
        })

    return redirect("/dashboard")

@app.route("/watchlist")
def watchlist():

    if "email" not in session:
        return redirect("/login")

    wl = watchlist_table.query(
        KeyConditionExpression=Key("email").eq(session["email"])
    ).get("Items", [])

    prices = get_all_prices()
    data = [p for p in prices if p["company"] in [i["company"] for i in wl]]

    user = users_table.get_item(Key={"email": session["email"]}).get("Item")

    return render_template(
        "watchlist.html",
        watchlist=data,
        balance=float(user["balance"]),
        user=session["user"]
    )

# ---------- BUY ----------
@app.route("/buy/<company>", methods=["POST"])
def buy(company):
    qty = int(request.form["quantity"])
    price, _ = get_latest_price(company)
    total = price * Decimal(qty)

    user = users_table.get_item(Key={"email": session["email"]}).get("Item")

    if total > user["balance"]:
        return "Insufficient balance"

    users_table.update_item(
        Key={"email": session["email"]},
        UpdateExpression="SET balance = balance - :amt",
        ExpressionAttributeValues={":amt": total}
    )

    portfolio_table.put_item(Item={
        "email": session["email"],
        "company": company,
        "quantity": qty,
        "buy_price": price
    })

    send_email_notification(
        "Stock Purchased",
        f"{session['user']} bought {qty} shares of {company} at {price}"
    )

    return redirect("/portfolio")

# ---------- SELL ----------
@app.route("/sell/<company>", methods=["POST"])
def sell(company):
    qty = int(request.form["quantity"])
    price, _ = get_latest_price(company)

    item = portfolio_table.get_item(
        Key={"email": session["email"], "company": company}
    ).get("Item")

    if not item or qty > item["quantity"]:
        return "Invalid quantity"

    total = price * Decimal(qty)

    users_table.update_item(
        Key={"email": session["email"]},
        UpdateExpression="SET balance = balance + :amt",
        ExpressionAttributeValues={":amt": total}
    )

    remaining = item["quantity"] - qty

    if remaining == 0:
        portfolio_table.delete_item(
            Key={"email": session["email"], "company": company}
        )
    else:
        portfolio_table.update_item(
            Key={"email": session["email"], "company": company},
            UpdateExpression="SET quantity = :q",
            ExpressionAttributeValues={":q": remaining}
        )

    send_email_notification(
        "Stock Sold",
        f"{session['user']} sold {qty} shares of {company} at {price}"
    )

    return redirect("/portfolio")

# ---------- PORTFOLIO ----------
@app.route("/portfolio")
def portfolio():
    response = portfolio_table.query(
        KeyConditionExpression=Key("email").eq(session["email"])
    )

    prices = {s["company"]: Decimal(str(s["price"])) for s in get_all_prices()}
    view = []

    for p in response.get("Items", []):
        cur = prices[p["company"]]
        pnl = (cur - p["buy_price"]) * Decimal(p["quantity"])

        view.append({
            "company": p["company"],
            "quantity": p["quantity"],
            "buy_price": float(p["buy_price"]),
            "current_price": float(cur),
            "pnl": float(round(pnl,2))
        })

    user = users_table.get_item(Key={"email": session["email"]}).get("Item")

    return render_template(
        "portfolio.html",
        portfolio=view,
        balance=float(user["balance"]),
        user=session["user"]
    )

# ---------- CHART FIX ----------
@app.route("/chart/<company>")
def chart(company):

    if company not in COMPANIES:
        return redirect("/dashboard")

    df = pd.read_csv(os.path.join(DATA_FOLDER, COMPANIES[company]))

    return render_template(
        "chart.html",
        company=company,
        data=df.tail(30).to_dict("records")
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
