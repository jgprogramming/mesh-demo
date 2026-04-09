import altair as alt
import pandas as pd
import requests
import streamlit as st
from pyiceberg.catalog.rest import RestCatalog

CATALOG_URL = "https://lakekeeper.k8s-jagr.duckdns.org/catalog"
WAREHOUSE = "sources"
NAMESPACE = "smartphone"
TABLE_NAME = "data"

KEYCLOAK_TOKEN_URL = (
    "https://keycloak.k8s-jagr.duckdns.org/realms/platform/protocol/openid-connect/token"
)
CLIENT_ID = "platform-app"
USERNAME = "alice"
PASSWORD = "admin"

S3_ENDPOINT = "https://garage.k8s-jagr.duckdns.org"
S3_ACCESS_KEY_ID = "GK0123456789abcdef01234567"
S3_SECRET_ACCESS_KEY = (
    "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
)

SELECTED_FIELDS = (
    "brand_name",
    "model",
    "price",
    "rating",
    "has_5g",
    "has_nfc",
    "processor_brand",
    "battery_capacity",
    "ram_capacity",
    "internal_memory",
    "refresh_rate",
    "os",
)

NUMERIC_COLUMNS = (
    "price",
    "rating",
    "battery_capacity",
    "ram_capacity",
    "internal_memory",
    "refresh_rate",
)


@st.cache_data(ttl=3600)
def fetch_access_token() -> str:
    response = requests.post(
        KEYCLOAK_TOKEN_URL,
        data={
            "grant_type": "password",
            "client_id": CLIENT_ID,
            "username": USERNAME,
            "password": PASSWORD,
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["access_token"]


@st.cache_resource
def get_catalog(token: str) -> RestCatalog:
    return RestCatalog(
        name="demo_catalog",
        warehouse=WAREHOUSE,
        uri=CATALOG_URL,
        token=token,
        **{
            "s3.endpoint": S3_ENDPOINT,
            "s3.access-key-id": S3_ACCESS_KEY_ID,
            "s3.secret-access-key": S3_SECRET_ACCESS_KEY,
            "s3.path-style-access": "true",
        },
    )


@st.cache_data(ttl=600)
def load_data() -> pd.DataFrame:
    token = fetch_access_token()
    catalog = get_catalog(token)
    table = catalog.load_table(f"{NAMESPACE}.{TABLE_NAME}")
    df = table.scan(selected_fields=SELECTED_FIELDS).to_pandas()
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    filtered = df.copy()

    st.sidebar.header("Filters")
    brands = sorted(df["brand_name"].dropna().astype(str).unique().tolist())
    selected_brands = st.sidebar.multiselect("Brand", brands, default=brands)
    if selected_brands:
        filtered = filtered[filtered["brand_name"].astype(str).isin(selected_brands)]

    os_values = sorted(df["os"].dropna().astype(str).unique().tolist())
    selected_os = st.sidebar.multiselect("OS", os_values, default=os_values)
    if selected_os:
        filtered = filtered[filtered["os"].astype(str).isin(selected_os)]

    valid_prices = df["price"].dropna()
    if not valid_prices.empty:
        min_price = int(valid_prices.min())
        max_price = int(valid_prices.max())
        price_range = st.sidebar.slider(
            "Price range",
            min_value=min_price,
            max_value=max_price,
            value=(min_price, max_price),
            step=max(1, (max_price - min_price) // 100),
        )
        filtered = filtered[
            filtered["price"].between(price_range[0], price_range[1], inclusive="both")
        ]

    min_rating = st.sidebar.slider("Minimum rating", 0.0, 5.0, 0.0, 0.1)
    filtered = filtered[filtered["rating"].fillna(0.0) >= min_rating]

    only_5g = st.sidebar.checkbox("Only 5G phones", value=False)
    if only_5g:
        filtered = filtered[filtered["has_5g"] == True]

    only_nfc = st.sidebar.checkbox("Only NFC phones", value=False)
    if only_nfc:
        filtered = filtered[filtered["has_nfc"] == True]

    return filtered


st.set_page_config(page_title="Lakehouse Smartphone Dashboard", layout="wide")
st.title("Smartphone Lakehouse Dashboard")
st.caption("Interactive demo on Iceberg data from the lakehouse.")

if st.button("Refresh data"):
    st.cache_data.clear()
    st.cache_resource.clear()

try:
    raw_df = load_data()
except Exception as exc:
    st.error(f"Could not load lakehouse data: {exc}")
    st.stop()

if raw_df.empty:
    st.warning("No rows returned from smartphone.data.")
    st.stop()

df = apply_filters(raw_df)

if df.empty:
    st.warning("No data after applying filters.")
    st.stop()

col1, col2, col3 = st.columns(3)
col1.metric("Phones", f"{len(df):,}")
col2.metric("Average Price", f"{df['price'].mean():,.0f}")
col3.metric("Average Rating", f"{df['rating'].mean():.2f}")

st.subheader("Price vs Rating")
scatter_df = df.dropna(subset=["price", "rating"]).copy()
if scatter_df.empty:
    st.info("No rows with both price and rating for scatter plot.")
else:
    scatter = (
        alt.Chart(scatter_df)
        .mark_circle(size=90, opacity=0.7)
        .encode(
            x=alt.X("price:Q", title="Price"),
            y=alt.Y("rating:Q", title="Rating"),
            color=alt.Color("brand_name:N", title="Brand"),
            tooltip=[
                "brand_name:N",
                "model:N",
                alt.Tooltip("price:Q", format=",.0f"),
                alt.Tooltip("rating:Q", format=".2f"),
                "battery_capacity:Q",
                "ram_capacity:Q",
                "internal_memory:Q",
                "has_5g:N",
                "has_nfc:N",
            ],
        )
        .interactive()
    )
    st.altair_chart(scatter, use_container_width=True)

st.subheader("Average Price by Brand")
brand_stats = (
    df.groupby("brand_name", dropna=True)
    .agg(avg_price=("price", "mean"), avg_rating=("rating", "mean"), count=("model", "count"))
    .reset_index()
)
brand_stats = brand_stats[brand_stats["count"] > 0].sort_values("avg_price", ascending=False)
top_n = st.slider("Top brands to show", min_value=5, max_value=25, value=10, step=1)
metric = st.selectbox("Brand sort metric", ["avg_price", "avg_rating", "count"], index=0)
brand_stats = brand_stats.sort_values(metric, ascending=False).head(top_n)
bars = (
    alt.Chart(brand_stats)
    .mark_bar()
    .encode(
        x=alt.X("brand_name:N", sort="-y", title="Brand"),
        y=alt.Y(f"{metric}:Q", title=metric.replace("_", " ").title()),
        tooltip=[
            "brand_name:N",
            alt.Tooltip("avg_price:Q", format=",.0f"),
            alt.Tooltip("avg_rating:Q", format=".2f"),
            "count:Q",
        ],
    )
)
st.altair_chart(bars, use_container_width=True)

st.subheader("Price Distribution")
hist = (
    alt.Chart(df.dropna(subset=["price"]))
    .mark_bar()
    .encode(
        x=alt.X("price:Q", bin=alt.Bin(maxbins=30), title="Price bucket"),
        y=alt.Y("count():Q", title="Count"),
        tooltip=[alt.Tooltip("count():Q", title="Phones")],
    )
)
st.altair_chart(hist, use_container_width=True)

st.subheader("Filtered Data")
st.dataframe(
    df.sort_values(["price", "rating"], ascending=[False, False]).reset_index(drop=True),
    use_container_width=True,
)
