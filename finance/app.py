
from flask import Flask, render_template, request, redirect, session, flash
from flask_session import Session
from werkzeug.security import generate_password_hash, check_password_hash
from cs50 import SQL
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
    # Get the user's cash balance
    user_cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

    # Get the user's stocks
    stocks = db.execute(
        "SELECT symbol, SUM(shares) as shares FROM transactions WHERE user_id = ? GROUP BY symbol HAVING shares > 0",
        session["user_id"]
    )

    # Calculate current prices and values
    portfolio = []
    total_value = user_cash
    for stock in stocks:
        symbol = stock["symbol"]
        shares = stock["shares"]
        stock_data = lookup(symbol)
        if stock_data:
            current_price = stock_data["price"]
            total_stock_value = current_price * shares
            total_value += total_stock_value
            portfolio.append({
                "symbol": symbol,
                "shares": shares,
                "price": usd(current_price),
                "total": usd(total_stock_value)
            })

    return render_template("index.html", portfolio=portfolio, cash=usd(user_cash), total=usd(total_value))

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        # Validate inputs
        if not symbol:
            flash("Must provide stock symbol.")
            return render_template("buy.html")
        if not shares.isdigit() or int(shares) <= 0:
            flash("Must provide a positive number of shares.")
            return render_template("buy.html")

        stock_data = lookup(symbol)
        if not stock_data:
            flash("Invalid stock symbol.")
            return render_template("buy.html")

        # Check if user has enough cash
        cost = stock_data["price"] * int(shares)
        user_cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
        if cost > user_cash:
            flash("Not enough funds.")
            return render_template("buy.html")

        # Insert transaction and update user's cash
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)",
                   session["user_id"], symbol, shares, stock_data["price"])
        db.execute("UPDATE users SET cash = cash - ? WHERE id = ?", cost, session["user_id"])

        flash("Bought successfully!")
        return redirect("/")
    return render_template("buy.html")



@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Query database for user's transaction history
    transactions = db.execute(
        "SELECT symbol, shares, price, time FROM transactions WHERE user_id = ? ORDER BY time DESC",
        session["user_id"]
    )

    # Format each transaction for display
    history = []
    for transaction in transactions:
        history.append({
            "symbol": transaction["symbol"],
            "shares": transaction["shares"],
            "price": usd(transaction["price"]),
            "total": usd(transaction["price"] * abs(transaction["shares"])),
            "type": "Buy" if transaction["shares"] > 0 else "Sell",
            "time": transaction["time"]
        })

    # Render history template
    return render_template("history.html", history=history)



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
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
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
    if request.method == "POST":
        symbol = request.form.get("symbol")
        if not symbol:
            flash("Stock symbol cannot be blank.")
            return render_template("quote.html")

        stock_data = lookup(symbol)
        if not stock_data:
            flash("Invalid stock symbol.")
            return render_template("quote.html")
        return render_template("quoted.html", stock=stock_data)
    return render_template("quote.html")



@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Validate inputs
        if not username:
            flash("Username is required.")
            return render_template("register.html")
        if not password:
            flash("Password is required.")
            return render_template("register.html")
        if password != confirmation:
            flash("Passwords must match.")
            return render_template("register.html")

        # Attempt to insert the new user into the database
        try:
            user_id = db.execute(
                "INSERT INTO users (username, hash) VALUES (?, ?)",
                username, generate_password_hash(password)
            )

            # Ensure the user_id was successfully created
            if user_id:
                session["user_id"] = user_id
                return redirect("/")
            else:
                flash("Registration failed. Please try again.")
                return render_template("register.html")

        except Exception as e:
            # Check if exception is due to duplicate username
            if "UNIQUE constraint failed" in str(e):
                flash("Username already taken.")
            else:
                flash("An error occurred during registration.")
            return render_template("register.html")

    # GET request: render the registration page
    return render_template("register.html")



@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        # Validate inputs
        if not symbol:
            flash("Must provide stock symbol.")
            return render_template("sell.html")
        if not shares.isdigit() or int(shares) <= 0:
            flash("Must provide a positive number of shares.")
            return render_template("sell.html")

        # Check if user has enough shares
        stock = db.execute("SELECT SUM(shares) as total_shares FROM transactions WHERE user_id = ? AND symbol = ? GROUP BY symbol",
                           session["user_id"], symbol)
        if not stock or stock[0]["total_shares"] < int(shares):
            flash("Not enough shares.")
            return render_template("sell.html")

        # Get current price and calculate sale value
        stock_data = lookup(symbol)
        if not stock_data:
            flash("Invalid stock symbol.")
            return render_template("sell.html")

        sale_value = stock_data["price"] * int(shares)

        # Update database
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)",
                   session["user_id"], symbol, -int(shares), stock_data["price"])
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", sale_value, session["user_id"])

        flash("Sold successfully!")
        return redirect("/")

    # Show user stocks for selling
    stocks = db.execute("SELECT symbol, SUM(shares) as shares FROM transactions WHERE user_id = ? GROUP BY symbol HAVING shares > 0",
                        session["user_id"])
    return render_template("sell.html", stocks=stocks)

if __name__ == '__main__':
    app.run(debug=True)
