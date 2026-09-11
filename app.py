import streamlit as st
import pandas as pd
import zipfile
import io
from sqlalchemy import create_engine
import plotly.express as px

st.set_page_config(layout="wide")

# --- Database Settings Sidebar ---
st.sidebar.header("Database Configuration")
st.sidebar.write("Configure connection to PostgreSQL:")
db_user = st.sidebar.text_input("Username", "postgres")
db_pass = st.sidebar.text_input("Password", "postgres", type="password")
db_host = st.sidebar.text_input("Host", "localhost")
db_port = st.sidebar.text_input("Port", "5432")
db_name = st.sidebar.text_input("Database Name", "webapp")

def send_to_postgresql(df, table_name):
    """Send dataframe to PostgreSQL database."""
    db_url = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    try:
        engine = create_engine(db_url)
        df.to_sql(table_name, engine, if_exists='replace', index=False)
        return True, None
    except Exception as e:
        return False, str(e)

st.title("Dialog Page Data")

st.header("Upload Files")
col1, col2 = st.columns(2)

with col1:
    uploaded_zip = st.file_uploader("Upload 'webapp' zip file (Page Data)", type="zip")

with col2:
    uploaded_post = st.file_uploader("Upload 'Post_Data' zip file (Post Data)", type="zip")

st.divider()

col_page, col_post = st.columns(2)

def clean_columns(df):
    """Make headers lowercase and replace spaces with underscores."""
    df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
    return df

def enforce_page_data_types(df):
    """Enforce specific data types for Page Data (webapp.zip) as requested."""
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'], errors='coerce')

    string_cols = ['profile', 'network', 'profile-id', 'link', 'external_links', 'image_link', 'source_file']
    for c in string_cols:
        if c in df.columns:
            df[c] = df[c].astype(str)

    pct_cols = [c for c in df.columns if any(x in c for x in ['post_interaction_rate', 'page_performance_index', 'follower_growth', 'engagement', 'conversations'])]
    dec_cols = ['comments_per_post', 'likes_per_post', 'shares/reposts/quotes_per_post']
    curr_cols = ['ad-value_(usd)']

    def clean_curr(x):
        x = str(x).lower().replace('$', '').replace(',', '').strip()
        try:
            if 'k' in x: return float(x.replace('k', '')) * 1000
            if 'm' in x: return float(x.replace('m', '')) * 1000000
            return float(x)
        except:
            return 0.0

    for c in curr_cols:
        if c in df.columns:
            df[c] = df[c].apply(clean_curr)

    float_cols = pct_cols + [c for c in dec_cols if c in df.columns]
    for c in float_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)

    skip_cols = set(['date'] + string_cols + pct_cols + dec_cols + curr_cols)
    int_cols = [c for c in df.columns if c not in skip_cols]

    for c in int_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).round().astype(int)

    return df

