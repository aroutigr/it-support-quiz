import streamlit as st

st.title("Aiven Database Connection Test")

# 1. Initialize the connection using the credentials from secrets.toml
# Streamlit automatically finds the [connections.aiven_db] block!
try:
    conn = st.connection("aiven_db", type="sql")
    st.success("Successfully connected to Aiven MySQL!")
    
    # 2. Run a simple query to prove it works
    # This queries standard MySQL system variables
    df = conn.query("SELECT version();", ttl=600)
    
    st.write("Database Version:")
    st.dataframe(df)

except Exception as e:
    st.error(f"Failed to connect: {e}")