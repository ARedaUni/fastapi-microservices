#!/bin/bash

# Get JWT token from users service
echo "Getting token from users service..."
RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/login/" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@admin.com&password=password")

TOKEN=$(echo $RESPONSE | jq -r '.access_token')
OWNER="1"  # sub claim from the JWT

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
  echo "❌ Failed to get token. Make sure users service is running on port 8000"
  echo "Response: $RESPONSE"
  exit 1
fi

echo ""
echo "✅ Got token!"
echo ""
echo "1. Open canvas.html in your browser:"
echo "   file:///Users/jimmy/Desktop/personal_engineering/fastapi-microservices/canvas.html"
echo ""
echo "2. Run this in the browser console (F12):"
echo ""
echo "localStorage.setItem('jwt_token', '$TOKEN')"
echo "localStorage.setItem('jwt_owner', '$OWNER')"
echo "location.reload()"
echo ""
echo "---"
echo "Or paste this one-liner:"
echo "localStorage.setItem('jwt_token', '$TOKEN'); localStorage.setItem('jwt_owner', '$OWNER'); location.reload()"
