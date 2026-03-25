import requests
from TM1py import TM1Service
from TM1py.Services.RestService import RestService
from config import TM1_CONFIG

def _patched_set_version(self):
    self._version = "12.5.5"

def _patched_construct_root(self):
    cfg = TM1_CONFIG
    base = f"http://{cfg['address']}:{cfg['port']}/tm1/api/v1/Databases('{cfg['database']}')"
    return (base, f"{base}/Configuration/ProductVersion/$value")

RestService.set_version = _patched_set_version
RestService._construct_service_and_auth_root = _patched_construct_root

def get_token():
    cfg = TM1_CONFIG
    auth = requests.post(
        f"http://{cfg['address']}:{cfg['port']}/tm1/auth/v1/session",
        auth=(cfg['client_id'], cfg['client_secret']),
        headers={'Content-Type': 'application/json'},
        json={'User': cfg['user']}
    )
    token = auth.cookies.get('TM1SessionId')
    if not token:
        raise ConnectionError(f"Failed to get TM1SessionId — status: {auth.status_code}")
    return token

def get_tm1_service() -> TM1Service:
    cfg = TM1_CONFIG
    token = get_token()
    return TM1Service(
        base_url=f"http://{cfg['address']}:{cfg['port']}/tm1/api/v1/Databases('{cfg['database']}')",
        session_id=token,
        ssl=False,
        verify=False,
    )

if __name__ == '__main__':
    print("Testing connection...")
    with get_tm1_service() as tm1:
        print(f"Connected ✓  version: {tm1.server.get_product_version()}")
