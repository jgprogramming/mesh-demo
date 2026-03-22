import os

import streamlit as st


st.title("Environment Variables")
st.write(dict(sorted(os.environ.items())))
