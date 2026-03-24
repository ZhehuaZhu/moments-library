from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate(compare_type=True)
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please sign in with the admin account."
csrf = CSRFProtect()
