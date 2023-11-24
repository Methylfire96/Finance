import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    rows = db.execute(
        "SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = ? GROUP BY symbol HAVING total_shares > 0",
        session["user_id"],
    )

    stocks = []
    for row in rows:
        stock_info = lookup(row["symbol"])
        stocks.append(
            {
                "symbol": row["symbol"],
                "name": stock_info["name"],
                "shares": row["total_shares"],
                "price": stock_info["price"],
                "total_value": row["total_shares"] * stock_info["price"],
            }
        )

    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
    # cash + total value of stocks
    grand_total = cash + sum(stock["total_value"] for stock in stocks)

    return render_template("index.html", stocks=stocks, cash=cash, grand_total=grand_total)
@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        timestamp = datetime.now()

        # empty field error
        if not symbol or not shares:
            return apology("must provide symbol and shares")

        # positiv number
        if not shares.isdigit() or int(shares) <= 0:
            return apology("shares must be a positive integer")

        stock_info = lookup(symbol)

        if not stock_info:
            return apology("invalid symbol")

        # total cost
        total_cost = int(shares) * stock_info["price"]

        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

        if cash < total_cost:
            return apology("insufficient funds")
        # insert
        db.execute(
            "INSERT INTO transactions (user_id, symbol, shares, price, transacted_at) VALUES (?, ?, ?, ?, ?)",
            session["user_id"],
            symbol,
            shares,
            stock_info["price"],
            timestamp,
        )

        # update
        db.execute(
            "UPDATE users SET cash = ? WHERE id = ?",
            cash - total_cost,
            session["user_id"],
        )
        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    rows = db.execute(
        "SELECT symbol, shares, price, transacted_at FROM transactions WHERE user_id = ? ORDER BY transacted_at DESC",
        session["user_id"],
    )

    transactions = []
    for row in rows:
        transactions.append(
            {
                "symbol": row["symbol"],
                "shares": row["shares"],
                "price": row["price"],
                "transacted_at": row["transacted_at"],
            }
        )

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        return redirect("/")

    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":

        symbol = request.form.get("symbol")

        # empty field error
        if not symbol:
            return apology("Must provide symbol", 400)

        stock_info = lookup(symbol)

        # invalid symbol
        if not stock_info:
            return apology("invalid symbol", 400)

        return render_template("quote_result.html", stock_info=stock_info)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # field free error
        if not username or not password or not confirmation:
            return apology("Must provide all blank fields", 400)

        # repaet password check
        if password != confirmation:
            return apology("Not matching password input")

        # existing user error
        existing_user = db.execute("SELECT * FROM users WHERE username = ?", username)
        if existing_user:
            return apology("username already exists", 400)

        hashed_password = generate_password_hash(password)

        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)",
            username,
            hashed_password,
        )
        return redirect("/login")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        timestamp = datetime.now()

        # empty field error
        if not symbol or not shares:
            return apology("must provide symbol and shares")

        # digit input
        if not shares.isdigit() or int(shares) <= 0:
            return apology("shares must be a positive integer")

        stock_info = lookup(symbol)

        if not stock_info:
            return apology("invalid symbol")

        user_shares = db.execute(
            "SELECT SUM(shares) as total_shares FROM transactions WHERE user_id = ? AND symbol = ?",
            session["user_id"], symbol)[0]["total_shares"]

        # amount check
        if user_shares < int(shares):
            return apology("insufficient shares")

        total_earnings = int(shares) * stock_info["price"]

        # Record the sell transaction in the database
        db.execute(
            "INSERT INTO transactions (user_id, symbol, shares, price, transacted_at) VALUES (?, ?, ?, ?, ?)",
            session["user_id"],
            symbol,
            -int(shares),
            stock_info["price"],
            timestamp,
        )

        # Update user's cash balance
        db.execute(
            "UPDATE users SET cash = cash + ? WHERE id = ?",
            total_earnings, session["user_id"]
        )
        return redirect("/")

    else:
        owned_stocks = db.execute(
            "SELECT symbol FROM transactions WHERE user_id = ? GROUP BY symbol HAVING SUM(shares) > 0",
            session["user_id"],
        )
        return render_template("sell.html", owned_stocks=owned_stocks)

@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    """Deposit money into user's account"""

    if request.method == "POST":
        amount = request.form.get("amount")

        # Ensure amount is a positive number
        if not amount or float(amount) <= 0:
            return apology("Invalid deposit amount")

        # Update user's cash balance
        db.execute(
            "UPDATE users SET cash = cash + ? WHERE id = ?",
            float(amount),
            session["user_id"],
        )
        return redirect("/")

    else:
        return render_template("deposit.html")
