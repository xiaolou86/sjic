from app import create_app
from app.extensions import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    try:
        db.session.execute(text('ALTER TABLE algorithms ADD COLUMN model_id INTEGER'))
        print("Added model_id to algorithms.")
    except Exception as e:
        print("model_id error:", e)

    try:
        db.session.execute(text('ALTER TABLE algorithms ADD COLUMN labels JSON'))
        print("Added labels to algorithms.")
    except Exception as e:
        print("labels error:", e)

    db.session.commit()
    print("MySQL Database patched successfully!")
