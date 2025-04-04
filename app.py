from flask import Flask, render_template, request, redirect, url_for, session, make_response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import csv
from io import StringIO
import os

# -------------------------------
# App & Database Setup
# -------------------------------
app = Flask(__name__)
app.secret_key = os.urandom(24)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///elevate_pos.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# -------------------------------
# Models
# -------------------------------
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)

class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)



# -------------------------------
# Filters
# -------------------------------
@app.template_filter('datetime')
def format_datetime_filter(value):
    return value.strftime("%B %d, %Y – %I:%M %p") if value else ""

# -------------------------------
# Routes
# -------------------------------
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username == "admin" and password == "admin123":
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        else:
            error = "Invalid username or password"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    total_products = Product.query.count()
    total_stock = db.session.query(db.func.sum(Product.stock)).scalar() or 0
    total_sales_count = Sale.query.count()
    total_revenue = db.session.query(db.func.sum(Sale.total)).scalar() or 0.0
    return render_template("dashboard.html", total_products=total_products, total_stock=total_stock, total_sales_count=total_sales_count, total_revenue=round(total_revenue, 2))

@app.route("/inventory")
def inventory():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    products = Product.query.all()
    return render_template("inventory.html", products=products)

@app.route("/add-product", methods=["POST"])
def add_product():
    name = request.form.get("name")
    price = float(request.form.get("price"))
    stock = int(request.form.get("stock"))
    new_product = Product(name=name, price=price, stock=stock)
    db.session.add(new_product)
    db.session.commit()
    return redirect(url_for("inventory"))

@app.route("/edit-product/<int:product_id>", methods=["POST"])
def edit_product(product_id):
    product = Product.query.get(product_id)
    if product:
        product.name = request.form.get("name")
        product.price = float(request.form.get("price"))
        product.stock = int(request.form.get("stock"))
        db.session.commit()
    return redirect(url_for("inventory"))

@app.route("/delete-product/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    product = Product.query.get(product_id)
    if product:
        db.session.delete(product)
        db.session.commit()
    return redirect(url_for("inventory"))

@app.route("/sales")
def sales_page():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    products = Product.query.all()
    sales = Sale.query.order_by(Sale.timestamp.desc()).all()
    return render_template("sales.html", products=products, sales=sales)

@app.route("/submit-sale", methods=["POST"])
def submit_sale():
    product_id = int(request.form.get("product_id"))
    quantity = int(request.form.get("quantity"))
    product = Product.query.get(product_id)
    if product and quantity > 0 and product.stock >= quantity:
        total = round(product.price * quantity, 2)
        sale = Sale(product_name=product.name, quantity=quantity, price=product.price, total=total)
        db.session.add(sale)
        product.stock -= quantity
        db.session.commit()
    return redirect(url_for("sales_page"))

@app.route("/delete-sale/<int:sale_id>", methods=["POST"])
def delete_sale(sale_id):
    sale = Sale.query.get(sale_id)
    if sale:
        product = Product.query.filter_by(name=sale.product_name).first()
        if product:
            product.stock += sale.quantity
        db.session.delete(sale)
        db.session.commit()
    return redirect(url_for("sales_page"))

@app.route("/cart")
def view_cart():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    cart = session.get("cart", [])
    total = sum(item["price"] * item["quantity"] for item in cart)
    return render_template("cart.html", cart=cart, total=round(total, 2))


@app.route("/receipt/<int:sale_id>")
def view_receipt(sale_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    sale = Sale.query.get_or_404(sale_id)
    return render_template("receipt.html", sale=sale)

@app.route("/add-to-cart/<int:product_id>")
def add_to_cart(product_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    product = Product.query.get(product_id)
    if not product:
        return redirect(url_for("inventory"))

    cart = session.get("cart", [])
    for item in cart:
        if item["id"] == product.id:
            item["quantity"] += 1
            break
    else:
        cart.append({
            "id": product.id,
            "name": product.name,
            "price": product.price,
            "quantity": 1
        })

    session["cart"] = cart
    return redirect(url_for("inventory"))

@app.route("/submit-cart", methods=["POST"])
def submit_cart():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    cart = session.get("cart", [])
    if not cart:
        return redirect(url_for("view_cart"))

    for item in cart:
        product = Product.query.get(item["id"])
        if product and product.stock >= item["quantity"]:
            product.stock -= item["quantity"]
            sale = Sale(
                product_name=product.name,
                quantity=item["quantity"],
                price=product.price,
                total=round(product.price * item["quantity"], 2)
            )
            db.session.add(sale)

    db.session.commit()
    session["cart"] = []  # Clear cart
    return redirect(url_for("sales_page"))


@app.route("/export-sales")
def export_sales():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    sales = Sale.query.order_by(Sale.timestamp.desc()).all()
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(["ID", "Product", "Quantity", "Price", "Total", "Timestamp"])
    for sale in sales:
        writer.writerow([sale.id, sale.product_name, sale.quantity, sale.price, sale.total, sale.timestamp.strftime('%Y-%m-%d %H:%M:%S')])
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=sales.csv"
    output.headers["Content-type"] = "text/csv"
    return output

# -------------------------------
# Run the App
# -------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=4500)