# --- Process Page Data (Zip File) ---
with col_page:
    if uploaded_zip is not None:
        st.subheader("Page Data (From Zip)")
        with zipfile.ZipFile(uploaded_zip, "r") as z:
            all_dataframes = []

            for file_name in z.namelist():
                # Skip hidden files and macOS '__MACOSX' folder
                if file_name.endswith('.xlsx') and not file_name.split('/')[-1].startswith('~') and '__MACOSX' not in file_name:
                    with z.open(file_name) as f:
                        try:
                            # 1. Read the date from the top header (row index 1, col index 5)
                            header_df = pd.read_excel(f, header=None, nrows=2, engine='openpyxl')
                            date_val = str(header_df.iloc[1, 5])
                            if " - " in date_val:
                                parts = date_val.split(" - ")
                                if parts[0] == parts[1]:
                                    date_val = parts[0]

                            # 2. Reset file pointer to read the main table
                            f.seek(0)

                            df = pd.read_excel(f, header=4, engine='openpyxl')
                            if 'Unnamed: 0' in df.columns:
                                df = df.drop(columns=['Unnamed: 0'])

                            # 3. Insert the Date as the first column
                            df.insert(0, 'Date', date_val)

                            df['Source_File'] = file_name.split('/')[-1]

                            # Clean the column headers
                            df = clean_columns(df)

                            # Replace all isolated '-' values with 0
                            df = df.replace('-', 0)

                            all_dataframes.append(df)
                        except Exception as e:
                            st.error(f"Error processing {file_name}: {e}")

            if all_dataframes:
                combined_df = pd.concat(all_dataframes, ignore_index=True)

                # Enforce data types BEFORE display and download
                combined_df = enforce_page_data_types(combined_df)

                st.success(f"Combined {len(all_dataframes)} Excel files successfully.")
                st.write(f"**Total rows:** {len(combined_df)}")
                st.dataframe(combined_df.head(10), use_container_width=True)

                # --- Visualizations ---
                st.markdown("### Page Data Visualizations")

                # 1. Bar Chart
                if 'profile' in combined_df.columns and 'follower' in combined_df.columns:
                    follower_df = combined_df.groupby('profile')['follower'].max().reset_index()
                    fig_bar = px.bar(follower_df, x='profile', y='follower', 
                                     title='Maximum Followers by Profile', 
                                     labels={'follower': 'Followers', 'profile': 'Profile'},
                                     color='profile')
                    st.plotly_chart(fig_bar, use_container_width=True)

                # 2. Pie Chart
                if 'network' in combined_df.columns and 'number_of_posts' in combined_df.columns:
                    posts_df = combined_df.groupby('network')['number_of_posts'].sum().reset_index()
                    fig_pie = px.pie(posts_df, names='network', values='number_of_posts', 
                                     title='Total Posts by Network',
                                     color='network')
                    st.plotly_chart(fig_pie, use_container_width=True)

                buffer_page = io.BytesIO()
                with pd.ExcelWriter(buffer_page, engine='openpyxl') as writer:
                    combined_df.to_excel(writer, index=False)

                st.download_button(
                    label="Download Cleaned Page Data",
                    data=buffer_page.getvalue(),
                    file_name="cleaned_page_data.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="btn_page"
                )

                if st.button("Send to PostgreSQL", key="db_page"):
                    with st.spinner("Connecting to PostgreSQL database..."):
                        success, error_msg = send_to_postgresql(combined_df, "page_data")
                        if success:
                            st.success("Successfully sent Page Data to the 'page_data' table in 'webapp' database!")
                        else:
                            st.error(f"Failed to connect or upload. Please check sidebar credentials.\nError: {error_msg}")
            else:
                st.warning("No valid .xlsx files found in the uploaded zip.")

# --- Process Post Data (Zip File) ---
with col_post:
    if uploaded_post is not None:
        st.subheader("Post Data (From Zip)")
        with zipfile.ZipFile(uploaded_post, "r") as z:
            all_post_dataframes = []

            for file_name in z.namelist():
                if file_name.endswith('.xlsx') and not file_name.split('/')[-1].startswith('~') and '__MACOSX' not in file_name:
                    with z.open(file_name) as f:
                        try:
                            # Post Data files already contain the Date column
                            df = pd.read_excel(f, header=4, engine='openpyxl')
                            if 'Unnamed: 0' in df.columns:
                                df = df.drop(columns=['Unnamed: 0'])

                            df['Source_File'] = file_name.split('/')[-1]

                            # Clean the column headers
                            df = clean_columns(df)

                            # Replace all isolated '-' values with 0
                            df = df.replace('-', 0)

                            all_post_dataframes.append(df)
                        except Exception as e:
                            st.error(f"Error processing {file_name}: {e}")

            if all_post_dataframes:
                combined_post_df = pd.concat(all_post_dataframes, ignore_index=True)

                st.success(f"Combined {len(all_post_dataframes)} Excel files successfully.")
                st.write(f"**Total rows:** {len(combined_post_df)}")
                st.dataframe(combined_post_df.head(10), use_container_width=True)

                buffer_post = io.BytesIO()
                with pd.ExcelWriter(buffer_post, engine='openpyxl') as writer:
                    combined_post_df.to_excel(writer, index=False)

                st.download_button(
                    label="Download Cleaned Post Data",
                    data=buffer_post.getvalue(),
                    file_name="cleaned_post_data.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="btn_post"
                )

                if st.button("Send to PostgreSQL", key="db_post"):
                    with st.spinner("Connecting to PostgreSQL database..."):
                        success, error_msg = send_to_postgresql(combined_post_df, "post_data")
                        if success:
                            st.success("Successfully sent Post Data to the 'post_data' table in 'webapp' database!")
                        else:
                            st.error(f"Failed to connect or upload. Please check sidebar credentials.\nError: {error_msg}")
            else:
                st.warning("No valid .xlsx files found in the uploaded zip.")

