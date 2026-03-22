import base64
import json

import streamlit as st


def decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        return {}

    payload = parts[1]
    padding = "=" * (-len(payload) % 4)

    try:
        decoded = base64.urlsafe_b64decode(payload + padding)
        return json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return {}


headers = getattr(st.context, "headers", {})
token = headers.get("X-Forwarded-Access-Token", "")
payload = decode_jwt_payload(token)

username = payload.get("preferred_username", "User").capitalize()
roles = payload.get("realm_access", {}).get("roles", [])

st.title(f"Hello, {username}")

if roles:
    st.write("Your roles:")
    for role in roles:
        st.write(f"- {role}")
