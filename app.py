#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import streamlit as st
import mysql.connector
from mysql.connector import Error
import hashlib
import datetime
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from fuzzywuzzy import process
from fuzzywuzzy import fuzz
from datetime import date
import os
import logging

# def connect_db():
#     try:
#         return mysql.connector.connect(
#             host=os.environ.get("DB_HOST"),
#             user=os.environ.get("DB_USER"),
#             password=os.environ.get("DB_PASSWORD"),
#             database="applogin",
#             port=3306,
#             ssl_ca="DigiCertGlobalRootCA.crt.pem",
#             ssl_disabled=False
#         )
#     except Error as e:
#         print("Error while connecting to MySQL:", e)
#         return None

# Connect to your MySQL database 
def connect_db():
    try:
#         return mysql.connector.connect.secrets.toml(**st.secrets.db_credentials)
        return mysql.connector.connect(**st.secrets.database_config)
#         return mysql.connector.connect.(**st.secrets.toml.db_credentials)
    except Error as e:
        st.error(f"Error while connecting to MySQL: {e}")  # Display the error message on the Streamlit app
        return None
    
# def connect_db():
#     try:
#         return mysql.connector.connect(**st.secrets.db_credentials)
# #         return mysql.connector.connect(**st.secrets["connections"]["mysql"])

#     except Error as e:
#         st.error(f"Error while connecting to MySQL: {e}")  # Display the error message on the Streamlit app
#         return None

# class DatabaseLogHandler(logging.Handler):
#     def emit(self, record):
#         db_connection = connect_db()
#         if db_connection is not None:
#             try:
#                 cursor = db_connection.cursor()
#                 log_entry = self.format(record)
#                 cursor.execute("INSERT INTO app_logs (log_level, log_message) VALUES (%s, %s)",
#                                (record.levelname, log_entry))
#                 db_connection.commit()
#                 cursor.close()
#             except mysql.connector.Error as e:
#                 print(f"Error while logging to database: {e}")
#             finally:
#                 db_connection.close()
                
# # Set up logging
# logger = logging.getLogger('my_application_logger')
# logger.setLevel(logging.INFO)

# # Create and add the database log handler
# db_handler = DatabaseLogHandler()
# logger.addHandler(db_handler)

# try:
#     # Some code that might raise an exception
#     # Example: 
#     # result = potentially_failing_operation()
#     pass  # Use 'pass' if there's no actual code to execute yet
# except Exception as e:
#     logger.error(f"An error occurred: {e}")


# # After completing a significant task
# logger.info("Completed data processing step")

# Far more compact version!
# my_db.connect(**st.secrets.connections.mysql)

# Connect to your MySQL database 
# def connect_db():
#     try:
#         return mysql.connector.connect(**st.secrets["connections.mysql"])
#     except Error as e:
#         print("Error while connecting to MySQL:", e)
#         return None


# def connect_db():
#     try:
#         return my_db.connect(**st.secrets.connections.mysql)
#     except Error as e:
#         print("Error while connecting to MySQL:", e)
#         return None


# #  Connect to your MySQL database
# def connect_db():
#     try:
#         connection = mysql.connector.connect(
#             host="pmsanalytics.mysql.database.azure.com",
#             user="chitemerere",
#             password="ruvimboML55AMG%",
#             database="applogin",
#             port=3306,
#             ssl_ca="DigiCertGlobalRootCA.crt.pem",
#             ssl_disabled=False
#         )
#         logging.info("Successfully connected to MySQL database")
#         return connection
#     except Error as e:
#         logging.error("Error while connecting to MySQL: %s", e)
#         return None


# # Connect to your MySQL database
# def connect_db():
#     try:
#         return mysql.connector.connect(
#             host="pmsanalytics.mysql.database.azure.com",
#             user="chitemerere",
#             password="ruvimboML55AMG%",
#             database="applogin",
#             port=3306,
#             ssl_ca="DigiCertGlobalRootCA.crt.pem",
#             ssl_disabled=False
#         )
#     except Error as e:
#         print("Error while connecting to MySQL:", e)
#         return None

# Function to hash passwords
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Function to authenticate user
def authenticate_user(username, password, admin_only=False):
    try:
        db = connect_db()
        if db is None:
            raise Exception("Database connection could not be established")
        cursor = db.cursor()
        hashed_password = hash_password(password)
        cursor.execute("""
            SELECT expiry_date, role FROM users
            WHERE username = %s AND password = %s
        """, (username, hashed_password))
        result = cursor.fetchone()
        cursor.close()
        db.close()
        if result:
            expiry_date, role = result
            if date.today() <= expiry_date and (not admin_only or role == "admin"):
                return True
        return False
    except Exception as e:
        print("Error in authenticate_user:", e)
        return False

# Function to create a new user (admin only)
def create_user(admin_username, admin_password, new_username, new_password, new_expiry_date):
    try:
        if authenticate_user(admin_username, admin_password, admin_only=True):
            db = connect_db()
            cursor = db.cursor()
            hashed_password = hash_password(new_password)
            cursor.execute("""
                INSERT INTO users (username, password, expiry_date, role)
                VALUES (%s, %s, %s, 'user')
            """, (new_username, hashed_password, new_expiry_date))
            db.commit()
            cursor.close()
            db.close()
            return True
        else:
            print("Admin authentication failed in create_user")
            return False
    except Exception as e:
        print("Error in create_user:", e)
        return False
 
# Streamlit UI for creating new user
def create_new_user_ui(admin_username, admin_password):
    with st.form("Create User"):
        new_username = st.text_input("New User Username")
        new_password = st.text_input("New User Password", type="password")
        new_expiry_date = st.date_input("Expiry Date")
        create_user_button = st.form_submit_button("Create User")

        if create_user_button:
            if create_user(admin_username, admin_password, new_username, new_password, new_expiry_date):
                st.success("User created successfully")
            else:
                st.error("Failed to create user")
                
def update_user_password(username, new_password):
    try:
        db = connect_db()
        if db is None:
            raise Exception("Failed to connect to the database")

        cursor = db.cursor()

        # Check if the user exists
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        if cursor.fetchone() is None:
            raise Exception("No such user found")

        # Hash the new password
        hashed_password = hash_password(new_password)

        # Update the user's password
        update_query = "UPDATE users SET password = %s WHERE username = %s"
        cursor.execute(update_query, (hashed_password, username))

        # Commit the changes
        db.commit()

        if cursor.rowcount == 0:
            raise Exception("Password update failed")

        cursor.close()
        db.close()
        return True

    except Exception as e:
        print(f"Error in update_user_password: {e}")
        return False
                 
def safe_load_csv(uploaded_file):
    if uploaded_file is not None and uploaded_file.size > 0:
        return pd.read_csv(uploaded_file)
    else:
        return None

# Function to load data
@st.cache_data

def load_data(uploaded_file):
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            df['Generic Name'] = df['Generic Name'].str.upper().str.strip()
            return df
        except pd.errors.EmptyDataError:
            st.error('The uploaded file is empty or not in a valid CSV format.')
            return pd.DataFrame()
    return pd.DataFrame()

