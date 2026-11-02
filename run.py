import os
from app import create_app
from app.extensions import db

app = create_app(os.environ.get('FLASK_CONFIG', 'default'))

@app.shell_context_processor
def make_shell_context():
    from app import models
    return dict(db=db, **{name: getattr(models, name) for name in models.__all__})

def initialize_database():
    """Create all tables and seed initial data."""
    with app.app_context():
        db.create_all()
        from app.routes.auth_bp import seed_initial_data
        seed_initial_data()
        print("[Startup] Database initialized and ready.")

if __name__ == '__main__':
    initialize_database()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
