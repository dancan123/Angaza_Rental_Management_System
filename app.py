import os
from run import app, initialize_database

if __name__ == '__main__':
    initialize_database()
    port = int(os.environ.get('PORT', 5000))
    print(f" * Starting Angaza Rental Management System on http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)