# Function to extract ATC level codes for Human Medicine
def extract_atc_levels_human(atc_code):
    return (atc_code[:1], atc_code[:3], atc_code[:4], atc_code[:5])

# Function to extract ATC level codes for Veterinary Medicine
def extract_atc_levels_veterinary(atc_code):
    return (atc_code[:2], atc_code[:4], atc_code[:5], atc_code[:6])

# Function to convert DataFrame to CSV
def convert_df_to_csv(df):
    if df is not None:
        return df.to_csv(index=False).encode('utf-8')
    else:
        # Handle the case where df is None, e.g., return an empty string or None
        return None

# Calculation Functions with Corrected Factors and Rounding
def calculate_prevalent_population(population, prevalence):
    return round(population * prevalence / 100, 2)

def calculate_symptomatic_population(prevalent_population, symptomatic_rate):
    return round(prevalent_population * symptomatic_rate / 100, 2)

def calculate_diagnosed_population(symptomatic_population, diagnosis_rate):
    return round(symptomatic_population * diagnosis_rate / 100, 2)

def calculate_potential_patients(diagnosed_population, access_rate):
    return round(diagnosed_population * access_rate / 100, 2)

def calculate_drug_treated_patients(potential_patients, treatment_rate):
    return round(potential_patients * treatment_rate / 100, 2)

def load_and_process_prohibited_generics(uploaded_file):
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)
        # Ensure 'Generic Name' is in uppercase to match the mcaz_register format
        df['Generic Name'] = df['Generic Name'].str.upper()
        return df
    return pd.DataFrame()

def filter_data_for_user(user_type, merged_data, prohibited_list):
    if user_type == 'Importer':
        # Filter out prohibited generics for importers
        filtered_data = merged_data[~merged_data['Generic Name'].isin(prohibited_list['Generic Name'])]
    else:
        # Local Manufacturer gets the full data
        filtered_data = merged_data
    return filtered_data

def apply_mutually_exclusive_filters(data, filters):
    for key, selected in filters.items():
        if selected and selected != 'None':
            data = data[data[key] == selected]
    return data

# Function for fuzzy matching of principal names
def fuzzy_match_names(series, threshold=90):
    # Convert the series to string type and fill NaN values with an empty string
    series = series.fillna('').astype(str)
    unique_names = series.unique()
    matched_names = {}
    
    for name in unique_names:
        if name:  # Check if the name is not an empty string
            # Find the best match for each unique name
            best_match = process.extractOne(name, unique_names, scorer=fuzz.token_sort_ratio)
            if best_match[1] >= threshold:
                matched_names[name] = best_match[0]
            else:
                matched_names[name] = name
        else:
            matched_names[name] = name  # Keep empty strings as is

    return series.map(matched_names)

def load_data_fda(uploaded_file):
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)
        return df
    return pd.DataFrame()

def filter_fda_data(fda_data, mcaz_register):
    filtered_data = fda_data.copy()
    for index, row in fda_data.iterrows():
        if ((mcaz_register['Generic Name'] == row['ACTIVE INGREDIENT']) &
            (mcaz_register['Strength'] == row['DOSAGE STRENGTH']) &
            (mcaz_register['Form'] == row['DOSAGE FORM'])).any():
            filtered_data = filtered_data.drop(index)
    return filtered_data

def load_data_orange(file):
    if file is not None:
        return pd.read_csv(file)
    return pd.DataFrame()

def outer_join_dfs(df1, df2, df3, key):
    return df1.merge(df2, on=key, how='outer').merge(df3, on=key, how='outer')

def filter_dataframe(df, column, value):
    if value != "None":
        return df[df[column] == value]
    return df

