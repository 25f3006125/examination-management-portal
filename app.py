import os 
from flask import Flask
from flask_wtf import CSRFProtect
from werkzeug.security import generate_password_hash
from models import db, User

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-only-chnage-me"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "emp.db")

db.init_app(app)

csrf = CSRFProtect(app)

def create_admin():
    if User.query.filter_by(role="admin").first() is None:
        admin = User(email="admin@emp.local", name="Administrator", role="admin", password_hash=generate_password_hash("admin123"))
        db.session.add(admin)
        db.session.commit()

with app.app_context():
    db.create_all()
    create_admin()

@app.route("/")
def home():
    return "Emp is running"

if __name__ == "__main__":
    app.run(debug=True)