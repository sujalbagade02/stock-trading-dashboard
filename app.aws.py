from flask import Flask, render_template, request, redirect, url_for, session
import pandas as pd
import os
import random
import boto3
from werkzeug.security import generate_password_hash, check_password_hash
from boto3.dynamodb.conditions import Key

# ---------------- APP SETUP ---------------- #

app = Flask(__name__)
application = app  # AWS compatibility

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

# ---------------- AWS ---------------- #

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
sns = boto3.client("sns", region_name="us-east-1")

users_table = dynamodb.Table("Users")
portfolio_table = dynamodb.Table("Portfolio")
watchlist_table = dynamodb.Table("Watchlist")

SNS_TOPIC_ARN = os.environ.get("arn:aws:sns:us-east-1:741448926436:aws_topicc")  # set on EC2

# ---------------- HELPERS ---------------- #

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
    response = users_table.get_item(Key={"email": session["email"]})
    return response.get("Item")

def send_notification(message):
    if SNS_TOPIC_ARN:
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=message,
            Subject="Stock Dashboard Alert"
        )

# ---------------- ROUTES ---------------- #

@app.route("/")
def main():
    return render_template("main.html")

@app.route("/about", endpoint="about")
def about_page():
    return render_template("about.html")


@app.route("/contact")
def contact():  
    return render_template("contact.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        users_table.put_item(
            Item={
                "email": request.form["email"],
                "name": request.form["name"],
                "password": generate_password_hash(request.form["password"]),
                "balance": 100000
            }
        )
        return redirect(url_for("login"))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        response = users_table.get_item(Key={"email": request.form["email"]})
        user = response.get("Item")

        if user and check_password_hash(user["password"], request.form["password"]):
            session["user"] = user["name"]
            session["email"] = user["email"]
            return redirect(url_for("dashboard"))

        return "Invalid login"
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))

    stocks = load_latest_prices()
    user = get_user()

    response = watchlist_table.query(
        KeyConditionExpression=Key("user").eq(session["email"])
    )

    watchlist = [i["company"] for i in response.get("Items", [])]

    return render_template(
        "dashboard.html",
        stocks=stocks,
        user=session["user"],
        balance=user["balance"],
        user_watchlist=watchlist
    )

# ---------------- BUY ---------------- #

@app.route("/buy/<company>", methods=["POST"])
def buy_stock(company):
    qty = int(request.form["quantity"])
    stock = next(s for s in load_latest_prices() if s["company"] == company)

    total_cost = qty * stock["price"]
    user = get_user()

    if user["balance"] < total_cost:
        return "Insufficient balance"

    users_table.update_item(
        Key={"email": session["email"]},
        UpdateExpression="SET balance = balance - :amt",
        ExpressionAttributeValues={":amt": total_cost}
    )

    portfolio_table.put_item(
        Item={
            "user": session["email"],
            "company": company,
            "quantity": qty,
            "buy_price": stock["price"]
        }
    )

    send_notification(f"BUY: {qty} {company} @ {stock['price']}")
    return redirect("/portfolio")

# ---------------- SELL ---------------- #

@app.route("/sell/<company>", methods=["POST"])
def sell_stock(company):
    qty = int(request.form["quantity"])
    sell_price = float(request.form["sell_price"])

    response = portfolio_table.get_item(
        Key={"user": session["email"], "company": company}
    )
    holding = response.get("Item")

    if not holding or holding["quantity"] < qty:
        return "Not enough quantity"

    users_table.update_item(
        Key={"email": session["email"]},
        UpdateExpression="SET balance = balance + :amt",
        ExpressionAttributeValues={":amt": qty * sell_price}
    )

    remaining = holding["quantity"] - qty

    if remaining == 0:
        portfolio_table.delete_item(
            Key={"user": session["email"], "company": company}
        )
    else:
        portfolio_table.update_item(
            Key={"user": session["email"], "company": company},
            UpdateExpression="SET quantity = :q",
            ExpressionAttributeValues={":q": remaining}
        )

    send_notification(f"SELL: {qty} {company} @ {sell_price}")
    return redirect("/portfolio")

@app.route("/portfolio")
def portfolio_page():
    user = get_user()

    response = portfolio_table.query(
        KeyConditionExpression=Key("user").eq(session["email"])
    )

    prices = load_latest_prices()
    portfolio_view = []

    for p in response.get("Items", []):
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
        user=session["user"]
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