def display_main_application_content():
                        
    st.markdown("<h1 style='font-size:30px;'>Pharmaceutical Products Analysis Application</h1>", unsafe_allow_html=True)
    # Initialize mcaz_register as an empty DataFrame at the start
    mcaz_register = pd.DataFrame()       

    # Initialize the variable to None or an empty list
    selected_generic_names = []   

    # Sidebar for navigation
    menu = ['Data Overview', 'Market Analysis', 'Manufacturer Analysis', 'FDA Orange Book Analysis', 'Patient-flow Forecast', 'Drug Classification Analysis', 'Drugs with no Competition']
    choice = st.sidebar.radio("Menu", menu)
    
    # File uploader
    uploaded_file = st.sidebar.file_uploader("Upload your MCAZ Register CSV file", type=["csv"])

    if uploaded_file is not None:
        data = load_data(uploaded_file)

        # Data Overview
        if choice == 'Data Overview':
            # ... code for 'Data Overview'
            st.subheader('Data Overview')
            # Load the data using the existing function
            data = load_data(uploaded_file)
            mcaz_register = load_data(uploaded_file)
            st.session_state['mcaz_register'] = mcaz_register
            
            # Manufacturer Filter
            # Check if 'Manufacturers' column exists in the data
            if 'Manufacturers' in data.columns:
                manufacturer_options = ['All Manufacturers'] + sorted(data['Manufacturers'].dropna().unique().tolist())
                selected_manufacturer = st.selectbox('Select Manufacturer', manufacturer_options, index=0)
            else:
                st.error("The 'Manufacturers' column is missing from the uploaded data.")

            # Generic Name (Product) Filter
            product_options = ['All Products'] + sorted(data['Generic Name'].dropna().unique().tolist())
            selected_product = st.selectbox('Select Generic Name', product_options, index=0)

            # Form Filter
            form_options = ['All Forms'] + sorted(data['Form'].dropna().unique().tolist())
            selected_form = st.selectbox('Select Form', form_options, index=0)

            # Principal Filter
            principal_options = ['All Principal'] + sorted(data['Principal Name'].dropna().unique().tolist())
            selected_principal = st.selectbox('Select Principal Name', principal_options, index=0)

            # Categories of Distribution Filter
            category_options = ['All Categories of Distribution'] + sorted(data['Categories for Distribution'].dropna().unique().tolist())
            selected_category = st.selectbox('Select Category of Distribution', category_options, index=0)

            # Applicant Filter
            applicant_options = ['All Applicants'] + sorted(data['Applicant Name'].dropna().unique().tolist())
            selected_applicant = st.selectbox('Select Applicant Name', applicant_options, index=0)

            # Sort Order Filter for Generic Name
            sort_order_generic_options = ['Ascending', 'Descending']
            selected_sort_order_generic = st.selectbox('Sort by Generic Name', sort_order_generic_options)

            # Sort Order Filter for Strength
            sort_order_strength_options = ['Ascending', 'Descending']
            selected_sort_order_strength = st.selectbox('Sort by Strength', sort_order_strength_options)


            # Filtering the data based on selections
            filtered_data = data
            if selected_manufacturer != 'All Manufacturers':
                filtered_data = filtered_data[filtered_data['Manufacturers'] == selected_manufacturer]
            if selected_product != 'All Products':
                filtered_data = filtered_data[filtered_data['Generic Name'] == selected_product]
            if selected_form != 'All Forms':
                filtered_data = filtered_data[filtered_data['Form'] == selected_form]
            if selected_principal != 'All Principal':
                filtered_data = filtered_data[filtered_data['Principal Name'] == selected_principal]
            if selected_category != 'All Categories of Distribution':
                filtered_data = filtered_data[filtered_data['Categories for Distribution'] == selected_category]
            if selected_applicant != 'All Applicants':
                filtered_data = filtered_data[filtered_data['Applicant Name'] == selected_applicant]

            # Apply sort order for Generic Name and then Strength
            if selected_sort_order_generic == 'Descending':
                filtered_data = filtered_data.sort_values(by=['Generic Name', 'Strength'], ascending=[False, selected_sort_order_strength == 'Ascending'])
            else:
                filtered_data = filtered_data.sort_values(by=['Generic Name', 'Strength'], ascending=[True, selected_sort_order_strength == 'Ascending'])

            # Display the filtered dataframe
            st.write("Filtered Data:")
            st.dataframe(filtered_data)

            # Download Dataframe
            csv = convert_df_to_csv(filtered_data)
            st.download_button(label="Download Filtered Data as CSV", data=csv, file_name='filtered_data.csv', mime='text/csv')
                                 
            #  Fuzzy matching
            if 'fuzzy_matched_data' not in st.session_state:
                st.session_state.fuzzy_matched_data = pd.DataFrame()
            if 'atc_level_data' not in st.session_state:
                st.session_state.atc_level_data = pd.DataFrame()
                
            #  Fuzzy matching and ATC Code Extraction
            st.subheader("Data Processing with Fuzzy Matching and ATC Code Extraction")

            # Choose the type of medicine
            medicine_type = st.radio("Select Medicine Type", ["Human Medicine", "Veterinary Medicine"])

            # Initialize session state for fuzzy matching data and ATC level data
            if 'fuzzy_matched_data' not in st.session_state:
                st.session_state.fuzzy_matched_data = pd.DataFrame()
            if 'atc_level_data' not in st.session_state:
                st.session_state.atc_level_data = pd.DataFrame()

            mcaz_register_file = st.file_uploader("Upload MCAZ Register File", type=['csv'], key="mcaz_register_uploader")
            atc_index_file = st.file_uploader(f"Upload {'Human' if medicine_type == 'Human Medicine' else 'Veterinary'} ATC Index File", type=['csv'], key="atc_index_uploader")

            # Select the correct ATC code extraction function based on the medicine type
            extract_atc_levels = extract_atc_levels_human if medicine_type == 'Human Medicine' else extract_atc_levels_veterinary

            # Initialize atc_index to None outside the conditional blocks
            atc_index = None
            mcaz_register = None
            
            # Process data only if files are uploaded and fuzzy_matched_data is empty
            if mcaz_register_file and atc_index_file and st.session_state.fuzzy_matched_data.empty:
                with st.spinner('Processing and mapping data...'):
                    # Load the two files
                    mcaz_register = pd.read_csv(mcaz_register_file)
                    atc_index = pd.read_csv(atc_index_file)
                    
                    # Fuzzy Matching Logic
                    name_to_atc_code = dict(zip(atc_index['Name'], atc_index['ATCCode']))
                    mcaz_register['Best Match Name'] = mcaz_register['Generic Name'].apply(
                        lambda x: process.extractOne(x, atc_index['Name'])[0]
                    )
                    mcaz_register['Match Score'] = mcaz_register['Generic Name'].apply(
                        lambda x: process.extractOne(x, atc_index['Name'])[1]
                    )
                    mcaz_register['ATCCode'] = mcaz_register['Best Match Name'].map(name_to_atc_code)
                    # Update the session state
                    st.session_state.fuzzy_matched_data = mcaz_register

            # Display the processed data only if it exists in session state
            if 'fuzzy_matched_data' in st.session_state and not st.session_state.fuzzy_matched_data.empty:
                st.write("Updated MCAZ Register with Fuzzy Matching and ATC Codes:")
                st.dataframe(st.session_state.fuzzy_matched_data)
                # ... [Rest of your code]
                  # Perform further processing on the mcaz_register DataFrame
                # Make sure to use the DataFrame from session state
                mcaz_register = st.session_state.fuzzy_matched_data

                # Check if the DataFrame has the required columns before accessing them
                required_columns = ['Generic Name', 'Strength', 'Form', 'Categories for Distribution', 'Manufacturers', 
                                    'Principal Name', 'Best Match Name', 'Match Score', 'ATCCode']
                if all(col in mcaz_register.columns for col in required_columns):
                    mcaz_register = mcaz_register[required_columns]
                    # ... [Any further operations on mcaz_register]
                else:
                    st.error("Missing required columns in the dataset.")
            else:
                st.warning("Please upload both MCAZ Register and ATC Index files to proceed.")

            # Download file
            csv = convert_df_to_csv(mcaz_register)
            if csv is not None:
                # Proceed with operations that use 'csv'
                st.download_button(label="Download MCAZ Register as CSV", data=csv, file_name='mcaz_register.csv', mime='text/csv', key='download_mcaz_withcodes')

            else:
                # Handle the case where 'csv' is None, e.g., display a message or take alternative action
                print("No data available to convert to CSV")
                    
            
            if mcaz_register is not None:
                # Proceed only if mcaz_register is a DataFrame
                try:
                    mcaz_register = mcaz_register[['Generic Name', 'Strength', 'Form','Categories for Distribution','Manufacturers','Principal Name','Best Match Name', 'Match Score', 'ATCCode']]
                    # Rest of your code that works with mcaz_register
                    mcaz_register = mcaz_register.applymap(lambda x: x.upper() if isinstance(x, str) else x)
                    # You can also save result_df to a CSV file or use it for further processing

                    # Apply the function to each ATC code in the DataFrame
                    mcaz_register[['ATCLevelOneCode', 'ATCLevelTwoCode', 'ATCLevelThreeCode', 'ATCLevelFourCode']] = \
                        mcaz_register['ATCCode'].apply(lambda x: pd.Series(extract_atc_levels(x)))

                    st.session_state.atc_level_data = mcaz_register

                    if not st.session_state.atc_level_data.empty:
                        st.write("Updated MCAZ Register with ATC Level Codes:")
                        st.dataframe(st.session_state.atc_level_data)

                        # Download file
                        csv = convert_df_to_csv(st.session_state.atc_level_data)
                        st.download_button(label="Download MCAZ Register as CSV", data=csv, file_name='mcaz_register.csv', mime='text/csv', key ='download_updated_register')
                except KeyError as e:
                    # Handle the case where one or more columns are missing
                    print(f"Column not found in DataFrame: {e}")
            else:
                # Handle the case where mcaz_register is None
                print("mcaz_register is None. Please check data loading and processing steps.")
                         

            # ATC Code Description Integration and Filtering
            # Streamlit UI layout
            st.subheader("ATC Code Description Integration and Filtering")

            # Initialize variables for ATC data and filter variables
            atc_one = atc_two = atc_three = atc_four = None
            atc_one_desc = atc_two_desc = atc_three_desc = atc_four_desc = selected_generic_names = []

            # File uploaders for ATC level description files
            atc_one_file = st.file_uploader("Upload ATC Level One Description File", type=['csv'], key="atc_one_uploader")
            atc_two_file = st.file_uploader("Upload ATC Level Two Description File", type=['csv'], key="atc_two_uploader")
            atc_three_file = st.file_uploader("Upload ATC Level Three Description File", type=['csv'], key="atc_three_uploader")
            atc_four_file = st.file_uploader("Upload ATC Level Four Description File", type=['csv'], key="atc_four_uploader")

            # Check if the data for merging is available in session state
            if 'atc_level_data' in st.session_state and not st.session_state.atc_level_data.empty:
                mcaz_register = st.session_state.atc_level_data
                # ... [Merging logic]
                merge_data = st.button("Merge Data")

                if merge_data:
                    atc_one = safe_load_csv(atc_one_file)
                    atc_two = safe_load_csv(atc_two_file)
                    atc_three = safe_load_csv(atc_three_file)
                    atc_four = safe_load_csv(atc_four_file)

                    # Retrieve mcaz_register from session state
                    mcaz_register = st.session_state.atc_level_data

                    # Merge with ATC level descriptions
                    with st.spinner('Merging data with ATC level descriptions...'):
                        if atc_one is not None and 'ATCLevelOneCode' in mcaz_register.columns:
                            mcaz_register = mcaz_register.merge(atc_one, on='ATCLevelOneCode', how='left')
                        if atc_two is not None and 'ATCLevelTwoCode' in mcaz_register.columns:
                            mcaz_register = mcaz_register.merge(atc_two, on='ATCLevelTwoCode', how='left')
                        if atc_three is not None and 'ATCLevelThreeCode' in mcaz_register.columns:
                            mcaz_register = mcaz_register.merge(atc_three, on='ATCLevelThreeCode', how='left')
                        if atc_four is not None and 'ATCLevelFourCode' in mcaz_register.columns:
                            mcaz_register = mcaz_register.merge(atc_four, on='ATCLevelFourCode', how='left')

                    # Transform the relevant columns to upper case
                    # Replace 'Column1', 'Column2', etc., with the actual column names you want to transform
                    columns_to_uppercase = ['Generic Name']  # Add your column names here

                    for col in columns_to_uppercase:
                        if col in mcaz_register.columns:
                            mcaz_register[col] = mcaz_register[col].str.upper()

                    # Update session state with the merged data
                    st.session_state['mcaz_with_ATCCodeDescription'] = mcaz_register

                    # Option 1: Remove complete duplicates
                    mcaz_register = mcaz_register.drop_duplicates()

                # Display the merged dataframe
                if not mcaz_register.empty:
                    st.write("Merged Data:")
                    st.dataframe(mcaz_register)
                else:
                    st.write("No data to display after merging.")
                
            else:
                st.warning("Please complete the fuzzy matching process first.")

                    
            # Filters
            filter_options = ["None", "ATCLevelOneDescript", "ATCLevelTwoDescript", "ATCLevelThreeDescript", "Chemical Subgroup", "Generic Name"]
            selected_filter = st.radio("Select a filter", filter_options)

            if selected_filter != "None" and not st.session_state.get('mcaz_with_ATCCodeDescription', pd.DataFrame()).empty:
                # Convert all values to string and sort
                filter_values = sorted(st.session_state['mcaz_with_ATCCodeDescription'][selected_filter].astype(str).unique())
                selected_values = st.multiselect(f"Select {selected_filter}", filter_values)

                if selected_values:
                    # Filter the dataframe only if the selection is not empty
                    filtered_data = st.session_state['mcaz_with_ATCCodeDescription'][
                        st.session_state['mcaz_with_ATCCodeDescription'][selected_filter].astype(str).isin(selected_values)
                    ]
                    st.write(f"Filtered Data by {selected_filter}:")
                    st.dataframe(filtered_data)
                else:
                    st.write("No filter applied.")

                    # Download file option
                    csv = convert_df_to_csv(filtered_data)
                    st.download_button(label="Download MCAZ Register as CSV", data=csv, file_name='mcaz_register_filtered.csv', mime='text/csv', key='download_mcaz_register_filtered')

            # Filter data based on local manufacturer or importer for selected type
            st.subheader("Data Filtering Based on User Type and Selected Filter")

            # Medicine type selection
            medicine_type_options = ["Select Medicine Type", "Human Medicine", "Veterinary Medicine"]
            selected_medicine_type = st.selectbox("Select Medicine Type", medicine_type_options)

            # Only proceed with user type filtering if "Human Medicine" is selected
            if selected_medicine_type == "Human Medicine":
                st.subheader("Data Filtering Based on User Type and Selected Filter")

                # Upload file
                prohibited_file = st.file_uploader("Upload Prohibited Generics List", type=['csv'])

                # User type selection and prohibited generics list upload
                # Include 'None' in user_type selection
                user_type_options = ["None", "Local Manufacturer", "Importer"]
                user_type = st.radio("Select User Type", user_type_options)

                # Define additional filter options
                filter_options = ["None", "ATCLevelOneDescript", "ATCLevelTwoDescript", 
                                    "ATCLevelThreeDescript", "Chemical Subgroup", "Generic Name"]
                selected_filter = st.radio("Select an additional filter", filter_options)

                # Check if the data is available in the session state
                if 'mcaz_with_ATCCodeDescription' in st.session_state and not st.session_state['mcaz_with_ATCCodeDescription'].empty:
                    mcaz_register = st.session_state['mcaz_with_ATCCodeDescription']

                    # Apply user type filter
                    if prohibited_file and user_type != "None":
                        prohibited_generics = load_and_process_prohibited_generics(prohibited_file)
                        mcaz_register = filter_data_for_user(user_type, mcaz_register, prohibited_generics)

                        # Option 1: Remove complete duplicates
                        mcaz_register = mcaz_register.drop_duplicates()

                    # Apply additional filter if selection is not 'None'
                    if selected_filter != "None":
                        filter_values = sorted(mcaz_register[selected_filter].astype(str).unique())
                        selected_values = st.multiselect(f"Select {selected_filter}", filter_values)

                        if selected_values:
                            mcaz_register = mcaz_register[mcaz_register[selected_filter].astype(str).isin(selected_values)]

                    st.write(f"Filtered data count: {len(mcaz_register)}")    
                    st.write("Filtered Data:")
                    st.dataframe(mcaz_register)
                else:
                    st.write("Data not available in the session state.")
            else:
                st.write("Select 'Human Medicine' to access user type based data filtering.")


        # Market Analysis
        elif choice == 'Market Analysis':
            st.subheader('Market Analysis')
            # Manufacturer selection logic
            # Placeholder for manufacturer filtering (if not yet implemented)
            all_manufacturers = ['All Manufacturers'] + sorted(data['Manufacturers'].dropna().unique().tolist())
            selected_manufacturer = st.selectbox('Select Manufacturer', all_manufacturers, index=0, key="manufacturer_select")
            if selected_manufacturer == 'All Manufacturers':
                manufacturer_filtered_data = data
            else:
                manufacturer_filtered_data = data[data['Manufacturers'] == selected_manufacturer]

            # Form selection logic
            all_forms = ['All Forms'] + sorted(data['Form'].dropna().unique().tolist())
            selected_forms = st.multiselect('Select Forms', all_forms, default='All Forms')
            if 'All Forms' in selected_forms or not selected_forms:
                form_filtered_data = manufacturer_filtered_data
            else:
                form_filtered_data = manufacturer_filtered_data[manufacturer_filtered_data['Form'].isin(selected_forms)]

            # Visualization (e.g., distribution of drug forms)
            form_counts = form_filtered_data['Form'].value_counts()
            st.bar_chart(form_counts)

            # Streamlit UI components for "Generic Name Count"
            st.subheader('Generic Name Count')

            # Load the data using the existing function
            data = load_data(uploaded_file)

            # Count unique generic names and their frequencies
            unique_generic_name_count = data['Generic Name'].nunique()
            generic_name_counts = data['Generic Name'].value_counts().head(1000)

            # Display the counts
            st.write(f"Total unique generic names: {unique_generic_name_count}")
            st.write("Top 1000 Generic Names by Count:")
            st.dataframe(generic_name_counts)

            # Download button for unique product count
            if not generic_name_counts.empty:
                csv = generic_name_counts.to_csv(index=False)
                st.download_button("Download Generic Name Data", csv, "generic_data.csv", "text/csv", key='download-unique-generic')

            # Unique generic name count
            st.subheader('Unique Generic Name Count')

            # Count unique generic names and their frequencies
            generic_name_counts = data['Generic Name'].value_counts()

            # Filter options
            filter_options = ['3 or less', '4', '5', '6', '7 or more']
            selected_filter = st.selectbox('Select count filter:', filter_options, index=0)

            # Apply filter
            if selected_filter == '3 or less':
                filtered_counts = generic_name_counts[generic_name_counts <= 3]
            elif selected_filter == '7 or more':
                filtered_counts = generic_name_counts[generic_name_counts >= 7]
            else:
                count_value = int(selected_filter)
                filtered_counts = generic_name_counts[generic_name_counts == count_value]

            # Display the counts
            st.write(f"Generic Names with {selected_filter} counts:")
            st.dataframe(filtered_counts)

            # Download button for generic name counts
            if not filtered_counts.empty:
                csv = filtered_counts.to_csv(index=False)
                st.download_button("Download Generic Name Counts", csv, "generic_name_counts.csv", "text/csv", key='download-generic-name-count')


            # Show unique products
            st.subheader('Unique Products Count')

            # Load the data using the existing function
            data = load_data(uploaded_file)

            # Create a new column combining 'Generic Name', 'Strength', and 'Form'
            data['Combined'] = data['Generic Name'] + " - " + data['Strength'].astype(str) + " - " + data['Form']

            # Product Filter
            product_options = ['All Products'] + sorted(data['Combined'].dropna().unique().tolist())
            selected_product = st.selectbox('Select Product', product_options, index=0)

            # Filter the data based on the selected product
            if selected_product != 'All Products':
                filtered_data = data[data['Combined'] == selected_product]
            else:
                filtered_data = data

            # Count unique products based on 'Combined'
            unique_product_count = filtered_data['Combined'].nunique()

            # Display the count
            st.write(f"Total unique products (by Generic Name, Strength, and Form): {unique_product_count}")

            # Value count filter options
            count_filter_options = ['3 or less', '4', '5', '6', '7 or more']
            selected_count_filter = st.selectbox('Select value count filter:', count_filter_options)

            # Filter and display the list of unique products with their count
            if st.checkbox("Show List of Unique Products", value=True):
                unique_products_counts = filtered_data['Combined'].value_counts()

                if selected_count_filter == '3 or less':
                    filtered_counts = unique_products_counts[unique_products_counts <= 3]
                elif selected_count_filter == '4':
                    filtered_counts = unique_products_counts[unique_products_counts == 4]
                elif selected_count_filter == '5':
                    filtered_counts = unique_products_counts[unique_products_counts == 5]
                elif selected_count_filter == '6':
                    filtered_counts = unique_products_counts[unique_products_counts == 6]
                elif selected_count_filter == '7 or more':
                    filtered_counts = unique_products_counts[unique_products_counts >= 7]

                st.write(filtered_counts)

                # Download button for unique product count
                if not filtered_counts.empty:
                    csv = filtered_counts.to_csv(index=False)
                    st.download_button("Download Unique Products Data", csv, "unique_products_data.csv", "text/csv", key='download-unique-product')

        # Manufacturer Analysis
        elif choice == 'Manufacturer Analysis':
            st.subheader('Manufacturer Analysis')

            # Ensure all manufacturers are strings and handle NaN values
            all_manufacturers = data['Manufacturers'].dropna().unique()
            all_manufacturers = [str(manufacturer) for manufacturer in all_manufacturers]
            all_manufacturers.sort()

            # Adding 'All Manufacturers' option
            manufacturers_options = ['All Manufacturers'] + all_manufacturers
            selected_manufacturer = st.selectbox('Select Manufacturer', manufacturers_options, index=0)

            # Filtering data based on the selected manufacturer
            if selected_manufacturer == 'All Manufacturers':
                filtered_data = data
            else:
                filtered_data = data[data['Manufacturers'] == selected_manufacturer]

            # Convert 'Date Registered' to datetime
            filtered_data['Date Registered'] = pd.to_datetime(filtered_data['Date Registered'])

            # Yearly trend analysis
            yearly_trend = filtered_data['Date Registered'].dt.year.value_counts().sort_index()
            st.line_chart(yearly_trend)

            # Main submodule for Principal Product Count
            st.subheader("Principal Product Count")

            # Data
            filtered_counts = pd.DataFrame()
            data = load_data(uploaded_file)

            if not data.empty:
                # Apply fuzzy matching to 'Principal Name'
                data['Fuzzy Matched Principal'] = fuzzy_match_names(data['Principal Name'])

                # Count products by fuzzy matched principal name
                principal_counts = (data.groupby('Fuzzy Matched Principal')['Generic Name']
                                    .count()
                                    .reset_index()
                                    .rename(columns={'Fuzzy Matched Principal': 'Principal Name', 'Generic Name': 'Generic Name Count'})
                                    .sort_values(by='Generic Name Count', ascending=False))

                st.write("Product Count by Principal:")
                st.dataframe(principal_counts)

                # Display the total count of products
                total_products = len(data)
                st.write(f"Total Count of Products: {total_products}")

                # Convert the complete DataFrame to CSV
                csv_data = convert_df_to_csv(principal_counts)
                st.download_button(
                    label="Download data as CSV",
                    data=csv_data,
                    file_name='principal_product_count.csv',
                    mime='text/csv',
                )
            else:
                st.write("No data available.")

            # Anatomial Main Group
            st.subheader("Anatomcal Main Group Count")

            if 'mcaz_with_ATCCodeDescription' in st.session_state and not st.session_state['mcaz_with_ATCCodeDescription'].empty:
                mcaz_register = st.session_state['mcaz_with_ATCCodeDescription']

                # Remove complete duplicates
                mcaz_register = mcaz_register.drop_duplicates()

                if not mcaz_register.empty:
                    # Convert 'Principal Name' to string and handle NaN values
                    mcaz_register['Principal Name'] = mcaz_register['Principal Name'].fillna('Unknown').astype(str)

                    # Add "None" option and select Principal Name
                    principal_options = ['None'] + sorted(mcaz_register['Principal Name'].unique())
                    selected_principal = st.selectbox("Select Principal Name", principal_options)

                    # Choose sort order
                    sort_order = st.radio("Select Sort Order", ["Ascending", "Descending"])

                    if selected_principal != "None":
                        # Filter data based on selected principal
                        filtered_data = mcaz_register[mcaz_register['Principal Name'] == selected_principal]
                    else:
                        # If "None" is selected, use the entire dataset
                        filtered_data = mcaz_register

                    # Group by 'ATC Level One Description' and count unique 'Generic Name'
                    # Sort based on the selected sort order
                    if sort_order == "Descending":
                        atc_classification_count = (filtered_data.groupby('ATCLevelOneDescript')['Generic Name']
                                                    .count()
                                                    .reset_index()
                                                    .rename(columns={'Generic Name': 'GenericNameCount'})
                                                    .sort_values(by='GenericNameCount', ascending=False))
                    else:
                        atc_classification_count = (filtered_data.groupby('ATCLevelOneDescript')['Generic Name']
                                                    .count()
                                                    .reset_index()
                                                    .rename(columns={'Generic Name': 'GenericNameCount'})
                                                    .sort_values(by='GenericNameCount', ascending=True))

                    st.write(f"Count of Generic Name by ATC Level One Description (sorted {sort_order}):")
                    st.dataframe(atc_classification_count)

                    # Calculate the total count of products across all ATC Level One Descriptions
                    # Ensure you're summing only the 'GenericNameCount' column
                    total_product_count = atc_classification_count['GenericNameCount'].sum()
                    st.write(f"Total Count of Products (Across All Groups): {total_product_count}")

                    # Convert the complete DataFrame to CSV
                    csv_data = convert_df_to_csv(atc_classification_count)
                    st.download_button(
                        label="Download data as CSV",
                        data=csv_data,
                        file_name='atc_classification_one_count.csv',
                        mime='text/csv',
                    )

                else:
                    st.write("No data available.")
            else:
                st.write("ATC Code Description data is not available.")

            # Pharmacological Group
            st.subheader("Pharmacological Group Count")

            if 'mcaz_with_ATCCodeDescription' in st.session_state and not st.session_state['mcaz_with_ATCCodeDescription'].empty:
                mcaz_register = st.session_state['mcaz_with_ATCCodeDescription']

                # Remove complete duplicates
                mcaz_register = mcaz_register.drop_duplicates()

                if not mcaz_register.empty:
                    # Convert 'Principal Name' to string and handle NaN values
                    mcaz_register['Principal Name'] = mcaz_register['Principal Name'].fillna('Unknown').astype(str)

                    # Add "None" option and select Principal Name
                    principal_options = ['None'] + sorted(mcaz_register['Principal Name'].unique())
                    selected_principal_1 = st.selectbox("Select Principal Name", principal_options, key = "principal_selection_1")

                    # Choose sort order
                    sort_order_1 = st.radio("Select Sort Order", ["Ascending", "Descending"], key = "sort_order_selection_1")

                    if selected_principal_1 != "None":
                        # Filter data based on selected principal
                        filtered_data = mcaz_register[mcaz_register['Principal Name'] == selected_principal_1]
                    else:
                        # If "None" is selected, use the entire dataset
                        filtered_data = mcaz_register

                    # Group by 'ATC Level One Description' and count unique 'Generic Name'
                    # Sort based on the selected sort order
                    if sort_order_1 == "Descending":
                        atc_classification_count = (filtered_data.groupby('ATCLevelTwoDescript')['Generic Name']
                                                    .count()
                                                    .reset_index()
                                                    .rename(columns={'Generic Name': 'GenericNameCount'})
                                                    .sort_values(by='GenericNameCount', ascending=False))
                    else:
                        atc_classification_count = (filtered_data.groupby('ATCLevelTwoDescript')['Generic Name']
                                                    .count()
                                                    .reset_index()
                                                    .rename(columns={'Generic Name': 'GenericNameCount'})
                                                    .sort_values(by='GenericNameCount', ascending=True))

                    st.write(f"Count of Generic Name by ATC Level Two Description (sorted {sort_order_1}):")
                    st.dataframe(atc_classification_count)

                    # Calculate the total count of products across all ATC Level One Descriptions
                    # Ensure you're summing only the 'GenericNameCount' column
                    total_product_count = atc_classification_count['GenericNameCount'].sum()
                    st.write(f"Total Count of Products (Across All Groups): {total_product_count}")

                    # Convert the complete DataFrame to CSV
                    csv_data = convert_df_to_csv(atc_classification_count)
                    st.download_button(
                        label="Download data as CSV",
                        data=csv_data,
                        file_name='atc_classification_two_count.csv',
                        mime='text/csv', key = "pharmacology",
                    )

                else:
                    st.write("No data available.")
            else:
                st.write("ATC Code Description data is not available.")

            # Therapuetic Group
            st.subheader("Therapeutic Group Count")

            if 'mcaz_with_ATCCodeDescription' in st.session_state and not st.session_state['mcaz_with_ATCCodeDescription'].empty:
                mcaz_register = st.session_state['mcaz_with_ATCCodeDescription']

                # Remove complete duplicates
                mcaz_register = mcaz_register.drop_duplicates()

                if not mcaz_register.empty:
                    # Convert 'Principal Name' to string and handle NaN values
                    mcaz_register['Principal Name'] = mcaz_register['Principal Name'].fillna('Unknown').astype(str)

                    # Add "None" option and select Principal Name
                    principal_options = ['None'] + sorted(mcaz_register['Principal Name'].unique())
                    selected_principal_2 = st.selectbox("Select Principal Name", principal_options, key = "principal_selection_2")

                    # Choose sort order
                    sort_order_2 = st.radio("Select Sort Order", ["Ascending", "Descending"], key = "sort_order_selection_2")

                    if selected_principal_2 != "None":
                        # Filter data based on selected principal
                        filtered_data = mcaz_register[mcaz_register['Principal Name'] == selected_principal_2]
                    else:
                        # If "None" is selected, use the entire dataset
                        filtered_data = mcaz_register

                    # Group by 'ATC Level One Description' and count unique 'Generic Name'
                    # Sort based on the selected sort order
                    if sort_order_2 == "Descending":
                        atc_classification_count = (filtered_data.groupby('ATCLevelThreeDescript')['Generic Name']
                                                    .count()
                                                    .reset_index()
                                                    .rename(columns={'Generic Name': 'GenericNameCount'})
                                                    .sort_values(by='GenericNameCount', ascending=False))
                    else:
                        atc_classification_count = (filtered_data.groupby('ATCLevelThreeDescript')['Generic Name']
                                                    .count()
                                                    .reset_index()
                                                    .rename(columns={'Generic Name': 'GenericNameCount'})
                                                    .sort_values(by='GenericNameCount', ascending=True))

                    st.write(f"Count of Generic Name by ATC Level Three Description (sorted {sort_order_1}):")
                    st.dataframe(atc_classification_count)

                    # Calculate the total count of products across all ATC Level One Descriptions
                    # Ensure you're summing only the 'GenericNameCount' column
                    total_product_count = atc_classification_count['GenericNameCount'].sum()
                    st.write(f"Total Count of Products (Across All Groups): {total_product_count}")

                    # Convert the complete DataFrame to CSV
                    csv_data = convert_df_to_csv(atc_classification_count)
                    st.download_button(
                        label="Download data as CSV",
                        data=csv_data,
                        file_name='atc_classification_three_count.csv',
                        mime='text/csv', key = "therapeutic",
                    )

                else:
                    st.write("No data available.")
            else:
                st.write("ATC Code Description data is not available.")

        # FDA Orange Bookd Analysis
        elif choice == 'FDA Orange Book Analysis':
            st.title("FDA Orange Book Analysis")

            # File uploaders
            products_file = st.file_uploader("Upload the products.csv file", type=['csv'], key="products_uploader")
            patent_file = st.file_uploader("Upload the patent.csv file", type=['csv'], key="patent_uploader")
            exclusivity_file = st.file_uploader("Upload the exclusivity.csv file", type=['csv'], key="exclusivity_uploader")

            if products_file and patent_file and exclusivity_file:
                products_df = load_data_orange(products_file)
                patent_df = load_data_orange(patent_file)
                exclusivity_df = load_data_orange(exclusivity_file)

                # Outer join tables by "Appl_No"
                merged_df = outer_join_dfs(products_df, patent_df, exclusivity_df, "Appl_No")

                # Remove duplicates
                merged_df = merged_df.drop_duplicates(subset=['Ingredient', 'DF;Route', 'Strength', 'Appl_No', 'Product_No_x', 'Patent_No'])

                # Remove records with no patents
                merged_df = merged_df.dropna(subset=['Patent_No'])

                # Remove records with "Type" equal to "DISCN"
                merged_df = merged_df[merged_df['Type'] != 'DISCN']

                # Filters
                ingredient = st.selectbox("Select Ingredient", ['None'] + sorted(merged_df['Ingredient'].dropna().unique().tolist()))
                df_route = st.selectbox("Select DF;Route", ['None'] + sorted(merged_df['DF;Route'].dropna().unique().tolist()))
                trade_name = st.selectbox("Select Trade Name", ['None'] + sorted(merged_df['Trade_Name'].dropna().unique().tolist()))
                applicant = st.selectbox("Select Applicant", ['None'] + sorted(merged_df['Applicant'].dropna().unique().tolist()))
                appl_type = st.selectbox("Select Appl Type", ['None'] + sorted(merged_df['Appl_Type'].dropna().unique().tolist()))
                type_filter = st.selectbox("Select Type", ['None'] + sorted(merged_df['Type'].dropna().unique().tolist()))
                rld = st.selectbox("Select RLD", ['None'] + sorted(merged_df['RLD'].dropna().unique().tolist()))
                rs = st.selectbox("Select RS", ['None'] + sorted(merged_df['RS'].dropna().unique().tolist()))

                # Apply filters
                if ingredient != "None": merged_df = filter_dataframe(merged_df, 'Ingredient', ingredient)
                if df_route != "None": merged_df = filter_dataframe(merged_df, 'DF;Route', df_route)
                if trade_name != "None": merged_df = filter_dataframe(merged_df, 'Trade_Name', trade_name)
                if applicant != "None": merged_df = filter_dataframe(merged_df, 'Applicant', applicant)
                if appl_type != "None": merged_df = filter_dataframe(merged_df, 'Appl_Type', appl_type)
                if type_filter != "None": merged_df = filter_dataframe(merged_df, 'Type', type_filter)
                if rld != "None": merged_df = filter_dataframe(merged_df, 'RLD', rld)
                if rs != "None": merged_df = filter_dataframe(merged_df, 'RS', rs)

                # Display Dataframe
                st.write("Filtered FDA Orange Book Data:")
                st.dataframe(merged_df)

                # Display count of products
                product_count = len(merged_df)
                st.write(f"Number of Products: {product_count}")

                # Download as CSV
                csv = convert_df_to_csv(merged_df)
                st.download_button(label="Download data as CSV", data=csv, file_name='fda_orange_book_data.csv', mime='text/csv')

                # Assuming 'merged_df' is your merged DataFrame
                filtered_columns = [
                    'Ingredient', 'DF;Route', 'Strength', 'Trade_Name', 
                    'Applicant', 'Patent_No', 'Approval_Date', 
                    'Patent_Expire_Date_Text'
                ]

                # Select only the specified columns
                merged_df = merged_df[filtered_columns]

                # Construct URLs for Patent Numbers only if an ingredient is selected
                if ingredient != "None":
                    base_url = "https://patentscope.wipo.int/search/en/search.jsf?query="
                    merged_df['Patent_Link'] = base_url + merged_df['Patent_No'].astype(str)
                    merged_df['Patent_Link'] = merged_df['Patent_Link'].apply(lambda x: f'<a href="{x}" target="_blank">{x}</a>')

                    # Filter the DataFrame based on the selected ingredient
                    filtered_df = merged_df[merged_df['Ingredient'] == ingredient]

                    # HTML Style for left alignment of the 'Patent_Link' column
                    left_align_style = "<style>td:nth-child(9) { text-align: left !important; }</style>"

                    # Display the DataFrame with hyperlinks for the selected ingredient
                    st.write(f"DataFrame with Hyperlinked Patent Numbers for Ingredient: {ingredient}")
                    st.markdown(left_align_style + filtered_df.to_html(escape=False, index=False), unsafe_allow_html=True)
   
                else:
                    st.write("Please select an ingredient to display detailed information.")

        # Patient Flow Forecasting
        elif choice == 'Patient-flow Forecast':
            st.subheader('Patient-flow Forecast')
            # Implement Patient flow Forecast

            # Input fields
            population = st.number_input("Population (millions)", min_value=0.0, value=1.0, step=0.1)
            prevalence = st.number_input("Epidemiology (prevalence %)", min_value=0.0, max_value=100.0, value=1.0, step=0.1)
            symptomatic_rate = st.number_input("Symptomatic rate (%)", min_value=0.0, max_value=100.0, value=1.0, step=0.1)
            diagnosis_rate = st.number_input("Diagnosis rate (%)", min_value=0.0, max_value=100.0, value=1.0, step=0.1)
            access_rate = st.number_input("Access rate (%)", min_value=0.0, max_value=100.0, value=1.0, step=0.1)
            treatment_rate = st.number_input("Drug-treated patients (%)", min_value=0.0, max_value=100.0, value=1.0, step=0.1)

            if st.button("Calculate"):
                prevalent_population = calculate_prevalent_population(population, prevalence)
                symptomatic_population = calculate_symptomatic_population(prevalent_population, symptomatic_rate)
                diagnosed_population = calculate_diagnosed_population(symptomatic_population, diagnosis_rate)
                potential_patients = calculate_potential_patients(diagnosed_population, access_rate)
                drug_treated_patients = calculate_drug_treated_patients(potential_patients, treatment_rate)

                st.write(f"Prevalent Population: {prevalent_population} million")
                st.write(f"Symptomatic Population: {symptomatic_population} million")
                st.write(f"Diagnosed Population: {diagnosed_population} million")
                st.write(f"Potential Patients: {potential_patients} million")
                st.write(f"Drug-treated Patients: {drug_treated_patients} million")

        # Drug Classification Analysis
        elif choice == 'Drug Classification Analysis':
            st.subheader('Drug Classification Analysis')
            # Implement drug classification analysis

            # Assume mcaz_register is loaded elsewhere in your application
            # Load mcaz_register
            mcaz_register = load_data(uploaded_file)

            # Filter options for 'Categories of Distribution'
            categories_options = ['All Categories'] + sorted(mcaz_register['Categories for Distribution'].dropna().unique().tolist())
            selected_category = st.selectbox('Select Category for Distribution', categories_options, index=0)

            # Filter options for 'Manufacturers'
            manufacturers_options = ['All Manufacturers'] + sorted(mcaz_register['Manufacturers'].dropna().unique().tolist())
            selected_manufacturer = st.selectbox('Select Manufacturer', manufacturers_options, index=0)

            # Apply filters
            if selected_category != 'All Categories':
                mcaz_register = mcaz_register[mcaz_register['Categories for Distribution'] == selected_category]

            if selected_manufacturer != 'All Manufacturers':
                mcaz_register = mcaz_register[mcaz_register['Manufacturers'] == selected_manufacturer]

            # Display filtered data
            st.write("Filtered Data:")
            st.dataframe(mcaz_register)

            # Display the total count of products
            total_products = len(mcaz_register)
            st.write(f"Total Count of Products: {total_products}")

        # Drugs with No Patents and NO Competition Analysis
        elif choice == 'Drugs with no Competition':
            st.subheader('FDA Drugs with No Patents and No Competition')
            # Implement FDA No Patents analysis

            # Medicine type selection
            medicine_type = st.radio("Select Medicine Type", ["Human Medicine", "Veterinary Medicine"])

            # Load MCAZ Register data (assuming it's already in session state)
            mcaz_register = st.session_state.get('mcaz_register', pd.DataFrame())

            if medicine_type == "Human Medicine":

                # Upload the file
                uploaded_file = st.file_uploader("Upload your Drugs with No Patents No Competition file", type=['csv'])

                if uploaded_file is not None:
                    fda_data = load_data_fda(uploaded_file)

                    if not fda_data.empty and not mcaz_register.empty:
                        # Filter out products that are in the MCAZ Register
                        filtered_fda_data = filter_fda_data(fda_data, mcaz_register)

                        # Add "None" option and sort filter options
                        dosage_form_options = ['None'] + sorted(fda_data['DOSAGE FORM'].dropna().unique().tolist())
                        selected_dosage_form = st.selectbox("Select Dosage Form", dosage_form_options)

                        type_options = ['None'] + sorted(fda_data['TYPE'].dropna().unique().tolist())
                        selected_type = st.selectbox("Select Type", type_options)

                        # Apply filters if selections are not "None"
                        if selected_dosage_form != "None":
                            filtered_fda_data = filtered_fda_data[filtered_fda_data['DOSAGE FORM'] == selected_dosage_form]
                        if selected_type != "None":
                            filtered_fda_data = filtered_fda_data[filtered_fda_data['TYPE'] == selected_type]

                        # Display the filtered dataframe
                        st.write("Filtered FDA Data (Excluding MCAZ Registered Products):")
                        st.dataframe(filtered_fda_data)

                        # Count and display the number of drugs
                        drug_count = len(filtered_fda_data)
                        st.write(f"Total Number of Unique Drugs: {drug_count}")

                        # Convert the complete DataFrame to CSV
                        csv_data = convert_df_to_csv(filtered_fda_data)
                        st.download_button(
                            label="Download data as CSV",
                            data=csv_data,
                            file_name='fda_nocompetition_product_count.csv',
                            mime='text/csv',
                        )

                    else:
                        st.write("Upload a file to see the data or ensure MCAZ Register data is available.")
                else:
                    st.write("Please upload a file.")
            else:
                st.write("Select 'Human Medicine' to access FDA drugs analysis.")

    else:
        st.warning('Please upload MCAZ Register CSV file.')

