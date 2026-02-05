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

# ---------- AWS (SAFE DEFAULT) ----------
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
users_table = dynamodb.Table("Users")
portfolio_table = dynamodb.Table("Portfolio")
watchlist_table = dynamodb.Table("Watchlist")

# ---------- HELPERS ----------
def get_price(company):
    df = pd.read_csv(os.path.join(DATA_FOLDER, COMPANIES[company]))
    return round(float(df.iloc[-1]["Close"]), 2)

def latest_prices():
    data = []
    for c in COMPANIES:
        df = pd.read_csv(os.path.join(DATA_FOLDER, COMPANIES[c]))
        row = df.iloc[-1]
        data.append({
            "company": c,
            "price": round(float(row["Close"]), 2),
            "date": row["Date"]
        })
    return data

# ---------- MAIN PAGES ----------
@app.route("/")
def main():
    return render_template("main.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

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

    stocks = latest_prices()
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

# ---------- BUY ----------
@app.route("/buy/<company>", methods=["POST"])
def buy(company):
    qty = int(request.form.get("quantity", 1))
    price = get_price(company)
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

# ---------- PORTFOLIO ----------
@app.route("/portfolio")
def portfolio():
    response = portfolio_table.query(
        KeyConditionExpression=Key("user").eq(session["email"])
    )

    prices = latest_prices()
    data = []

    for p in response.get("Items", []):
        cur = next(s["price"] for s in prices if s["company"] == p["company"])
        pnl = round((cur - p["buy_price"]) * p["quantity"], 2)
        data.append({
            **p,
            "current_price": cur,
            "pnl": pnl
        })

    user = users_table.get_item(Key={"email": session["email"]}).get("Item")
    return render_template("portfolio.html", portfolio=data, balance=user["balance"], user=session["user"])

# ---------- WATCHLIST ----------
@app.route("/add_to_watchlist/<company>")
def add_watchlist(company):
    watchlist_table.put_item(Item={
        "user": session["email"],
        "company": company
    })
    return redirect("/dashboard")

@app.route("/watchlist")
def watchlist():
    wl = watchlist_table.query(
        KeyConditionExpression=Key("user").eq(session["email"])
    ).get("Items", [])

    stocks = latest_prices()
    data = [s for s in stocks if s["company"] in [i["company"] for i in wl]]

    user = users_table.get_item(Key={"email": session["email"]}).get("Item")
    return render_template("watchlist.html", watchlist=data, balance=user["balance"], user=session["user"])

# ---------- CHART ----------
@app.route("/chart/<company>")
def chart(company):
    df = pd.read_csv(os.path.join(DATA_FOLDER, COMPANIES[company]))
    return render_template("chart.html", company=company, data=df.to_dict("records"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
