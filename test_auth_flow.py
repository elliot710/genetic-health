#!/usr/bin/env python3
"""
Test script to simulate the frontend's authentication flow
"""
import asyncio
import aiohttp
import json

async def test_auth_flow():
    """Test the authentication and progress endpoint"""
    async with aiohttp.ClientSession() as session:
        # First, try to get a token (simulate login)
        login_data = {
            "username": "victoriatco",  # Replace with actual username
            "password": "Victor123!"     # Replace with actual password
        }
        
        try:
            # Test login endpoint
            async with session.post(
                "http://localhost:8000/auth/login",
                json=login_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    auth_data = await response.json()
                    token = auth_data.get("access_token")
                    print(f"✅ Login successful, token: {token[:20]}...")
                    
                    # Test progress endpoint with token
                    headers = {
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    }
                    
                    async with session.get(
                        "http://localhost:8000/analyze/progress/25",
                        headers=headers
                    ) as progress_response:
                        if progress_response.status == 200:
                            progress_data = await progress_response.json()
                            print(f"✅ Progress endpoint works: {json.dumps(progress_data, indent=2)}")
                        else:
                            error_text = await progress_response.text()
                            print(f"❌ Progress endpoint failed ({progress_response.status}): {error_text}")
                else:
                    error_text = await response.text()
                    print(f"❌ Login failed ({response.status}): {error_text}")
                    
        except Exception as e:
            print(f"❌ Connection error: {e}")

if __name__ == "__main__":
    asyncio.run(test_auth_flow())