def main():
           
    # Initialize session state for admin and user login
    if 'admin_logged_in' not in st.session_state:
        st.session_state['admin_logged_in'] = False
    if 'user_logged_in' not in st.session_state:
        st.session_state['user_logged_in'] = False

    # Display the title, admin and user login forms only when no user is logged in
    if not st.session_state['user_logged_in']:
        st.title("User Management System")
        
        # Admin login form
        if not st.session_state.get('admin_logged_in', False):
            st.subheader("Admin Login")
            admin_username = st.text_input("Admin Username", key="admin_user")
            admin_password = st.text_input("Admin Password", type="password", key="admin_pass")

            if st.button("Admin Login"):
                try:
                    if authenticate_user(admin_username, admin_password, admin_only=True):
                        st.session_state['admin_logged_in'] = True
                        st.success("Admin authentication successful")
                    else:
                        st.error("Authentication failed")
                except Exception as e:
                    # Catch any exceptions that occur during authentication
                    st.error(f"An error occurred during authentication: {e}")

#         # Admin login form
#         admin_username = admin_password = ""
#         if not st.session_state['admin_logged_in']:
#             st.subheader("Admin Login")
#             admin_username = st.text_input("Admin Username", key="admin_user")
#             admin_password = st.text_input("Admin Password", type="password", key="admin_pass")
#             if st.button("Admin Login"):
#                 if authenticate_user(admin_username, admin_password, admin_only=True):
#                     st.session_state['admin_logged_in'] = True
#                     st.success("Admin authentication successful")
#                 else:
#                     st.error("Authentication failed")

        # User creation form shown only if admin is logged in
        if st.session_state['admin_logged_in']:
            create_new_user_ui(admin_username, admin_password)
            
        # Regular user login form
        st.subheader("User Login")
        username = st.text_input("Username", key="user_name")
        password = st.text_input("Password", type="password", key="user_pass")

        if st.button("User Login"):
            try:
                if authenticate_user(username, password, admin_only=False):
                    st.session_state['user_logged_in'] = True
                    st.success("Login successful")
                else:
                    st.error("Login failed or account expired")
            except Exception as e:
                # Catch any exceptions that occur during authentication
                st.error(f"An error occurred during authentication: {e}")

#         # Regular user login form
#         st.subheader("User Login")
#         username = st.text_input("Username", key="user_name")
#         password = st.text_input("Password", type="password", key="user_pass")
#         if st.button("User Login"):
#             if authenticate_user(username, password, admin_only=False):
#                 st.session_state['user_logged_in'] = True
#                 st.success("Login successful")
#             else:
#                 st.error("Login failed or account expired")
                
        # User settings for changing password
        st.subheader("User Settings")
        with st.form("Change Password"):
            new_password = st.text_input("New Password", type="password", key='new_password')
            update_button = st.form_submit_button("Update Password")

            if update_button:
                # Retrieve the current logged-in user's username from session state
                current_username = st.session_state['current_user']
                if update_user_password(current_username, new_password):
                    st.success("Password updated successfully")
                else:
                    st.error("Failed to update password")

    # Display main application content if the user is logged in
    if st.session_state['user_logged_in']:
        display_main_application_content()
        
if __name__ == "__main__":
    main()


# In[ ]:





# In[ ]:




