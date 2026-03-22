"""Quick test to verify the analysis service refactoring works end-to-end."""
import urllib.request, urllib.parse, json, sys

def test():
    # 1. Health check
    try:
        resp = urllib.request.urlopen('http://localhost:8000/health', timeout=10)
        data = json.loads(resp.read())
        print(f"Health: {json.dumps(data)}")
    except Exception as e:
        print(f"Health FAIL: {e}")
        sys.exit(1)

    # 2. Login
    try:
        login_data = json.dumps({
            'username': 'elliotalderson710@gmail.com',
            'password': 'Victor123!'
        }).encode()
        req = urllib.request.Request(
            'http://localhost:8000/auth/login',
            data=login_data,
            headers={'Content-Type': 'application/json'}
        )
        resp = urllib.request.urlopen(req, timeout=10)
        token_data = json.loads(resp.read())
        token = token_data.get('access_token', '')
        print(f"Login: OK (token len={len(token)})")
    except Exception as e:
        print(f"Login FAIL: {e}")
        sys.exit(1)

    # 3. Dashboard data
    try:
        req2 = urllib.request.Request(
            'http://localhost:8000/api/analysis/dashboard-data',
            headers={'Authorization': f'Bearer {token}'}
        )
        resp2 = urllib.request.urlopen(req2, timeout=30)
        dashboard = json.loads(resp2.read())
        print(f"Dashboard keys: {sorted(dashboard.keys())}")
        for k, v in sorted(dashboard.items()):
            if isinstance(v, list):
                print(f"  {k}: {len(v)} items")
            elif isinstance(v, dict):
                print(f"  {k}: dict({len(v)} keys)")
            else:
                print(f"  {k}: {v}")
    except Exception as e:
        print(f"Dashboard FAIL: {e}")

    # 4. Analysis status
    try:
        req3 = urllib.request.Request(
            'http://localhost:8000/api/analysis/status/70',
            headers={'Authorization': f'Bearer {token}'}
        )
        resp3 = urllib.request.urlopen(req3, timeout=10)
        status = json.loads(resp3.read())
        print(f"Analysis #70: status={status.get('status')} progress={status.get('progress_percent')}% step={status.get('current_step')}")
    except Exception as e:
        print(f"Analysis #70 status: {e}")

    print("ALL API TESTS DONE")

if __name__ == '__main__':
    test()
