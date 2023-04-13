import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from time import time, ctime
from collections import defaultdict

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

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


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
    if request.method == "GET":

        # Get amounts of shares for each company the user owns
        bought_shares = db.execute("SELECT company_symbol AS symbol, SUM(shares) AS shares FROM transactions WHERE user_id = ? AND transaction_type='purchase' GROUP BY symbol", session["user_id"])
        sold_shares = db.execute("SELECT company_symbol AS symbol, SUM(shares) AS shares FROM transactions WHERE user_id = ? AND transaction_type='sale' GROUP BY symbol", session["user_id"])
        held_shares = bought_shares
        held_shares = [{**stock, 'value': stock['shares'] * stock['prices']} for stock in held_shares or sold_shares]
        # Prepare a nice list of companies for which the user holds shares
        tickers = db.execute("SELECT DISTINCT company_symbol FROM transactions WHERE user_id = ?", session["user_id"])
        companies = []
        for index in range(len(tickers)):
            for key in tickers[index]:
                companies.append(tickers[index][key])
        companies = list(dict.fromkeys(companies))

        # Make lookup calls for each company the user owns stock for
        lookupRes = []
        for item in companies:
            tmp = lookup(item)
            lookupRes.append(tmp)

        # Create a list of dictionaries from the first list of dictionaries, with 'symbol' as the key
        result = [{**d1, **next((d2 for d2 in lookupRes if d2['symbol'] == d1['symbol']), {})} for d1 in shares]
        print(result)

        # Add the resulting computation to the respective lists of dictionaries
        result = [{**stock, 'value': stock['shares'] * stock['price']} for stock in result]

        # Get how much cash the user has from db
        cashDict = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        cash = cashDict[0]['cash']
        cashusd = usd(cash)
        total_value = sum(stock['value'] for stock in result)
        total_valueusd = usd(total_value)
        total_funds = usd(cash + total_value)
        context = {'cash': cashusd, 'total_value': total_valueusd, 'total_funds': total_funds}

        return render_template("index.html", results=result, context=context)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():

    # Get + check ticker symbol from user
    if request.method == "POST":
        txt = request.form.get("symbol")
        name = txt.upper()
        if not name or lookup(name) == None:
            return apology("Please input a valid IEX ticker-symbol.", 403)

        # Get + check requested shares from user
        shares = int(request.form.get("shares"))

        if shares < 0:
            return apology("Please input a positive integer representing the number of shares to purchase.", 403)

        trans_type = "purchase"
        purchaseTime = time()
        info = lookup(name)
        purchasePrice = int(info["price"])
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        cashSpent = purchasePrice * shares
        newCash = cash[0]["cash"] - cashSpent

        if newCash < 0:
            return apology("We're sorry, you don't have enough funds to make that purchase right now.", 403)

        else:
            db.execute("INSERT INTO transactions (transaction_time, transaction_type, company_symbol, shares, price, amount, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)", purchaseTime, trans_type, name, shares, purchasePrice, cashSpent, session["user_id"])
            db.execute("UPDATE users SET cash = ? WHERE id = ?", newCash, session["user_id"])
            return redirect("/")

    # Show buy.html when users go to the page.
    if request.method == "GET":
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    return apology("TODO")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("Must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("Must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
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
    # When a user visits the page, display quote.html providing forms for searching ticker symbols
    if request.method == "GET":
        return render_template("quote.html")

    # When a user submits to /quote via POST, render quoted.html with values from 'lookup'
    elif request.method == "POST":
        # Access data from /quote.html form
        symbol = request.form.get("symbol")

        # Check that it's valid (not empty or too long)
        if not symbol or len(symbol) > 4:
            return apology("Please enter a valid ticker symbol", 403)

        # Query IEX for ticker symbol's data and display to user on /quoted.html
        else:
            info = lookup(symbol)

            return render_template("quoted.html", info=info)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    if request.method == "POST":
        username = request.form.get("username")
        if not username:
            return apology("Please supply an appropriate username", 403)
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        if password and password == confirmation:
            hashedpass = generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)
            db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, hashedpass)
        else:
            return apology("Your request could not be completed. Ensure you entered a valid password and matching confirmation.", 403)
    return redirect("/register")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # When users visit the webpage, execute db query to populate select fields with ticker-symbols
    if request.method == "GET":
        shares = db.execute("SELECT company_symbol AS symbol FROM transactions WHERE user_id = ? GROUP BY symbol", session["user_id"])
        return render_template("sell.html", shares=shares)

    # When users send a POST request to /sell, sell their stock.
    if request.method == "POST":

        # Get the user's selected input.
        symbol = request.form.get("symbol")

        if not symbol:
            return apology("Please input a valid company's ticker-symbol.", 403)

        # Get which shares for each company the user owns
        shares = db.execute("SELECT company_symbol AS symbol FROM transactions WHERE UserID = ?", session["user_id"])

        # Get how many shares the user would like to sell
        soldShares = int(request.form.get("shares"))

        # Render an apology if the user inputs a non-positive number or chooses an invalid ticker-symbol
        if soldShares <= 0:
            return apology("Please input a positive integer equal to or lesser than the total shares you own for the company.", 403)
        else:

            # Check that the user has that many shares to sell
            currentShares = db.execute("SELECT company_symbol AS symbol, SUM(shares) AS sharesOwned FROM transactions WHERE user_id = ?", session["user_id"])
            for row in currentShares:
                if row['symbol'] == symbol:
                    if soldShares > row['sharesOwned']:
                        return apology("Sorry, you don't own that many shares in the selected company.", 403)
                    else:
                        # The user has the shares, sell by updating the purchases db
                        # TODO
                        # First, determine the user's new number of shares, then determine their new cash value based on
                        # the current price of the stock sold and how many shares the user sold. Update new cash balance.

                        # Get current price of share for symbol, isolate price, get users' cash, set new cash balance value
                        trans_type = "sale"
                        sale = lookup(symbol)
                        salePrice = int(sale["price"])
                        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
                        cashGained = salePrice * soldShares
                        newCash = cash[0]["cash"] + cashGained
                        db.execute("UPDATE users SET cash = ? WHERE id = ?", newCash, session["user_id"])

                        # Get time, update purchases table with sale information
                        saleTime = time()
                        newShares = row['sharesOwned'] - soldShares
                        db.execute("UPDATE transactions SET shares = ?, transaction_time = ?, transaction_type = ? WHERE company_symbol = ? AND user_id = ?", soldShares, saleTime, trans_type, symbol, session["user_id"])
                        return redirect("/")
                else:
                    return apology("It doesn't look like you own stock in that company, sorry.", 403)