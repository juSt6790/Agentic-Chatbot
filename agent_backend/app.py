"""Simple local launcher for the Flask application.

Run with:
    python3 run.py

This launcher starts the same Flask application that `app/cosi_app.py`
defines, so running `python3 run.py` behaves the same as
`python3 -m app.cosi_app`.
"""

import os
from app.cosi_app import app
from dotenv import load_dotenv
# Load environment variables
load_dotenv()

if __name__ == "__main__":
    # Keep defaults consistent with previous development behavior
    # app.run(host="0.0.0.0", port=8000, debug=True)
    ssl_cert = os.getenv("SSL_CERT_PATH")
    ssl_key = os.getenv("SSL_KEY_PATH")   
    ssl_ctx = (ssl_cert, ssl_key) if ssl_cert and ssl_key else None 
    app.run(host='0.0.0.0', 
            port=8000, 
            # ssl_context=('/app/mcp_gmail/app/fullchain.pem', '/app/mcp_gmail/app/privkey.pem'), 
            ssl_context=ssl_ctx,
            debug=True
            )
