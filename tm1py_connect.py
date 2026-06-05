import requests
from TM1py import TM1Service
from TM1py.Services.RestService import RestService
from config import TM1_CONFIG


def get_token():
    cfg = TM1_CONFIG
    auth = requests.post(
        f"http://{cfg['address']}:{cfg['port']}/tm1/auth/v1/session",
        auth=(cfg["client_id"], cfg["client_secret"]),
        headers={"Content-Type": "application/json"},
        json={"User": cfg["user"]},
    )
    token = auth.cookies.get("TM1SessionId")
    if not token:
        raise ConnectionError(
            f"Failed to get TM1SessionId — status: {auth.status_code}"
        )
    return token


def _patch_for_v12():
    def _patched_set_version(self):
        self._version = "12.5.5"

    def _patched_construct_root(self):
        cfg = TM1_CONFIG
        base = f"http://{cfg['address']}:{cfg['port']}/tm1/api/v1/Databases('{cfg['database']}')"
        return (base, f"{base}/Configuration/ProductVersion/$value")

    RestService.set_version = _patched_set_version
    RestService._construct_service_and_auth_root = _patched_construct_root


def _get_v12_service():
    _patch_for_v12()
    cfg = TM1_CONFIG
    token = get_token()
    return TM1Service(
        base_url=f"http://{cfg['address']}:{cfg['port']}/tm1/api/v1/Databases('{cfg['database']}')",
        session_id=token,
        ssl=False,
        verify=False,
    )


def _get_v11_service():
    cfg = TM1_CONFIG
    return TM1Service(
        address=cfg["address"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        ssl=False,
    )


def get_tm1_service() -> TM1Service:
    server_type = TM1_CONFIG.get("server_type", "v12_onprem")
    if server_type == "v11_onprem":
        return _get_v11_service()
    return _get_v12_service()


if __name__ == "__main__":
    print("Testing connection...")
    with get_tm1_service() as tm1:
        print(f"Connected ✓  version: {tm1.server.get_product_version()}")
