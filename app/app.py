import os

import streamlit as st


st.title("Request Headers")

headers = getattr(st.context, "headers", {})

for key, value in sorted(headers.items()):
    st.write(f"{key}: {value}")

st.title("Environment Variables")

for key, value in sorted(os.environ.items()):
    st.write(f"{key}: {value}")
