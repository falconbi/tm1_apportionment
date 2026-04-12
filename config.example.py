"""
config.example.py
Copy this file to config.py and fill in your environment details.
config.py is excluded from git — never commit real credentials.

    cp config.example.py config.py
"""

TM1_CONFIG = {
    'address':       '192.168.1.1',         # TM1 server IP or hostname
    'port':          4444,                   # TM1 REST API port
    'database':      'YourDatabaseName',     # TM1 database/server name
    'client_id':     'your_client_id',       # Authentik / OAuth2 client ID
    'client_secret': 'your_client_secret',   # Authentik / OAuth2 client secret
    'user':          'your_username',        # TM1 admin user
}

# ── CST model constants ───────────────────────────────────────────────────────
# Update these to match your GBL Account hierarchy before building the model.
# These consolidation names are substituted into TM1 rules and views at deploy time.

CST_CONFIG = {
    'overhead_consolidation': 'TOTAL OVERHEAD',      # consolidation of indirect/overhead accounts
    'direct_consolidation':   'TOTAL DIRECT COSTS',  # consolidation of direct cost accounts
}
