#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import streamlit as st
import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from fuzzywuzzy import process
from fuzzywuzzy import fuzz
from datetime import datetime, date 
import os
import toml
import chardet
from rapidfuzz import process, fuzz

# Specify the timezone for Harare
harare_timezone = ZoneInfo("Africa/Harare")

# Initialize session state variables at the start
def initialize_session_state():
    if 'start_time' not in st.session_state:
        st.session_state['start_time'] = None
    if 'end_time' not in st.session_state:
        st.session_state['end_time'] = None
    if 'processed_rows' not in st.session_state:
        st.session_state['processed_rows'] = 0
    if 'fuzzy_matched_data' not in st.session_state:
        st.session_state['fuzzy_matched_data'] = pd.DataFrame()

initialize_session_state()

# Define a key for your upload in session_state to check if the data is already loaded
data_key = 'ema_fda_healthcanada_data'

def apply_all_filters(df, filter_settings):
    """
    Apply all filters to the dataframe based on the filter settings.
    """
    # Year range filter
    if 'year_range' in filter_settings:
        start_year, end_year = filter_settings['year_range']
        df = df[(df['Approval Year'] >= start_year) & (df['Approval Year'] <= end_year)]

    # NDA/BLA filter
    if filter_settings['nda_bla_selection'] != 'All':
        df = df[df['NDA/BLA'] == filter_settings['nda_bla_selection']]

    # Active Ingredient/Moiety filter
    if filter_settings['active_ingredient_selection'] != 'All':
        df = df[df['Active Ingredient/Moiety'] == filter_settings['active_ingredient_selection']]

    # Review Designation filter
    if filter_settings['review_designation_selection'] != 'All':
        df = df[df['Review Designation'] == filter_settings['review_designation_selection']]

    # Boolean filters (Yes/No or presence checks)
    if filter_settings['orphan_drug_option']:
        df = df[df['Orphan Drug Designation'] == 'Yes']
    if filter_settings['accelerated_approval_option']:
        df = df[df['Accelerated Approval'] == 'Yes']
    if filter_settings['breakthrough_therapy_option']:
        df = df[df['Breakthrough Therapy Designation'] == 'Yes']
    if filter_settings['fast_track_option']:
        df = df[df['Fast Track Designation'] == 'Yes']
    if filter_settings['qualified_infectious_option']:
        df = df[df['Qualified Infectious Disease Product'] == 'Yes']

    return df

def safe_load_csv(uploaded_file):
    if uploaded_file is not None and uploaded_file.size > 0:
        return pd.read_csv(uploaded_file)
    else:
        return None

# Function to load data
@st.cache_data

def load_data(uploaded_file):
    if uploaded_file is not None:
        # Check if the uploaded file is not empty
        uploaded_file.seek(0)  # Go to the start of the file
        if uploaded_file.read(1024) == b'':  # Read the first 1KB to check if it's empty
            st.error('The uploaded file is empty.')
            return pd.DataFrame()
        
        # Reset the file pointer to the start of the file after checking
        uploaded_file.seek(0)
        
        # Since the file is not empty, attempt to read it as a CSV
        df = pd.read_csv(uploaded_file)
        
        # After loading, check if the DataFrame is actually empty or if there's a 'Generic Name' column
        if df.empty:
            st.error('The uploaded file is empty or not in a valid CSV format.')
            return pd.DataFrame()
        
        if 'Generic Name' in df.columns:
            df['Generic Name'] = df['Generic Name'].str.upper().str.strip()
        else:
            st.error("'Generic Name' column not found in the uploaded file.")
            return pd.DataFrame()

        return df
    else:
        # If no file was uploaded, return an empty DataFrame
        return pd.DataFrame()
    
# Adjusted ATC code extraction functions
def extract_atc_levels_human(atc_code):
    # Ensure atc_code is a string to prevent TypeError
    atc_code = str(atc_code) if pd.notna(atc_code) else ""
    return pd.Series([atc_code[:1], atc_code[:3], atc_code[:4], atc_code[:5]])

def extract_atc_levels_veterinary(atc_code):
    atc_code = str(atc_code) if pd.notna(atc_code) else ""
    return pd.Series([atc_code[:1], atc_code[:3], atc_code[:4], atc_code[:5]])
        
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
        # Create a temporary column to identify rows to be filtered out
        # Merge merged_data with prohibited_list on both 'Generic Name' and 'Form'
        # Use an indicator to identify rows that exist in both DataFrames
        temp_merged = merged_data.merge(prohibited_list, on=['Generic Name', 'Form'], how='left', indicator=True)
        
        # Filter out rows that are found in the prohibited_list (i.e., those with '_merge' == 'both')
        filtered_data = temp_merged[temp_merged['_merge'] == 'left_only']
        
        # Drop the '_merge' column as it's no longer needed
        filtered_data = filtered_data.drop(columns=['_merge'])
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

# Function to load data from an uploaded file
@st.cache_data
def load_data_sales(uploaded_file):
    if uploaded_file is not None:
        try:
            # Attempt to read the uploaded file with specified encoding
            df = pd.read_csv(uploaded_file, encoding='latin1')
            # Check if the file is empty by looking at the DataFrame shape
            if df.empty:
                st.error("Uploaded file is empty. Please upload a file with data.")
                return pd.DataFrame()  # Return an empty DataFrame as a fallback
            return df
        except pd.errors.EmptyDataError:
            # Handle the case where the CSV file is empty or not properly formatted
            st.error("Uploaded file is empty or not properly formatted. Please check the file and try again.")
            return pd.DataFrame()  # Return an empty DataFrame as a fallback
        except UnicodeDecodeError as e:
            # Handle potential Unicode decoding errors by providing a message to the user
            st.error(f"Error decoding file: {e}. Try changing the file encoding and upload again.")
            return pd.DataFrame()
        except Exception as e:
            # Handle any other exceptions that may occur
            st.error(f"An error occurred while processing the file: {e}")
            return pd.DataFrame()
    else:
        # If no file is uploaded, return an empty DataFrame
        return pd.DataFrame()
    
# Function to load a CSV file into a DataFrame with caching
@st.cache_data
def load_file(file):
    return pd.read_csv(file)

# Function to initialize necessary columns in the DataFrame if they don't exist
def init_columns(df):
    for column in ['Best Match Name', 'Match Score', 'ATCCode']:
        if column not in df.columns:
            df[column] = pd.NA
    return df

def process_data(mcaz_register, atc_index, extract_atc_levels):
    # Initialize session state for timing and progress if not already done
    if 'start_time_mcaz' not in st.session_state or st.session_state.start_time_mcaz is None:
        st.session_state.start_time_mcaz = datetime.now(harare_timezone)
    
    # Prepare the ATC index
    atc_index['Name'] = atc_index['Name'].astype(str)
    if 'route' not in atc_index.columns:
        atc_index['route'] = ""  # Adding a default empty 'route' if not present
    atc_index['route'] = atc_index['route'].astype(str)
    atc_index['Combined'] = atc_index['Name'] + " | " + atc_index['route']
    combined_to_atc_code = dict(zip(atc_index['Combined'], atc_index['ATCCode']))
    
    # Prepare the FDA register for 'route' if not present
    if 'route' not in mcaz_register.columns:
        mcaz_register['route'] = ""  # Adjust based on 'route' population
    mcaz_register['route'] = mcaz_register['route'].astype(str)
    
    total_rows_mcaz = len(mcaz_register)
    processed_rows_mcaz = st.session_state.get('processed_rows_mcaz', 0)
    
    progress_bar = st.progress(0)
    st.subheader('Processing and mapping data...')
    st.write(f"Processing started at: {datetime.now(harare_timezone).strftime('%Y-%m-%d %H:%M:%S')}")

    # Ensure necessary columns exist
    for col in ['Best Match Name', 'Match Score', 'ATCCode']:
        if col not in mcaz_register.columns:
            mcaz_register[col] = None

    for index, row in mcaz_register.iloc[processed_rows_mcaz:].iterrows():
        combined_ingredient_route = f"{row['Generic Name']} | {row.get('route', '')}"
        
        # Use rapidfuzz for fuzzy matching
        match_result = process.extractOne(combined_ingredient_route, atc_index['Combined'], scorer=fuzz.WRatio)

        if match_result is None:
            best_match_combined, match_score = None, 0
        else:
            best_match_combined, match_score = match_result[0], match_result[1]
        
        atc_code = combined_to_atc_code.get(best_match_combined) if best_match_combined else None
        best_match_name = best_match_combined.split(' | ')[0] if best_match_combined else None
        
        mcaz_register.at[index, 'Best Match Name'] = best_match_name
        mcaz_register.at[index, 'Match Score'] = match_score
        mcaz_register.at[index, 'ATCCode'] = atc_code
        
        progress = int(((index - processed_rows_mcaz + 1) / total_rows_mcaz) * 100)
        progress_bar.progress(progress)
        st.session_state.processed_rows_mcaz = index + 1

    progress_bar.progress(100)
    processing_end_time_mcaz = datetime.now(harare_timezone)
    processing_time_mcaz = processing_end_time_mcaz - st.session_state.start_time_mcaz
    st.write(f"Processing completed at: {processing_end_time_mcaz.strftime('%Y-%m-%d %H:%M:%S')}")
    st.write(f"Total processing time: {processing_time_mcaz}")
    
    st.session_state.fuzzy_matched_data = mcaz_register  # Save processed data for later use

def process_data_fda(fda_register, atc_index, extract_atc_levels):
    # Initialize the start time if not already set
    if 'start_time' not in st.session_state or st.session_state.start_time is None:
        st.session_state.start_time = datetime.now(harare_timezone)
        
    # Prepare the ATC index
    atc_index['Name'] = atc_index['Name'].astype(str)
    if 'route' not in atc_index.columns:
        atc_index['route'] = ""  # Adding a default empty 'route' if not present
    atc_index['route'] = atc_index['route'].astype(str)
    # Combine 'Name' and 'route' for fuzzy matching
    atc_index['Combined'] = atc_index['Name'] + " | " + atc_index['route']
    combined_to_atc_code = dict(zip(atc_index['Combined'], atc_index['ATCCode']))
    
    # Prepare the FDA register for 'route' if not present
    if 'route' not in fda_register.columns:
        fda_register['route'] = ""  # Adjust based on how you populate 'route'
    fda_register['route'] = fda_register['route'].astype(str)
    
    total_rows = len(fda_register)
    fda_processed_rows = st.session_state.get('fda_processed_rows', 0)
    
    progress_bar = st.progress(0)
    st.subheader('Processing and mapping data...')
    st.session_state.start_time = datetime.now(harare_timezone) 
    st.write(f"Processing started at: {st.session_state.start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Ensure necessary columns exist
    for col in ['Best Match Name', 'Match Score', 'ATCCode']:
        if col not in fda_register.columns:
            fda_register[col] = None

    for index, row in fda_register.iloc[fda_processed_rows:].iterrows():
        combined_ingredient_route = f"{row['Ingredient']} | {row.get('route', '')}"
        
        # Use rapidfuzz for fuzzy matching
        match_result = process.extractOne(combined_ingredient_route, atc_index['Combined'], scorer=fuzz.ratio)

        # Handle None result from extractOne
        if match_result is None:
            best_match_combined, match_score = None, 0
        else:
            best_match_combined, match_score = match_result[0], match_result[1]
        
        atc_code = combined_to_atc_code.get(best_match_combined) if best_match_combined else None
        
        best_match_name = best_match_combined.split(' | ')[0] if best_match_combined else None
        fda_register.at[index, 'Best Match Name'] = best_match_name
        fda_register.at[index, 'Match Score'] = match_score
        fda_register.at[index, 'ATCCode'] = atc_code
        
        progress = int(((index - fda_processed_rows + 1) / total_rows) * 100)
        progress_bar.progress(progress)
        st.session_state.fda_processed_rows = index + 1
  
    progress_bar.progress(100)
    st.session_state.end_time = datetime.now(harare_timezone)
    if st.session_state.start_time is not None and st.session_state.end_time is not None:
        processing_time = st.session_state.end_time - st.session_state.start_time
        st.write(f"Processing completed at: {st.session_state.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        st.write(f"Total processing time: {processing_time}")
    else:
        st.error("Processing time could not be calculated due to missing start or end time.")
    
    st.session_state.fuzzy_matched_data_fda = fda_register  # Save processed data for later use

def check_required_columns(df, required_columns, level):
    """
    Checks if the required columns are present in the dataframe.
    If not, displays a warning message and updates the session state to indicate the check failed.
    """
    if df is not None:
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            st.warning(f"Missing required columns for ATC Level {level}: {', '.join(missing_columns)}")
            st.session_state['check_passed'] = False
        if not missing_columns:
            st.success(f"All required column for ATC Level {level} are present.")
    else:
        st.warning(f"No file uploaded for ATC Level {level}.")
        st.session_state['check_passed'] = False
    
# Function to check for required columns in the uploaded file
def check_required_columns_in_file(file, required_columns):
    if file is not None:
        # Attempt to read the uploaded file into a DataFrame
        try:
            df = pd.read_csv(file)
            missing_columns = [column for column in required_columns if column not in df.columns]
            if missing_columns:
                return False, missing_columns
            return True, None
        except Exception as e:
            st.error(f"Failed to read the uploaded file. Error: {str(e)}")
            return False, None
    return None, None  # Indicates no file was uploaded

def check_prohibited_file_columns(df, required_columns):
    # Check for the presence of required columns in the dataframe
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        return False, missing_columns
    return True, []

required_columns_establishment = [
    "FIRM_NAME", "ADDRESS", "EXPIRATION_DATE", "OPERATIONS",
    "ESTABLISHMENT_CONTACT_NAME", "ESTABLISHMENT_CONTACT_EMAIL", "REGISTRANT_NAME",
    "REGISTRANT_CONTACT_NAME", "REGISTRANT_CONTACT_EMAIL"
]

required_columns_country = ["Country", "Alpha-2 code", "Alpha-3 code"]

def process_uploaded_file(uploaded_file):
    try:
        df = pd.read_csv(uploaded_file, encoding='ISO-8859-1')
        
        # Extract COUNTRY_CODE from ADDRESS
        if 'ADDRESS' in df.columns:
            df['COUNTRY_CODE'] = df['ADDRESS'].str.extract(r'\(([^)]+)\)$', expand=False)
            df['COUNTRY_CODE'] = df['COUNTRY_CODE'].fillna('Unknown')
            columns = [
                "FIRM_NAME",
                "ADDRESS",
                "COUNTRY_CODE",
                "EXPIRATION_DATE",
                "OPERATIONS",
                "ESTABLISHMENT_CONTACT_NAME",
                "ESTABLISHMENT_CONTACT_EMAIL",
                "REGISTRANT_NAME",
                "REGISTRANT_CONTACT_NAME",
                "REGISTRANT_CONTACT_EMAIL"
            ]
            df = df[columns]
            
        # Ensure required columns are present, including COUNTRY_CODE
        if 'COUNTRY_CODE' not in df.columns:
            df['COUNTRY_CODE'] = 'Unknown'  # Ensuring COUNTRY_CODE is always present

        required_columns_with_country_code = required_columns_establishment + ['COUNTRY_CODE']
        missing_columns = [col for col in required_columns_with_country_code if col not in df.columns]
        if missing_columns:
            st.error(f"Establishment file is missing required columns: {', '.join(missing_columns)}")
            return None

        return df
    except Exception as e:
        st.error(f"An error occurred while processing the file: {e}")
        return None

def process_country_code_file(uploaded_file):
    try:
        df = pd.read_csv(uploaded_file)
        # Validate required country columns
        if not all(column in df.columns for column in required_columns_country):
            st.error('Country code file is missing one or more required columns.')
            return None

        return df
    except Exception as e:
        st.error(f"An error occurred while processing the country code file: {e}")
        return None

def filter_dataframe_establishments(df, firm_name, country, operations, registrant_name):
    if firm_name != "All":
        df = df[df['FIRM_NAME'] == firm_name]
    if country != "All":
        df = df[df['Country'] == country]  # Ensure column name is correct
    if operations != "All":
        df = df[df['OPERATIONS'].apply(lambda x: x.strip() == operations)]
    if registrant_name != "All":
        df = df[df['REGISTRANT_NAME'] == registrant_name]
    return df.sort_values(by=["FIRM_NAME", "Country", "OPERATIONS", "REGISTRANT_NAME"], ascending=True)

def load_data_nme(uploaded_file):
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file, encoding='latin1')

        # Explicitly check if 'FDA Approval Date' is already in datetime format
        if not pd.api.types.is_datetime64_any_dtype(df['FDA Approval Date']):
            try:
                df['FDA Approval Date'] = pd.to_datetime(df['FDA Approval Date'], errors='coerce')
            except Exception as e:
                st.error(f"Error converting FDA Approval Date to datetime: {e}")
                return None

        # Ensure the conversion was successful by checking for datetime dtype again
        if pd.api.types.is_datetime64_any_dtype(df['FDA Approval Date']):
            df['Approval Year'] = df['FDA Approval Date'].dt.year.dropna().astype(int)
        else:
            st.error("Failed to convert 'FDA Approval Date' to datetime format.")
            return None

        return df
    else:
        return None
    
# This function now returns an HTML <a> tag for each link
def construct_espacenet_link(patent_no):
    espacenet_base_url = "https://worldwide.espacenet.com/searchResults?submitted=true&locale=en_EP&DB=EPODOC&ST=advanced&TI=&AB=&PN="
    link = f"{espacenet_base_url}{patent_no}&AP=&PR=&PD=&PA=&IN=&CPC=&IC=&Submit=Search"
    return f'<a href="{link}" target="_blank">{patent_no}</a>'

def construct_wipo_link(patent_no):
    # This is a base URL for initiating a search on WIPO. Adjustments might be needed based on the exact requirement.
    wipo_search_base_url = "https://patentscope.wipo.int/search/en/search.jsf"
    # The query parameter 'searchQuery' is assumed to be the way to pre-fill the search; adjust based on actual parameter names.
    # Note: This is speculative and may not work as expected without the correct parameter names and values.
    link = f"{wipo_search_base_url}?searchQuery={patent_no}"
    # Return the HTML anchor tag for the link
    return f'<a href="{link}" target="_blank">{patent_no}</a>'

# Function to check if required columns are present in the dataframe
def check_required_columns_orangebook(df, required_columns):
    if df is None:
        return False, ["DataFrame is None"]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        return False, missing_columns
    return True, None

def check_columns(uploaded_file, required_columns):
    """Check if uploaded file contains all required columns."""
    try:
        # Read a small part of the file to determine its encoding
        rawdata = uploaded_file.read(10000)  # Read the first 10,000 bytes to detect encoding
        uploaded_file.seek(0)  # Reset file pointer to the beginning
        result = chardet.detect(rawdata)
        
        encoding = result['encoding']
        if encoding == 'ascii' or not encoding:
            encoding = 'Windows-1252'  # Fallback to 'Windows-1252' if 'ascii' or detection failed
        
        # Attempt to read the file with the detected or fallback encoding
        try:
            df = pd.read_csv(uploaded_file, encoding=encoding)
        except UnicodeDecodeError:
            uploaded_file.seek(0)  # Reset file pointer and try with 'Windows-1252'
            df = pd.read_csv(uploaded_file, encoding='Windows-1252')
        
        if all(column in df.columns for column in required_columns):
            return df
        else:
            st.error(f"{uploaded_file.name} does not contain all required columns.")
            return None
    except Exception as e:
        st.error(f"Error reading {uploaded_file.name}: {str(e)}")
        return None

def process_data_Drugs(dataframes):
    # Join operations
    products_df = dataframes["Products@FDA.csv"]
    applications_df = dataframes["Applications.csv"]
    submissions_df = dataframes["Submissions.csv"]
    marketing_status_df = dataframes["MarketingStatus.csv"]
    marketing_status_lookup_df = dataframes["MarketingStatus_Lookup.csv"]

    # Join Products on Applications, Submissions, and MarketingStatus
    merged_df = products_df.merge(applications_df, on="ApplNo", how="left") \
                            .merge(submissions_df, on="ApplNo", how="left") \
                            .merge(marketing_status_df, on=["ApplNo", "ProductNo"], how="left") \
                            .merge(marketing_status_lookup_df, on="MarketingStatusID", how="left")

    # Drop values where MarketingStatusID is 3 or 5
    merged_df = merged_df[~merged_df.MarketingStatusID.isin([3, 5])]
    
    columns_to_drop = ['ApplPublicNotes', 'SubmissionClassCodeID', 'SubmissionNo', 'SubmissionsPublicNotes', 'MarketingStatusID']
    columns_to_drop = [col for col in columns_to_drop if col in merged_df.columns]

    # Drop the columns from the dataframe safely
    merged_df.drop(columns=columns_to_drop, axis=1, inplace=True)

    return merged_df

def perform_drugs_fda_analysis():
    st.subheader('Drugs@FDA Analysis')

    # Check if the data has already been processed and stored in session state
    if 'processed_data_Drugs' not in st.session_state:
        uploaded_files = st.file_uploader(
            "Upload Applications, Products@FDA, Submissions, MarketingStatus and MarketingStatus_Lookup files",
            accept_multiple_files=True,
            help="Upload the files: Products@FDA.csv, Applications.csv, Submissions.csv, MarketingStatus.csv, MarketingStatus_Lookup.csv"
        )

        if uploaded_files:
            files = {file.name: file for file in uploaded_files}
            required_columns = {
                # Your required columns here
                "Products@FDA.csv": ["ApplNo", "ProductNo", "Form", "Strength", "ReferenceDrug", "DrugName", "ActiveIngredient", "ReferenceStandard"],
                "Applications.csv": ["ApplNo", "ApplType", "ApplPublicNotes", "SponsorName"],
                "Submissions.csv": ["ApplNo", "SubmissionClassCodeID", "SubmissionType", "SubmissionNo", "SubmissionStatus", "SubmissionStatusDate", "SubmissionsPublicNotes", "ReviewPriority"],
                "MarketingStatus.csv": ["ApplNo", "ProductNo", "MarketingStatusID"],
                "MarketingStatus_Lookup.csv": ["MarketingStatusID", "MarketingStatusDescription"],            
            }

            dataframes = {}
            for filename, required_cols in required_columns.items():
                if filename in files:
                    df = check_columns(files[filename], required_cols)
                    if df is not None:
                        dataframes[filename] = df
                else:
                    st.warning(f"{filename} not uploaded.")

            if len(dataframes) == 5:
                # Process data and store it in session state
                st.session_state['processed_data_Drugs'] = process_data_Drugs(dataframes)

    if 'processed_data_Drugs' in st.session_state:
        merged_df = st.session_state['processed_data_Drugs']
        # Continue with displaying the processed data or further analysis...
        # Mutually Exclusive Filters
        form_options = ['All'] + sorted(merged_df['Form'].unique().tolist())
        drug_name_options = ['All'] + sorted(merged_df['DrugName'].unique().tolist())
        active_ingredient_options = ['All'] + sorted(merged_df['ActiveIngredient'].unique().tolist())
        appl_type_options = ['All'] + sorted(merged_df['ApplType'].astype(str).unique().tolist())
        sponsor_name_options = ['All'] + sorted(merged_df['SponsorName'].astype(str).unique().tolist())
        marketing_status_options = ['All'] + sorted(merged_df['MarketingStatusDescription'].astype(str).unique().tolist())
        submission_type_options = ['All'] + sorted(merged_df['SubmissionType'].astype(str).unique().tolist())
        review_priority_options = ['All'] + sorted(merged_df['ReviewPriority'].astype(str).unique().tolist())
        submission_status_options = ['All'] + sorted(merged_df['SubmissionStatus'].astype(str).unique().tolist())

        form_selection = st.selectbox("Form", options=form_options)
        drug_name_selection = st.selectbox("Drug Name", options=drug_name_options)
        active_ingredient_selection = st.selectbox("Active Ingredient", options=active_ingredient_options)
        appl_type_selection = st.selectbox("Application Type", options=appl_type_options)
        sponsor_name_selection = st.selectbox("Sponsor Name", options=sponsor_name_options)
        marketing_status_selection = st.selectbox("Marketing Status", options=marketing_status_options)
        submission_type_selection = st.selectbox("Submission Type", options=submission_type_options)
        review_priority_selection = st.selectbox("Review Priority", options=review_priority_options)
        submission_status_selection = st.selectbox("Submission Status", options=submission_status_options)

        # Apply filters
        if form_selection != 'All':
            merged_df = merged_df[merged_df['Form'] == form_selection]
        if drug_name_selection != 'All':
            merged_df = merged_df[merged_df['DrugName'] == drug_name_selection]
        if active_ingredient_selection != 'All':
            merged_df = merged_df[merged_df['ActiveIngredient'] == active_ingredient_selection]
        if appl_type_selection != 'All':
            merged_df = merged_df[merged_df['ApplType'] == appl_type_selection]
        if sponsor_name_selection != 'All':
            merged_df = merged_df[merged_df['SponsorName'] == sponsor_name_selection]
        if marketing_status_selection != 'All':
            merged_df = merged_df[merged_df['MarketingStatusDescription'] == marketing_status_selection]
        if submission_type_selection != 'All':
            merged_df = merged_df[merged_df['SubmissionType'] == submission_type_selection]
        if review_priority_selection != 'All':
            merged_df = merged_df[merged_df['ReviewPriority'] == review_priority_selection]
        if submission_status_selection != 'All':
            merged_df = merged_df[merged_df['SubmissionStatus'] == submission_status_selection]
        
        st.dataframe(merged_df)
        st.write(f"Filtered data count: {len(merged_df)}")
        # Example: Download button for processed data
        csv = convert_df_to_csv(merged_df)
        st.download_button(
            label="Download processed data as CSV",
            data=csv,
            file_name='processed_data_drugs@fda.csv',
            mime='text/csv',
        )
        
# Function to strip the last part of a string after a semicolon
def get_route_from_df_route(df_route_value):
    if pd.notnull(df_route_value) and ';' in df_route_value:
        return df_route_value.split(';')[-1]
    return None

# Define a function to calculate and store the number of patients per therapy type in thousands
def calculate_patients():
    # Access drug_treated_patients from the nested dictionary in session state
    drug_treated_patients = st.session_state['results']['drug_treated_patients']
    
    # Calculate the number of patients for each therapy type, converting results into thousands
    monotherapy = st.session_state.monotherapy_percentage / 100 * drug_treated_patients * 1000
    dual_therapy = st.session_state.dual_therapy_percentage / 100 * drug_treated_patients * 1000
    triple_therapy = st.session_state.triple_therapy_percentage / 100 * drug_treated_patients * 1000
    combo_injectable_therapy = st.session_state.combo_injectable_percentage / 100 * drug_treated_patients * 1000

    # Update session state with the calculated values
    st.session_state.update({
        "patients_on_monotherapy": monotherapy,
        "patients_on_dual_therapy": dual_therapy,
        "patients_on_triple_therapy": triple_therapy,
        "patients_on_combo_injectable_therapy": combo_injectable_therapy,
    })
    
# Function to load data from the uploaded file
def load_data_maturity(uploaded_file):
    return pd.read_csv(uploaded_file)  # Adjust this if your file is not a CSV

# Initialize dmf session state if not already initialized
if 'uploaded_file_name' not in st.session_state:
    st.session_state['uploaded_file_name'] = None
if 'data' not in st.session_state:
    st.session_state['data'] = None
    
# Example placeholder functions for the necessary functionality
def load_data_dmf(file):
    # Load the data without parsing dates initially
    data = pd.read_csv(file)
    
    # Check if 'SUBMIT DATE' column exists, then parse dates
    if 'SUBMIT DATE' in data.columns:
        data['SUBMIT DATE'] = pd.to_datetime(data['SUBMIT DATE'])
    
    return data

def check_required_columns_dmf(df, required_columns):
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        return False, missing_columns
    return True, None

def filter_data(data, status, type_filter, date_from, date_to, holder, subject, holder_sort, subject_sort):
    filtered = data.copy()
    
    if status != 'All':
        filtered = filtered[filtered['STATUS'] == status]
    
    if type_filter != 'All':
        filtered = filtered[filtered['TYPE'] == type_filter]
    
    # Convert date_from and date_to to datetime64
    date_from = pd.to_datetime(date_from)
    date_to = pd.to_datetime(date_to)
    
    # Check if 'SUBMIT DATE' column exists before filtering by date
    if 'SUBMIT DATE' in filtered.columns:
        filtered = filtered[(filtered['SUBMIT DATE'] >= date_from) & (filtered['SUBMIT DATE'] <= date_to)]
    
    if holder != 'All':
        filtered = filtered[filtered['HOLDER'] == holder]
    
    if 'All' not in subject:
        filtered = filtered[filtered['SUBJECT'].isin(subject)]
    
    if holder_sort != "None":
        filtered = filtered.sort_values(by='HOLDER', ascending=(holder_sort == "Ascending"))
    
    if subject_sort != "None":
        filtered = filtered.sort_values(by='SUBJECT', ascending=(subject_sort == "Ascending"))
    
    return filtered

  
# Define function to extract the town from the business address
def extract_town(address):
    if pd.notna(address):
        return address.split()[-1]
    return ''

# Function to load data and process it
def load_and_process_data(file):
    # Load the data
    df = pd.read_csv(file)
    
    # Select the required columns
    df = df[['Name', 'Gender', 'Registration Number', 'Qualification', 'Specialty', 'Business Address', 'Business Contact']]
    
    # Derive the Town column
    df['Town'] = df['Business Address'].apply(extract_town)
    
    return df

def display_main_application_content():
                        
    # Initialize mcaz_register as an empty DataFrame at the start
    mcaz_register = pd.DataFrame()       

    # Initialize the variable to None or an empty list
    selected_generic_names = []   

    # Sidebar for navigation
    menu = ['Data Overview', 'Market Analysis', 'Principal Analysis', 'FDA Orange Book Analysis', 
            'FDA Applicant Analysis', 'Drugs@FDA Analysis','Patient-flow Forecast', 'Drug Classification Analysis', 
            'Drugs with no Competition', 'Top Pharma Companies Sales', 'FDA Drug Establishment Sites', 
            'FDA NME & New Biologic Approvals', 'EMA FDA Health Canada Approvals 2023', 'FDA Filed DMFs',
           'Healthcare Practitioners']
    choice = st.sidebar.radio("Menu", menu)
    
    # File uploader
    uploaded_file = st.sidebar.file_uploader("Upload your MCAZ Register CSV file", type=["csv"])

    if uploaded_file is not None:
        # Load the data once and use it throughout
        data = load_data(uploaded_file)
        # Normalize column names immediately after loading
        data.columns = [str(col).strip() for col in data.columns]
        
        # Data Overview
        if choice == 'Data Overview':
            st.subheader('Data Overview')

            # Use the loaded and normalized 'data' directly
            mcaz_register = data.copy()
            st.session_state['mcaz_register'] = mcaz_register

            # Required columns
            required_columns_overview = [
                "Trade Name", "Generic Name", "Registration No", "Date Registered",
                "Expiry Date", "Form", "Categories for Distribution", "Strength",
                "Manufacturers", "Applicant Name", "Principal Name"
            ]

            # Check if all required columns exist in the data
            missing_columns = [col for col in required_columns_overview if col not in data.columns]
            if missing_columns:
                st.error(f"The following required columns are missing from the uploaded data: {', '.join(missing_columns)}")
                # Use a conditional block to stop further processing
                # At this point, you've informed the user what's wrong. You can prompt them to re-upload or fix the file.
                st.info("Please upload a file that includes all the required columns.")
            else:
            # Proceed with processing that depends on the presence of required columns
                        
                # Convert 'Date Registered' to datetime format
                data['Date Registered'] = pd.to_datetime(data['Date Registered'], format='%d/%m/%Y', errors='coerce')

                # Ensure 'Date Registered' is in datetime format
                if 'Date Registered' in data.columns:
                    try:
                        data['Date Registered'] = pd.to_datetime(data['Date Registered'])
                    except Exception as e:
                        st.error(f"Failed to convert 'Date Registered' to datetime: {e}")
                        
                # Filtering options
                if 'Manufacturers' in data.columns:
                    manufacturer_options = ['All Manufacturers'] + sorted(data['Manufacturers'].dropna().unique().tolist())
                    selected_manufacturer = st.selectbox('Select Manufacturer', manufacturer_options, index=0)

                data.columns = [str(col).strip() for col in data.columns]  # Strip whitespace from column names
                product_options = ['All Products'] + sorted(data['Generic Name'].dropna().unique().tolist())
                selected_product = st.selectbox('Select Generic Name', product_options, index=0)

                form_options = ['All Forms'] + sorted(data['Form'].dropna().unique().tolist())
                selected_form = st.selectbox('Select Form', form_options, index=0)

                # Multiselect widget for selecting one or more principal names
                principal_options = ['All Principal'] + sorted(data['Principal Name'].dropna().unique().tolist())
                selected_principals = st.multiselect('Select Principal Name(s)', principal_options, default=['All Principal'])

                category_options = ['All Categories of Distribution'] + sorted(data['Categories for Distribution'].dropna().unique().tolist())
                selected_category = st.selectbox('Select Category of Distribution', category_options, index=0)

                applicant_options = ['All Applicants'] + sorted(data['Applicant Name'].dropna().unique().tolist())
                selected_applicant = st.selectbox('Select Applicant Name', applicant_options, index=0)

                # Sort order options
                sort_order_generic_options = ['Ascending', 'Descending']
                selected_sort_order_generic = st.selectbox('Sort by Generic Name', sort_order_generic_options)

                sort_order_strength_options = ['Ascending', 'Descending']
                selected_sort_order_strength = st.selectbox('Sort by Strength', sort_order_strength_options)

                sort_order_date_registered_options = ['Ascending', 'Descending']
                selected_sort_order_date_registered = st.selectbox('Sort by Date Registered', sort_order_date_registered_options)

                # Filter data based on selections
                filtered_data = data.copy()
                if selected_manufacturer != 'All Manufacturers':
                    filtered_data = filtered_data[filtered_data['Manufacturers'] == selected_manufacturer]
                if selected_product != 'All Products':
                    filtered_data = filtered_data[filtered_data['Generic Name'] == selected_product]
                if selected_form != 'All Forms':
                    filtered_data = filtered_data[filtered_data['Form'] == selected_form]

                # Filter data based on the selection
                if 'All Principal' not in selected_principals:
                    filtered_data = filtered_data[filtered_data['Principal Name'].isin(selected_principals)]

                if selected_category != 'All Categories of Distribution':
                    filtered_data = filtered_data[filtered_data['Categories for Distribution'] == selected_category]
                if selected_applicant != 'All Applicants':
                    filtered_data = filtered_data[filtered_data['Applicant Name'] == selected_applicant]

                # Apply sorting based on the selected order
                sort_criteria = []
                ascending_order = []

                # Add sorting criteria based on user selection
                if selected_sort_order_generic:
                    sort_criteria.append('Generic Name')
                    ascending_order.append(selected_sort_order_generic == 'Ascending')

                if selected_sort_order_strength:
                    sort_criteria.append('Strength')
                    ascending_order.append(selected_sort_order_strength == 'Ascending')

                if selected_sort_order_date_registered:
                    sort_criteria.append('Date Registered')
                    ascending_order.append(selected_sort_order_date_registered == 'Ascending')

                # Apply sorting to the filtered data
                if sort_criteria:
                    filtered_data = filtered_data.sort_values(by=sort_criteria, ascending=ascending_order)

                # Convert the "Date Registered" column to the desired format (e.g., "01 December 2024")
                filtered_data['Date Registered'] = pd.to_datetime(filtered_data['Date Registered']).dt.strftime('%d %B %Y')

              
                # Display the filtered and sorted dataframe
                st.write("Filtered Data:")
                st.dataframe(filtered_data)
                st.write(f"Filtered data count: {len(filtered_data)}")      

                # Download Dataframe
                csv = convert_df_to_csv(filtered_data)
                st.download_button(label="Download Filtered Data as CSV", data=csv, file_name='filtered_data.csv', mime='text/csv')
                
            # Start of the Streamlit UI layout
            st.subheader("MCAZ Data Processing with Fuzzy Matching and ATC Code Extraction")

            medicine_type = st.radio("Select Medicine Type", ["Human Medicine", "Veterinary Medicine"])

            # Initialize or ensure session state variables are available
            if 'fuzzy_matched_data' not in st.session_state:
                st.session_state.fuzzy_matched_data = pd.DataFrame()
            if 'atc_level_data_mcaz' not in st.session_state:
                st.session_state.atc_level_data_mcaz = pd.DataFrame()
            if 'mcaz_register' not in st.session_state:
                st.session_state.mcaz_register = pd.DataFrame()

            mcaz_register_file = st.file_uploader("Upload MCAZ Register File", type=['csv'], key="mcaz_register_uploader")
            atc_index_file = st.file_uploader(f"Upload {'Human' if medicine_type == 'Human Medicine' else 'Veterinary'} ATC Index File", type=['csv'], key="atc_index_uploader_mcaz")

            if 'processed_rows_mcaz' not in st.session_state:
                st.session_state.processed_rows_mcaz = 0
            if 'resume_processing_mcaz' not in st.session_state:
                st.session_state.resume_processing = False

            if mcaz_register_file and atc_index_file:
                st.session_state.mcaz_register = load_file(mcaz_register_file)
                atc_index = load_file(atc_index_file)

                # Required columns for MCAZ register and ATC Index file
                required_mcaz_columns = ['Generic Name', 'Strength', 'Form', 'Categories for Distribution', 'Manufacturers', 'Applicant Name','Principal Name']
                required_atc_columns = ['ATCCode', 'Name']

                if not all(column in st.session_state.mcaz_register.columns for column in required_mcaz_columns):
                    st.error("MCAZ Register file is missing one or more required columns.")
                elif not all(column in atc_index.columns for column in required_atc_columns):
                    st.error("ATC Index file is missing one or more required columns.")
                else:
                    st.session_state.mcaz_register = init_columns(st.session_state.mcaz_register)
                    
                    # Add a new column 'route' by extracting the part after the semicolon in the 'Form' column
                    st.session_state.mcaz_register['route'] = st.session_state.mcaz_register['Form'].apply(lambda x: x.split(';')[-1] if pd.notnull(x) else None)

                    extract_atc_levels = extract_atc_levels_human if medicine_type == 'Human Medicine' else extract_atc_levels_veterinary
                    
                    # Proceed with processing only if all required columns are present
                    if st.button("Start/Resume MCAZ Processing", key="mcaz_resume"):
                        st.session_state.resume_processing_mcaz = True
                        process_data(st.session_state.mcaz_register, atc_index, extract_atc_levels)
            else:
                st.error("Please upload both MCAZ Register and ATC Index files to proceed.")

            if st.button("Reset MCAZ Processing", key="mcaz_reset"):
                for key in ['processed_rows_mcaz', 'resume_processing_mcaz', 'start_time_mcaz', 'processing_end_time_mcaz', 'fuzzy_matched_data', 'atc_level_data_mcaz', 'mcaz_register']:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
                    
            if 'fuzzy_matched_data' in st.session_state and not st.session_state.fuzzy_matched_data.empty:
                st.write("Updated MCAZ Register with Fuzzy Matching and ATC Codes:")
                st.dataframe(st.session_state.fuzzy_matched_data)

                csv_data = convert_df_to_csv(st.session_state.fuzzy_matched_data)
                st.download_button(label="Download MCAZ Register as CSV", data=csv_data, file_name='mcaz_register_with_atc_codes.csv', mime='text/csv')
            else:
                st.write("No processed data available for download or processing not yet started.")
                
            if st.session_state.fuzzy_matched_data is not None:
                try:
                    st.session_state.fuzzy_matched_data = st.session_state.fuzzy_matched_data[['Generic Name', 'Strength', 'Form', 'Categories for Distribution', 'Manufacturers', 'Principal Name', 'Best Match Name', 'Match Score', 'ATCCode']]

                    # Convert all strings in the DataFrame to uppercase
                    for column in st.session_state.fuzzy_matched_data.columns:
                        st.session_state.fuzzy_matched_data.loc[:, column] = st.session_state.fuzzy_matched_data.loc[:, column].map(lambda x: x.upper() if isinstance(x, str) else x)

                    # Assuming extract_atc_levels_human and extract_atc_levels_veterinary are defined
                    extract_atc_levels = extract_atc_levels_human if medicine_type == 'Human Medicine' else extract_atc_levels_veterinary

                    # Apply the function to each ATC code in the DataFrame
                    atc_data = st.session_state.fuzzy_matched_data['ATCCode'].apply(lambda x: pd.Series(extract_atc_levels(x)))
                    atc_data.columns = ['ATCLevelOneCode', 'ATCLevelTwoCode', 'ATCLevelThreeCode', 'ATCLevelFourCode']
                    st.session_state.fuzzy_matched_data = pd.concat([st.session_state.fuzzy_matched_data, atc_data], axis=1)

                    st.session_state.atc_level_data_mcaz = st.session_state.fuzzy_matched_data

                    if not st.session_state.atc_level_data_mcaz.empty:
                        st.write("Updated MCAZ Register with ATC Level Codes:")
                        st.dataframe(st.session_state.atc_level_data_mcaz)

                        # Download file
                        csv = convert_df_to_csv(st.session_state.atc_level_data_mcaz)
                        st.download_button(label="Download MCAZ Register as CSV", data=csv, file_name='mcaz_register_with_ATC_Level_Codes.csv', mime='text/csv', key='download_updated_register')
                except KeyError as e:
                    print(f"Column not found in DataFrame: {e}")
            else:
                print("mcaz_register is None. Please check data loading and processing steps.")

            # Streamlit UI layout for ATC Code Description Integration and Filtering
            st.subheader("ATC Code Description Integration and Filtering")
            
            # Initialize session state for check_passed
            if 'check_passed' not in st.session_state:
                st.session_state['check_passed'] = False

            # Initialize variables for ATC data and filter variables
            atc_one = atc_two = atc_three = atc_four = None
            atc_one_desc = atc_two_desc = atc_three_desc = atc_four_desc = selected_generic_names = []

            # Required columns for each ATC level
            required_columns_atc_one = ['ATCLevelOneCode', 'ATCLevelOneDescript']
            required_columns_atc_two = ['ATCLevelTwoCode', 'ATCLevelTwoDescript']
            required_columns_atc_three = ['ATCLevelThreeCode', 'ATCLevelThreeDescript']
            required_columns_atc_four = ['ATCLevelFourCode', 'Chemical Subgroup']

            # File uploaders for ATC level description files
            atc_one_file = st.file_uploader("Upload ATC Level One Description File", type=['csv'], key="atc_one_uploader_one")
            atc_two_file = st.file_uploader("Upload ATC Level Two Description File", type=['csv'], key="atc_two_uploader_two")
            atc_three_file = st.file_uploader("Upload ATC Level Three Description File", type=['csv'], key="atc_three_uploader_three")
            atc_four_file = st.file_uploader("Upload ATC Level Four Description File", type=['csv'], key="atc_four_uploader_four")

            # Button to trigger the check operation
            check_data = st.button("Check Required Columns")

            if check_data:
                # Reset the check_passed flag
                st.session_state['check_passed'] = True

                # Load ATC description files if uploaded
                atc_one = safe_load_csv(atc_one_file) if atc_one_file else None
                atc_two = safe_load_csv(atc_two_file) if atc_two_file else None
                atc_three = safe_load_csv(atc_three_file) if atc_three_file else None
                atc_four = safe_load_csv(atc_four_file) if atc_four_file else None

                # Check for required columns in each ATC level description file
                check_required_columns(atc_one, required_columns_atc_one, "One")
                check_required_columns(atc_two, required_columns_atc_two, "Two")
                check_required_columns(atc_three, required_columns_atc_three, "Three")
                check_required_columns(atc_four, required_columns_atc_four, "Four")
                
            else:
                st.info("Please upload ATC level description files and press 'Check Required Columns'.")

            # Button to trigger the merge operation
            merge_data = st.button("Merge Data")

            if merge_data:
                if 'fuzzy_matched_data' in st.session_state and not st.session_state.fuzzy_matched_data.empty:
                    if st.session_state['check_passed']:  # Check if all required columns are present
                        # Your merging logic here...
                        # Load ATC description files if uploaded
                        atc_one = safe_load_csv(atc_one_file) if atc_one_file else None
                        atc_two = safe_load_csv(atc_two_file) if atc_two_file else None
                        atc_three = safe_load_csv(atc_three_file) if atc_three_file else None
                        atc_four = safe_load_csv(atc_four_file) if atc_four_file else None
                        
                        # Retrieve the fuzzy_matched_data from session state
                        mcaz_register =  st.session_state.atc_level_data_mcaz

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

                        # Correctly update the session state with the merged data
                        st.session_state['mcaz_with_ATCCodeDescription'] = mcaz_register
                        st.success("Data merged with ATC level descriptions.")

                        # Display the merged dataframe
                        if not mcaz_register.empty:
                            st.write("Merged Data:")
                            st.dataframe(mcaz_register)
                        else:
                            st.write("No data to display after merging.")

                        st.success("Data merged with ATC level descriptions.")
                    else:
                        st.error("Cannot merge data. Please ensure all required columns are present and try again.")
                else:
                    st.warning("Please complete the fuzzy matching process and ensure ATC level description files are uploaded.")

            # Download file
            csv = convert_df_to_csv(mcaz_register)
            if csv is not None:
                # Proceed with operations that use 'csv'
                st.download_button(label="Download MCAZ Register as CSV", data=csv, file_name='mcaz_register_with_atc_description.csv', mime='text/csv', key='download_mcaz_withatcdescription')

            else:
                # Handle the case where 'csv' is None, e.g., display a message or take alternative action
                print("No data available to convert to CSV")
                
            # Define filter options for ATC Levels and Principal
            atc_filter_options = ["None", "ATCLevelOneDescript", "ATCLevelTwoDescript", "ATCLevelThreeDescript", "Chemical Subgroup"]
            principal_filter_options = ["None", "Principal Name"]

            # Let user select filters
            selected_atc_filter = st.radio("Select an ATC filter", atc_filter_options)
            selected_principal_filter = st.radio("Select a Principal filter", principal_filter_options)

            # Check if data is in session state and is not empty
            if 'mcaz_with_ATCCodeDescription' in st.session_state and not st.session_state['mcaz_with_ATCCodeDescription'].empty:
                # Start with the full dataset to handle scope
                filtered_data = st.session_state['mcaz_with_ATCCodeDescription'].copy()

                filter_message = "Filtered Data:"

                # Filter by ATC Level if selected
                if selected_atc_filter != "None":
                    atc_filter_values = sorted(filtered_data[selected_atc_filter].astype(str).unique())
                    selected_atc_values = st.multiselect(f"Select {selected_atc_filter}", atc_filter_values)
                    if selected_atc_values:
                        filtered_data = filtered_data[filtered_data[selected_atc_filter].astype(str).isin(selected_atc_values)]
                        filter_message += f" {selected_atc_filter} ({', '.join(selected_atc_values)})"

                # Filter by Principal Name if selected
                if selected_principal_filter != "None":
                    principal_filter_values = sorted(filtered_data['Principal Name'].astype(str).unique())
                    selected_principal_values = st.multiselect("Select Principal Name", principal_filter_values)
                    if selected_principal_values:
                        filtered_data = filtered_data[filtered_data['Principal Name'].astype(str).isin(selected_principal_values)]
                        if "Filtered Data:" in filter_message:
                            filter_message += " and"
                        filter_message += f" Principal Name ({', '.join(selected_principal_values)})"

                # Display selected filters
                if selected_atc_filter == "None" and selected_principal_filter == "None":
                    st.write("Displaying unfiltered data:")
                else:
                    st.write(filter_message + ":")

                # Display filtered data and count
                st.dataframe(filtered_data)
                st.write(f"Filtered data count: {len(filtered_data)}")

                # Offer CSV download for filtered data
                csv = convert_df_to_csv(filtered_data)
                st.download_button(label="Download Filtered Data as CSV", data=csv, file_name='mcaz_register_filtered.csv', mime='text/csv', key='download_filtered')
            else:
                st.write("No data loaded or data is empty.")
                  
            # Medicine type selection
            medicine_type_options = ["Select Medicine Type", "Human Medicine", "Veterinary Medicine"]
            selected_medicine_type = st.selectbox("Select Medicine Type", medicine_type_options)

            # Initialize an empty DataFrame for mcaz_register to handle its scope outside the if condition
            mcaz_register = pd.DataFrame()

            # Only proceed with user type filtering if "Human Medicine" is selected and data has been merged
            if selected_medicine_type == "Human Medicine":
                user_type_options = ["None", "Local Manufacturer", "Importer"]
                user_type = st.radio("Select User Type", user_type_options)

                prohibited_file = st.file_uploader("Upload Prohibited Generics List With Dosage Forms", type=['csv'])

                if prohibited_file is not None:
                    # Attempt to read the uploaded file for column verification
                    try:
                        temp_df = pd.read_csv(prohibited_file)
                        # Reset the file pointer after reading
                        prohibited_file.seek(0)
                        required_columns = ['Generic Name', 'Form']
                        check_passed, missing_columns = check_prohibited_file_columns(temp_df, required_columns)
                        if check_passed:
                            st.success("Uploaded file contains all required columns.")
                        else:
                            st.error(f"Uploaded file is missing required columns: {', '.join(missing_columns)}")
                            # Skip further processing if required columns are missing
                            prohibited_file = None
                    except Exception as e:
                        st.error(f"An error occurred while processing the file: {str(e)}")
                        prohibited_file = None

                filter_options = ["None", "ATCLevelOneDescript", "ATCLevelTwoDescript", 
                                  "ATCLevelThreeDescript", "Chemical Subgroup", "Generic Name"]
                selected_filter = st.radio("Select an additional filter", filter_options)

                if 'mcaz_with_ATCCodeDescription' in st.session_state and not st.session_state['mcaz_with_ATCCodeDescription'].empty:
                    mcaz_register = st.session_state['mcaz_with_ATCCodeDescription']

                    if prohibited_file and user_type != "None":
                        prohibited_generics = load_and_process_prohibited_generics(prohibited_file)
                        mcaz_register = filter_data_for_user(user_type, mcaz_register, prohibited_generics)
                        mcaz_register = mcaz_register.drop_duplicates()

                    if selected_filter != "None":
                        filter_values = sorted(mcaz_register[selected_filter].astype(str).unique())
                        selected_values = st.multiselect(f"Select {selected_filter}", filter_values, key="valid")

                        if selected_values:
                            mcaz_register = mcaz_register[mcaz_register[selected_filter].astype(str).isin(selected_values)]

                    st.write("Filtered Data:")
                    st.dataframe(mcaz_register)
                    st.write(f"Filtered data count: {len(mcaz_register)}")

                    csv = convert_df_to_csv(mcaz_register)
                    if csv is not None:
                        st.download_button(label="Download MCAZ Register as CSV", data=csv, file_name='mcaz_register_prohibited_medicine.csv', mime='text/csv', key='download_mcaz_filtered')
                else:
                    st.error("Data not available in the session state or no data to display after filtering.")
            else:
                st.error("Select 'Human Medicine' to access user type based data filtering.")
       
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
            generic_name_counts = data['Generic Name'].value_counts()

            # Display the counts
            st.write(f"Total unique generic names: {unique_generic_name_count}")
            st.write("Top Generic Names by Count:")
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
            
            # Streamlit widget to upload the Prohibited Medicines file
            uploaded_prohibited_file = st.file_uploader("Upload Prohibited Medicines file With Strength and Dosage Form", type=['csv'])
            
            # Required columns
            required_columns = ['Generic Name', 'Strength', 'Form']

            # Check for required columns if a file is uploaded
            file_check_passed, missing_columns = check_required_columns_in_file(uploaded_prohibited_file, required_columns)

            if file_check_passed is True:
                st.success("Uploaded file contains all required columns.")
            elif file_check_passed is False:
                st.error(f"Uploaded file is missing required columns: {', '.join(missing_columns)}")
            elif file_check_passed is None and uploaded_prohibited_file is not None:
                st.warning("Please upload a file to proceed.")

            # Assuming you have a variable to capture the user type
            user_type = st.selectbox('Select User Type', ['None', 'Importer', 'Local Manufacturer'])
            
            if uploaded_prohibited_file is not None:
                uploaded_prohibited_file.seek(0)  # Reset file pointer to the start
                try:
                    # Attempt to load the Prohibited Medicines file
                    prohibited_medicines_df = pd.read_csv(uploaded_prohibited_file)

                    # Ensure the DataFrame is not empty by checking if it has columns
                    if prohibited_medicines_df.empty:
                        st.error("Uploaded file is empty or does not contain any data.")
                    else:
                        # Convert column names to uppercase to match the MCAZ Register
                        prohibited_medicines_df.columns = prohibited_medicines_df.columns.str.upper()
                
                        # Combine 'GENERIC NAME', 'STRENGTH', and 'FORM' to match the 'Combined' format in your data dataframe
                        prohibited_medicines_df['COMBINED'] = prohibited_medicines_df['GENERIC NAME'] + " - " + prohibited_medicines_df['STRENGTH'].astype(str) + " - " + prohibited_medicines_df['FORM']

                        # Example to integrate the prohibited medicines filter based on the user type
                        if user_type == 'Importer':
                            # Assuming 'filtered_counts' is already defined in your code with the counts of unique products
                            # First, ensure 'filtered_counts' is in a format that can be filtered (e.g., a DataFrame)

                            # Exclude prohibited medicines for importers
                            prohibited_list = prohibited_medicines_df['COMBINED'].tolist()
                            filtered_counts = filtered_counts[~filtered_counts.index.isin(prohibited_list)]

                            # Display the filtered 'filtered_counts' DataFrame
                            st.write(filtered_counts)
                            
                            # Download button for unique product count
                            if not filtered_counts.empty:
                                csv = filtered_counts.to_csv(index=False)
                                st.download_button("Download Unique Products Data", csv, "unique_products_importer_data.csv", "text/csv", key='download-unique-product_importer')

                    
                except Exception as e:
                    # This will catch all exceptions, including any related to empty data or parsing issues
                    st.error(f"An error occurred while processing the file: {str(e)}")
                    
            # Add a subheader for the new section
            st.subheader("Portfolio Maturity Analysis")

            # Ensure all entries in the 'Principal Name' and 'Generic Name' columns are strings
            data['Principal Name'] = data['Principal Name'].astype(str)
            data['Generic Name'] = data['Generic Name'].astype(str)

            # Calculate the age of each product in years
            today = datetime.today()
            data['Age since Registration'] = data['Date Registered'].apply(lambda x: (today - pd.to_datetime(x)).days / 365)

            # Filter options for Principal Name, sorted in ascending order
            principal_filter_options = ['All'] + sorted(data['Principal Name'].unique(), reverse=False)
            selected_principal = st.selectbox("Filter by Principal Name", principal_filter_options)

            # Filter options for Generic Name, sorted in ascending order
            generic_filter_options = ['All'] + sorted(data['Generic Name'].unique(), reverse=False)
            selected_generic = st.selectbox("Filter by Generic Name", generic_filter_options)

            # Apply the filters
            filtered_data = data
            if selected_principal != 'All':
                filtered_data = filtered_data[filtered_data['Principal Name'] == selected_principal]

            if selected_generic != 'All':
                filtered_data = filtered_data[filtered_data['Generic Name'] == selected_generic]

            # Display the filtered dataframe
            st.dataframe(filtered_data[['Trade Name', 'Generic Name','Strength','Form' ,'Principal Name', 'Age since Registration']])

            # Calculate and display the average age of the product portfolio
            average_age = filtered_data['Age since Registration'].mean()
            st.write(f"Average Age of Product Portfolio: {average_age:.2f} years")
                   
        # Principal Analysis
        elif choice == 'Principal Analysis':
            st.subheader('Principal Analysis')

            # Ensure all manufacturers are strings and handle NaN values
            all_manufacturers = data['Principal Name'].dropna().unique()
            all_manufacturers = [str(manufacturer) for manufacturer in all_manufacturers]
            all_manufacturers.sort()

            # Adding 'All Manufacturers' option
            manufacturers_options = ['All Principals'] + all_manufacturers
            selected_manufacturer = st.selectbox('Select Principal', manufacturers_options, index=0)

            # Filtering data based on the selected principal
            if selected_manufacturer == 'All Principals':
                filtered_data = data
            else:
                filtered_data = data[data['Principal Name'] == selected_manufacturer]

            # Convert 'Date Registered' to datetime
            filtered_data['Date Registered'] = pd.to_datetime(filtered_data['Date Registered'], format='%m/%d/%Y', errors='coerce')
#             filtered_data['Date Registered'] = pd.to_datetime(filtered_data['Date Registered'])
            
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
#                 mcaz_register = mcaz_register.drop_duplicates()

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
#                 mcaz_register = mcaz_register.drop_duplicates()

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
#                 mcaz_register = mcaz_register.drop_duplicates()

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

        # FDA Orange Book Analysis
        elif choice == 'FDA Orange Book Analysis':
            # Check if the dataframes are already loaded in the session state
            if 'products_df' not in st.session_state or 'patent_df' not in st.session_state or 'exclusivity_df' not in st.session_state:
                st.title("FDA Orange Book Analysis")

                # File uploaders
                products_file = st.file_uploader("Upload the products.csv file", type=['csv'], key="products_uploader")
                patent_file = st.file_uploader("Upload the patent.csv file", type=['csv'], key="patent_uploader")
                exclusivity_file = st.file_uploader("Upload the exclusivity.csv file", type=['csv'], key="exclusivity_uploader")


                # Check for required columns in each dataframe
                products_columns_required = ['Ingredient', 'DF;Route', 'Trade_Name', 'Applicant', 'Strength']
                patent_columns_required = ['Appl_Type', 'Appl_No', 'Product_No', 'Patent_No', 'Patent_Expire_Date_Text', 'Drug_Substance_Flag', 'Drug_Product_Flag', 'Patent_Use_Code', 'Delist_Flag', 'Submission_Date']
                exclusivity_columns_required = ['Appl_Type', 'Appl_No', 'Product_No', 'Exclusivity_Code', 'Exclusivity_Date']
                
                # Initialize a flag to indicate all required files are uploaded
                all_files_uploaded = True

                # Attempt to load the products file
                if products_file:
                    products_df = load_data_orange(products_file)
                    products_check, products_missing = check_required_columns_orangebook(products_df, products_columns_required) if products_df is not None else (False, ["DataFrame is None"])
                    if not products_check:
                        st.error(f"Missing columns in products file: {', '.join(products_missing)}. Please upload a correct file.")
                else:
                    st.error("Products file is not uploaded.")
                    all_files_uploaded = False

                # Attempt to load the patent file
                if patent_file:
                    patent_df = load_data_orange(patent_file)
                    patent_check, patent_missing = check_required_columns_orangebook(patent_df, patent_columns_required) if patent_df is not None else (False, ["DataFrame is None"])
                    if not patent_check:
                        st.error(f"Missing columns in patent file: {', '.join(patent_missing)}. Please upload a correct file.")
                else:
                    st.error("Patent file is not uploaded.")
                    all_files_uploaded = False

                # Attempt to load the exclusivity file
                if exclusivity_file:
                    exclusivity_df = load_data_orange(exclusivity_file)
                    exclusivity_check, exclusivity_missing = check_required_columns_orangebook(exclusivity_df, exclusivity_columns_required) if exclusivity_df is not None else (False, ["DataFrame is None"])
                    if not exclusivity_check:
                        st.error(f"Missing columns in exclusivity file: {', '.join(exclusivity_missing)}. Please upload a correct file.")
                else:
                    st.error("Exclusivity file is not uploaded.")
                    all_files_uploaded = False

                # Only proceed if all files are correctly uploaded and loaded
                if all_files_uploaded:
                    # Store the dataframes in the session state or proceed with further processing
                    st.session_state.products_df = products_df if 'products_df' in locals() else None
                    st.session_state.patent_df = patent_df if 'patent_df' in locals() else None
                    st.session_state.exclusivity_df = exclusivity_df if 'exclusivity_df' in locals() else None
            
            # If the dataframes are in the session state, proceed with the analysis
            if 'products_df' in st.session_state and 'patent_df' in st.session_state and 'exclusivity_df' in st.session_state:
                # Perform the analysis using the dataframes from the session state
                merged_df = outer_join_dfs(st.session_state.products_df, st.session_state.patent_df, st.session_state.exclusivity_df, "Appl_No")

                # Remove duplicates
                merged_df = merged_df.drop_duplicates(subset=['Ingredient', 'DF;Route', 'Strength', 'Appl_No', 'Product_No_x', 'Patent_No'])

                # Remove records with "Type" equal to "DISCN"
                merged_df = merged_df[merged_df['Type'] != 'DISCN']
                               
                # To ensure the changes are applied to the original DataFrame in-place, you can use:
                merged_df.sort_values(by='Ingredient', ascending=True, inplace=True)
                
#                 # Step 1: Identify Ingredients with mixed TE_Code values
#                 ingredient_te_code = merged_df.groupby(['Ingredient', 'DF;Route'])['TE_Code'].apply(lambda x: x.notna().any() and x.isna().any())
#                 mixed_te_code_ingredients = ingredient_te_code[ingredient_te_code].index
                              
                # Step 1: Identify Ingredients with mixed TE_Code values
                ingredient_te_code = merged_df.groupby('Ingredient')['TE_Code'].apply(lambda x: x.notna().any() and x.isna().any())
                mixed_te_code_ingredients = ingredient_te_code[ingredient_te_code].index
                
                # Step 2: Filter out these Ingredients
                merged_df = merged_df[~merged_df['Ingredient'].isin(mixed_te_code_ingredients)]

                # Retain records with no TE_Code in the original DataFrame
                merged_df = merged_df[merged_df['TE_Code'].isna()]
        
                # Remove records with no patents
                merged_df = merged_df.dropna(subset=['Patent_No'])
                                               
                # Convert 'Patent_No' column to string
                merged_df['Patent_No'] = merged_df['Patent_No'].astype(str)
                
                # Strip the trailing '.0' from 'Patent_No' column
                merged_df['Patent_No'] = merged_df['Patent_No'].str.rstrip('.0')

                # Filters
                ingredient = st.selectbox("Select Ingredient", ['None'] + sorted(merged_df['Ingredient'].dropna().unique().tolist()))
                df_route = st.selectbox("Select DF;Route", ['None'] + sorted(merged_df['DF;Route'].dropna().unique().tolist()))
                trade_name = st.selectbox("Select Trade Name", ['None'] + sorted(merged_df['Trade_Name'].dropna().unique().tolist()))
                applicant = st.selectbox("Select Applicant", ['None'] + sorted(merged_df['Applicant'].dropna().unique().tolist()))
                appl_type = st.selectbox("Select Appl Type", ['None'] + sorted(merged_df['Appl_Type'].dropna().unique().tolist()))
                type_filter = st.selectbox("Select Type", ['None'] + sorted(merged_df['Type'].dropna().unique().tolist()))
                rld = st.selectbox("Select Rerence Listed Drug", ['None'] + sorted(merged_df['RLD'].dropna().unique().tolist()))
                rs = st.selectbox("Select Reference Standard", ['None'] + sorted(merged_df['RS'].dropna().unique().tolist()))
                drug_product_flag = st.selectbox("Select Drug Product Flag", ['None'] + sorted(merged_df['Drug_Product_Flag'].dropna().unique().tolist()))
                drug_substance_flag = st.selectbox("Select Drug Substance Flag", ['None'] + sorted(merged_df['Drug_Substance_Flag'].dropna().unique().tolist()))

                # Apply filters
                if ingredient != "None": merged_df = filter_dataframe(merged_df, 'Ingredient', ingredient)
                if df_route != "None": merged_df = filter_dataframe(merged_df, 'DF;Route', df_route)
                if trade_name != "None": merged_df = filter_dataframe(merged_df, 'Trade_Name', trade_name)
                if applicant != "None": merged_df = filter_dataframe(merged_df, 'Applicant', applicant)
                if appl_type != "None": merged_df = filter_dataframe(merged_df, 'Appl_Type', appl_type)
                if type_filter != "None": merged_df = filter_dataframe(merged_df, 'Type', type_filter)
                if rld != "None": merged_df = filter_dataframe(merged_df, 'RLD', rld)
                if rs != "None": merged_df = filter_dataframe(merged_df, 'RS', rs)
                if drug_product_flag != "None": merged_df = filter_dataframe(merged_df, 'Drug_Product_Flag', drug_product_flag)
                if drug_substance_flag != "None": merged_df = filter_dataframe(merged_df, 'Drug_Substance_Flag', drug_substance_flag)

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
                    'Patent_Expire_Date_Text', 'Drug_Product_Flag'
                ]

                # Select only the specified columns
                merged_df = merged_df[filtered_columns]
                
                # Convert 'Patent_No' column to string
                merged_df['Patent_No'] = merged_df['Patent_No'].astype(str)

                # Strip the trailing '.0' from 'Patent_No' column
                merged_df['Patent_No'] = merged_df['Patent_No'].str.rstrip('.0')
                
                # Check if an ingredient is selected
                if ingredient != "None":
                    # Google Patents base URL
                    google_patents_base_url = "https://patents.google.com/patent/"
                    # WIPO base URL
                    base_url = "https://patentscope.wipo.int/search/en/search.jsf?query="
                                                           
                    # Construct Google Patents link
                    merged_df['Google_Patents_Link'] = merged_df['Patent_No'].apply(lambda x: f'<a href="{google_patents_base_url}US{x}B2/en?oq={x}" target="_blank">US{x}B2 on Google Patents</a>')

                    # Construct WIPO link (assuming WIPO docId format is compatible with your Patent_No format; adjust as needed)
#                     merged_df['WIPO_Patent_Link'] = merged_df['Patent_No'].apply(lambda x: f'<a href="{base_url}{x}" target="_blank">{x}</a>')
                    merged_df['WIPO_Link'] = merged_df['Patent_No'].apply(construct_wipo_link)

                    
                    # Apply the function to the 'Patent_No' column to create a new 'Espacenet_Link' column
                    merged_df['Espacenet_Link'] = merged_df['Patent_No'].apply(construct_espacenet_link)

                    # Filter the DataFrame based on the selected ingredient
                    filtered_df = merged_df[merged_df['Ingredient'] == ingredient]

                    # HTML Style for left alignment of the link columns
                    left_align_style = "<style>td { text-align: left !important; }</style>"

                    # Display the DataFrame with hyperlinks for the selected ingredient
                    st.write(f"DataFrame with Hyperlinked Patent Numbers for Ingredient: {ingredient}")
                    st.markdown(left_align_style + filtered_df.to_html(escape=False, index=False), unsafe_allow_html=True)
                else:
                    st.write("Please select an ingredient to display detailed information.")
                    
                
            # Start of the Streamlit UI layout
            st.subheader("FDA Data Processing with Fuzzy Matching and ATC Code Extraction")

            medicine_type = st.radio("Select Medicine Type", ["Human Medicine", "Veterinary Medicine"])

            # Initialize or ensure session state variables are available
            if 'fuzzy_matched_data_fda' not in st.session_state:
                st.session_state.fuzzy_matched_data_fda = pd.DataFrame()
            if 'atc_level_data' not in st.session_state:
                st.session_state.atc_level_data = pd.DataFrame()
            if 'fda_register' not in st.session_state:
                st.session_state.fda_register = pd.DataFrame()

            fda_register_file = st.file_uploader("Upload FDA Register File", type=['csv'], key="fda_register_uploader")
            atc_index_file = st.file_uploader(f"Upload {'Human' if medicine_type == 'Human Medicine' else 'Veterinary'} ATC Index File", type=['csv'], key="atc_index_uploader_fda")

            if 'fda_processed_rows' not in st.session_state:
                st.session_state.fda_processed_rows = 0
            if 'fda_resume_processing' not in st.session_state:
                st.session_state.fda_resume_processing = False

            if fda_register_file and atc_index_file:
                st.session_state.fda_register = load_file(fda_register_file)
                atc_index = load_file(atc_index_file)

                # Check for required columns in both files
                required_fda_columns = ['Ingredient', 'DF;Route', 'Strength', 'Trade_Name', 'Applicant']
                required_atc_columns = ['ATCCode', 'Name']

                if not all(column in st.session_state.fda_register.columns for column in required_fda_columns):
                    st.error("FDA Register file is missing one or more required columns.")
                elif not all(column in atc_index.columns for column in required_atc_columns):
                    st.error("ATC Index file is missing one or more required columns.")
                else:
                    st.session_state.fda_register = init_columns(st.session_state.fda_register)
                    
                     # Attempt to add the 'route' column only if 'DF;Route' exists
                    if 'DF;Route' in st.session_state.fda_register.columns:
                        # Add the 'route' column
                        st.session_state.fda_register['route'] = st.session_state.fda_register['DF;Route'].apply(
                            lambda x: x.split(';')[-1] if pd.notnull(x) and ';' in x else x
                        )


                    extract_atc_levels = extract_atc_levels_human if medicine_type == 'Human Medicine' else extract_atc_levels_veterinary
                    
                    # Proceed with processing only if all required columns are present
                    if st.button("Start/Resume FDA Processing", key="start_resume_fda"):
                        st.session_state.fda_resume_processing = True
                        process_data_fda(st.session_state.fda_register, atc_index, extract_atc_levels)
            else:
                st.error("Please upload both FDA Register and ATC Index files to proceed.")

            if st.button("Reset FDA Processing", key="reset_fda"):
                for key in ['fda_processed_rows', 'fda_resume_processing', 'start_time', 'end_time', 'fuzzy_matched_data_fda', 'atc_level_data', 'st.session_state.fda_register']:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
                    
            if 'fuzzy_matched_data_fda' in st.session_state and not st.session_state.fuzzy_matched_data_fda.empty:
                st.write("Updated FDA Register with Fuzzy Matching and ATC Codes:")
                st.dataframe(st.session_state.fuzzy_matched_data_fda)

                csv_data = convert_df_to_csv(st.session_state.fuzzy_matched_data_fda)
                st.download_button(label="Download FDA Register as CSV", data=csv_data, file_name='fda_register_with_atc_codes.csv', mime='text/csv')
            else:
                st.write("No processed data available for download or processing not yet started.")
                
            if st.session_state.fuzzy_matched_data_fda is not None:
                try:
                    st.session_state.fuzzy_matched_data_fda = st.session_state.fuzzy_matched_data_fda[['Ingredient', 'DF;Route', 'Strength', 'Trade_Name', 'Applicant', 'Best Match Name', 'Match Score', 'ATCCode']]

                    # Convert all strings in the DataFrame to uppercase
                    for column in st.session_state.fuzzy_matched_data_fda.columns:
                        st.session_state.fuzzy_matched_data_fda[column] = st.session_state.fuzzy_matched_data_fda[column].map(lambda x: x.upper() if isinstance(x, str) else x)

                    # Assuming extract_atc_levels_human and extract_atc_levels_veterinary are defined
                    extract_atc_levels = extract_atc_levels_human if medicine_type == 'Human Medicine' else extract_atc_levels_veterinary

                    # Apply the function to each ATC code in the DataFrame
                    atc_data = st.session_state.fuzzy_matched_data_fda['ATCCode'].apply(lambda x: pd.Series(extract_atc_levels(x)))
                    atc_data.columns = ['ATCLevelOneCode', 'ATCLevelTwoCode', 'ATCLevelThreeCode', 'ATCLevelFourCode']
                    st.session_state.fuzzy_matched_data_fda = pd.concat([st.session_state.fuzzy_matched_data_fda, atc_data], axis=1)

                    st.session_state.atc_level_data = st.session_state.fuzzy_matched_data_fda

                    if not st.session_state.atc_level_data.empty:
                        st.write("Updated FDA Register with ATC Level Codes:")
                        st.dataframe(st.session_state.atc_level_data)

                        # Download file
                        csv = convert_df_to_csv(st.session_state.atc_level_data)
                        st.download_button(label="Download FDA Register as CSV", data=csv, file_name='fda_register_with_ATC_Level_Codes.csv', mime='text/csv', key='download_fda_updated_register')
                except KeyError as e:
                    print(f"Column not found in DataFrame: {e}")
            else:
                print("fda_register is None. Please check data loading and processing steps.")
                
            # Streamlit UI layout for ATC Code Description Integration and Filtering
            st.subheader("FDA Orange Book ATC Code Description Integration and Filtering")

            # Initialize session state for check_passed
            if 'check_passed' not in st.session_state:
                st.session_state['check_passed'] = False

            # Initialize variables for ATC data and filter variables
            atc_one = atc_two = atc_three = atc_four = None
            atc_one_desc = atc_two_desc = atc_three_desc = atc_four_desc = selected_generic_names = []

            # Required columns for each ATC level
            required_columns_atc_one = ['ATCLevelOneCode', 'ATCLevelOneDescript']
            required_columns_atc_two = ['ATCLevelTwoCode', 'ATCLevelTwoDescript']
            required_columns_atc_three = ['ATCLevelThreeCode', 'ATCLevelThreeDescript']
            required_columns_atc_four = ['ATCLevelFourCode', 'Chemical Subgroup']

            # File uploaders for ATC level description files
            atc_one_file = st.file_uploader("Upload ATC Level One Description File", type=['csv'], key="atc_one_uploader_one_fda")
            atc_two_file = st.file_uploader("Upload ATC Level Two Description File", type=['csv'], key="atc_two_uploader_two_fda")
            atc_three_file = st.file_uploader("Upload ATC Level Three Description File", type=['csv'], key="atc_three_uploader_three_fda")
            atc_four_file = st.file_uploader("Upload ATC Level Four Description File", type=['csv'], key="atc_four_uploader_four_fda")

            # Button to trigger the check operation
            check_data = st.button("Check Required Columns", key = "fda_data")

            if check_data:
                # Reset the check_passed flag
                st.session_state['check_passed'] = True

                # Load ATC description files if uploaded
                atc_one = safe_load_csv(atc_one_file) if atc_one_file else None
                atc_two = safe_load_csv(atc_two_file) if atc_two_file else None
                atc_three = safe_load_csv(atc_three_file) if atc_three_file else None
                atc_four = safe_load_csv(atc_four_file) if atc_four_file else None

                # Check for required columns in each ATC level description file
                check_required_columns(atc_one, required_columns_atc_one, "One")
                check_required_columns(atc_two, required_columns_atc_two, "Two")
                check_required_columns(atc_three, required_columns_atc_three, "Three")
                check_required_columns(atc_four, required_columns_atc_four, "Four")
                
            else:
                st.info("Please upload ATC level description files and press 'Check Required Columns'.")

            # Button to trigger the merge operation
            merge_data = st.button("Merge Data", key = "fda_merge")

            if merge_data:
                if 'fuzzy_matched_data_fda' in st.session_state and not st.session_state.fuzzy_matched_data_fda.empty:
                    if st.session_state['check_passed']:  # Check if all required columns are present
                        # Your merging logic here...
                        # Load ATC description files if uploaded
                        atc_one = safe_load_csv(atc_one_file) if atc_one_file else None
                        atc_two = safe_load_csv(atc_two_file) if atc_two_file else None
                        atc_three = safe_load_csv(atc_three_file) if atc_three_file else None
                        atc_four = safe_load_csv(atc_four_file) if atc_four_file else None
                        # Merge with ATC level descriptions
                        with st.spinner('Merging data with ATC level descriptions...'):
                            merged_data = st.session_state.fuzzy_matched_data_fda.copy()  # Work on a copy to prevent modifying the original data prematurely
                            if atc_one is not None and 'ATCLevelOneCode' in merged_data.columns:
                                merged_data = merged_data.merge(atc_one, on='ATCLevelOneCode', how='left')
                            if atc_two is not None and 'ATCLevelTwoCode' in merged_data.columns:
                                merged_data = merged_data.merge(atc_two, on='ATCLevelTwoCode', how='left')
                            if atc_three is not None and 'ATCLevelThreeCode' in merged_data.columns:
                                merged_data = merged_data.merge(atc_three, on='ATCLevelThreeCode', how='left')
                            if atc_four is not None and 'ATCLevelFourCode' in merged_data.columns:
                                merged_data = merged_data.merge(atc_four, on='ATCLevelFourCode', how='left')
                                
                        # Save the merged data in session state under a new key
                        st.session_state['fda_with_ATCCodeDescription'] = merged_data
                        # Display the merged dataframe
                        if not merged_data.empty:
                            st.write("Merged Data:")
                            st.dataframe(merged_data)
                        else:
                            st.write("No data to display after merging.")

                        st.success("Data merged with ATC level descriptions.")
                    else:
                        st.error("Cannot merge data. Please ensure all required columns are present and try again.")
                else:
                    st.warning("Please complete the fuzzy matching process and ensure ATC level description files are uploaded.")

            # Download file
            csv = convert_df_to_csv(st.session_state.fuzzy_matched_data_fda)
            if csv is not None:
                # Proceed with operations that use 'csv'
                st.download_button(label="Download FDA Register as CSV", data=csv, file_name='fda_register_with_atc_description.csv', mime='text/csv', key='download_mcaz_withatcdescription_fda')

            else:
                # Handle the case where 'csv' is None, e.g., display a message or take alternative action
                print("No data available to convert to CSV")
                
            # Primary filter options presented to the user
            primary_filter_options = ["None", "ATCLevelOneDescript", "ATCLevelTwoDescript", "ATCLevelThreeDescript", "Chemical Subgroup", "Ingredient"]
            selected_primary_filter = st.radio("Select a primary filter", primary_filter_options)

            # Secondary filter options (Applicant filter)
            applicant_filter_options = ["None", "Applicant"]
            selected_applicant_filter = st.radio("Select a secondary filter", applicant_filter_options)

            # Check if 'fda_with_ATCCodeDescription' is in session state and is not empty
            if 'fda_with_ATCCodeDescription' in st.session_state and not st.session_state['fda_with_ATCCodeDescription'].empty:
                # Initialize filtered_data with the full dataset
                filtered_data = st.session_state['fda_with_ATCCodeDescription'].copy()

                # Track applied filters
                applied_filters = []

                # Apply primary filter if selected
                if selected_primary_filter != "None":
                    # Convert all values in the selected filter column to string, get unique values, and sort
                    primary_filter_values = sorted(filtered_data[selected_primary_filter].astype(str).unique())
                    selected_primary_values = st.multiselect(f"Select {selected_primary_filter}", primary_filter_values)

                    if selected_primary_values:
                        # Apply filter based on selected primary values
                        filtered_data = filtered_data[filtered_data[selected_primary_filter].astype(str).isin(selected_primary_values)]
                        applied_filters.append(selected_primary_filter)

                # Apply secondary filter if selected
                if selected_applicant_filter == "Applicant":
                    # Convert all values in the applicant filter column to string, get unique values, and sort
                    applicant_filter_values = sorted(filtered_data["Applicant"].astype(str).unique())
                    selected_applicant_values = st.multiselect("Select Applicant", applicant_filter_values)

                    if selected_applicant_values:
                        # Apply filter based on selected applicant values
                        filtered_data = filtered_data[filtered_data["Applicant"].astype(str).isin(selected_applicant_values)]
                        applied_filters.append("Applicant")

                # Display filtered data and count
                if applied_filters:
                    st.write(f"Filtered Data by {', '.join(applied_filters)}:")
                else:
                    st.write("Displaying unfiltered data (no specific filter values selected):")

                st.dataframe(filtered_data)
                st.write(f"Filtered data count: {len(filtered_data)}")

                # Offer CSV download for filtered data
                csv = convert_df_to_csv(filtered_data)
                st.download_button(label="Download Filtered Data as CSV", data=csv, file_name='fda_register_filtered.csv', mime='text/csv', key='download_filtered')

            else:
                # Handle case where the data isn't available or hasn't been loaded
                st.write("Data not available. Please ensure data is loaded and processed.")

        # Applicant Analysis
        elif choice == 'FDA Applicant Analysis':
            st.subheader('FDA Applicant Analysis')
            
            # Anatomial Main Group
            st.subheader("Anatomcal Main Group Count")

            if 'fda_with_ATCCodeDescription' in st.session_state and not st.session_state['fda_with_ATCCodeDescription'].empty:
                fda_register = st.session_state['fda_with_ATCCodeDescription']

                # Remove complete duplicates
                fda_register = fda_register.drop_duplicates()

                if not fda_register.empty:
                    # Convert 'Principal Name' to string and handle NaN values
                    fda_register['Applicant'] = fda_register['Applicant'].fillna('Unknown').astype(str)

                    # Add "None" option and select Appplicant Name
                    applicant_options = ['None'] + sorted(fda_register['Applicant'].unique())
                    selected_applicant = st.selectbox("Select Applicant Name", applicant_options)

                    # Choose sort order
                    sort_order = st.radio("Select Sort Order", ["Ascending", "Descending"])

                    if selected_applicant != "None":
                        # Filter data based on selected principal
                        filtered_data = fda_register[fda_register['Applicant'] == selected_applicant]
                    else:
                        # If "None" is selected, use the entire dataset
                        filtered_data = fda_register

                    # Group by 'ATC Level One Description' and count unique 'Generic Name'
                    # Sort based on the selected sort order
                    if sort_order == "Descending":
                        atc_classification_count = (filtered_data.groupby('ATCLevelOneDescript')['Ingredient']
                                                    .count()
                                                    .reset_index()
                                                    .rename(columns={'Ingredient': 'IngredientCount'})
                                                    .sort_values(by='IngredientCount', ascending=False))
                    else:
                        atc_classification_count = (filtered_data.groupby('ATCLevelOneDescript')['Ingredient']
                                                    .count()
                                                    .reset_index()
                                                    .rename(columns={'Ingredient': 'IngredientCount'})
                                                    .sort_values(by='IngredientCount', ascending=True))

                    st.write(f"Count of Ingredient Name by ATC Level One Description (sorted {sort_order}):")
                    st.dataframe(atc_classification_count)

                    # Calculate the total count of products across all ATC Level One Descriptions
                    # Ensure you're summing only the 'GenericNameCount' column
                    total_product_count = atc_classification_count['IngredientCount'].sum()
                    st.write(f"Total Count of Products (Across All Groups): {total_product_count}")

                    # Convert the complete DataFrame to CSV
                    csv_data = convert_df_to_csv(atc_classification_count)
                    st.download_button(
                        label="Download data as CSV",
                        data=csv_data,
                        file_name='atc_classification_one_count_orange.csv',
                        mime='text/csv',
                    )

                else:
                    st.write("No data available.")
            else:
                st.write("ATC Code Description data is not available.")

            # Pharmacological Group
            st.subheader("Pharmacological Group Count")

            if 'fda_with_ATCCodeDescription' in st.session_state and not st.session_state['fda_with_ATCCodeDescription'].empty:
                fda_register = st.session_state['fda_with_ATCCodeDescription']

                # Remove complete duplicates
                fda_register = fda_register.drop_duplicates()

                if not fda_register.empty:
                    # Convert 'Principal Name' to string and handle NaN values
                    fda_register['Applicant'] = fda_register['Applicant'].fillna('Unknown').astype(str)

                    # Add "None" option and select Principal Name
                    applicant_options = ['None'] + sorted(fda_register['Applicant'].unique())
                    selected_applicant_3 = st.selectbox("Select Applicant Name", applicant_options, key = "applicant_selection_3")
                    
                    # Choose sort order
                    sort_order_3 = st.radio("Select Sort Order", ["Ascending", "Descending"], key = "sort_order_selection_3")

                    if selected_applicant_3 != "None":
                        # Filter data based on selected principal
                        filtered_data = fda_register[fda_register['Applicant'] == selected_applicant_3]
                    else:
                        # If "None" is selected, use the entire dataset
                        filtered_data = fda_register

                    # Group by 'ATC Level One Description' and count unique 'Generic Name'
                    # Sort based on the selected sort order
                    if sort_order_3 == "Descending":
                        atc_classification_count = (filtered_data.groupby('ATCLevelTwoDescript')['Ingredient']
                                                    .count()
                                                    .reset_index()
                                                    .rename(columns={'Ingredient': 'IngredientCount'})
                                                    .sort_values(by='IngredientCount', ascending=False))
                    else:
                        atc_classification_count = (filtered_data.groupby('ATCLevelTwoDescript')['Ingredient']
                                                    .count()
                                                    .reset_index()
                                                    .rename(columns={'Ingredient': 'IngredientCount'})
                                                    .sort_values(by='IngredientCount', ascending=True))

                    st.write(f"Count of Ingredient Name by ATC Level Two Description (sorted {sort_order_3}):")
                    st.dataframe(atc_classification_count)

                    # Calculate the total count of products across all ATC Level One Descriptions
                    # Ensure you're summing only the 'GenericNameCount' column
                    total_product_count = atc_classification_count['IngredientCount'].sum()
                    st.write(f"Total Count of Products (Across All Groups): {total_product_count}")

                    # Convert the complete DataFrame to CSV
                    csv_data = convert_df_to_csv(atc_classification_count)
                    st.download_button(
                        label="Download data as CSV",
                        data=csv_data,
                        file_name='atc_classification_two_count_orange.csv',
                        mime='text/csv', key = "pharmacology",
                    )

                else:
                    st.write("No data available.")
            else:
                st.write("ATC Code Description data is not available.")

            # Therapuetic Group
            st.subheader("Therapeutic Group Count")

            if 'fda_with_ATCCodeDescription' in st.session_state and not st.session_state['fda_with_ATCCodeDescription'].empty:
                fda_register = st.session_state['fda_with_ATCCodeDescription']

                # Remove complete duplicates
                fda_register = fda_register.drop_duplicates()

                if not fda_register.empty:
                    # Convert 'Applicant Name' to string and handle NaN values
                    fda_register['Applicant'] = fda_register['Applicant'].fillna('Unknown').astype(str)

                    # Add "None" option and select Applicant Name
                    applicant_options = ['None'] + sorted(fda_register['Applicant'].unique())
                    selected_applicant_4 = st.selectbox("Select Applicant Name", applicant_options, key = "applicant_applicant_4")

                    # Choose sort order
                    sort_order_4 = st.radio("Select Sort Order", ["Ascending", "Descending"], key = "sort_order_selection_4")

                    if selected_applicant_4 != "None":
                        # Filter data based on selected applicant
                        filtered_data = fda_register[fda_register['Applicant'] == selected_applicant_4]
                    else:
                        # If "None" is selected, use the entire dataset
                        filtered_data = fda_register

                    # Group by 'ATC Level One Description' and count unique 'Generic Name'
                    # Sort based on the selected sort order
                    if sort_order_4 == "Descending":
                        atc_classification_count = (filtered_data.groupby('ATCLevelThreeDescript')['Ingredient']
                                                    .count()
                                                    .reset_index()
                                                    .rename(columns={'Ingredient': 'IngredientCount'})
                                                    .sort_values(by='IngredientCount', ascending=False))
                    else:
                        atc_classification_count = (filtered_data.groupby('ATCLevelThreeDescript')['Ingredient']
                                                    .count()
                                                    .reset_index()
                                                    .rename(columns={'Ingredient': 'IngredientCount'})
                                                    .sort_values(by='IngredientCount', ascending=True))

                    st.write(f"Count of Ingredient Name by ATC Level Three Description (sorted {sort_order_4}):")
                    st.dataframe(atc_classification_count)

                    # Calculate the total count of products across all ATC Level One Descriptions
                    # Ensure you're summing only the 'GenericNameCount' column
                    total_product_count = atc_classification_count['IngredientCount'].sum()
                    st.write(f"Total Count of Products (Across All Groups): {total_product_count}")

                    # Convert the complete DataFrame to CSV
                    csv_data = convert_df_to_csv(atc_classification_count)
                    st.download_button(
                        label="Download data as CSV",
                        data=csv_data,
                        file_name='atc_classification_three_count_orange.csv',
                        mime='text/csv', key = "therapeutic",
                    )

                else:
                    st.write("No data available.")
            else:
                st.write("ATC Code Description data is not available.")
               
        
        # Patient Flow Forecasting
        elif choice == 'Patient-flow Forecast':
            st.subheader('Patient-flow Forecast')
            # Implement Patient flow Forecast
            
            # Ensure all keys are initialized in session state
            required_keys = ['population', 'prevalence', 'symptomatic_rate', 'diagnosis_rate', 'access_rate', 'treatment_rate']
            if 'data' not in st.session_state or any(key not in st.session_state['data'] for key in required_keys):
                st.session_state['data'] = {
                    'population': 1.0,
                    'prevalence': 1.0,
                    'symptomatic_rate': 1.0,
                    'diagnosis_rate': 1.0,
                    'access_rate': 1.0,
                    'treatment_rate': 1.0
                }
            
            if 'population' in st.session_state['data']:
                st.session_state['data']['population'] = st.number_input("Population (millions)", min_value=0.0, value=st.session_state['data']['population'], step=0.1)
            else:
                st.error('Population data is not initialized.')


#             st.session_state['data']['population'] = st.number_input("Population (millions)", min_value=0.0, value=st.session_state['data']['population'], step=0.1)
            st.session_state['data']['prevalence'] = st.number_input("Epidemiology (prevalence %)", min_value=0.0, max_value=100.0, value=st.session_state['data']['prevalence'], step=0.1)
            st.session_state['data']['symptomatic_rate'] = st.number_input("Symptomatic rate (%)", min_value=0.0, max_value=100.0, value=st.session_state['data']['symptomatic_rate'], step=0.1)
            st.session_state['data']['diagnosis_rate'] = st.number_input("Diagnosis rate (%)", min_value=0.0, max_value=100.0, value=st.session_state['data']['diagnosis_rate'], step=0.1)
            st.session_state['data']['access_rate'] = st.number_input("Access rate (%)", min_value=0.0, max_value=100.0, value=st.session_state['data']['access_rate'], step=0.1)
            st.session_state['data']['treatment_rate'] = st.number_input("Drug-treated patients (%)", min_value=0.0, max_value=100.0, value=st.session_state['data']['treatment_rate'], step=0.1)

            if st.button("Calculate"):
                prevalent_population = calculate_prevalent_population(st.session_state['data']['population'], st.session_state['data']['prevalence'])
                symptomatic_population = calculate_symptomatic_population(prevalent_population, st.session_state['data']['symptomatic_rate'])
                diagnosed_population = calculate_diagnosed_population(symptomatic_population, st.session_state['data']['diagnosis_rate'])
                potential_patients = calculate_potential_patients(diagnosed_population, st.session_state['data']['access_rate'])
                drug_treated_patients = calculate_drug_treated_patients(potential_patients, st.session_state['data']['treatment_rate'])
                
                # Store the results in session state
                st.session_state['results'] = {
                    'prevalent_population': prevalent_population,
                    'symptomatic_population': symptomatic_population,
                    'diagnosed_population': diagnosed_population,
                    'potential_patients': potential_patients,
                    'drug_treated_patients': drug_treated_patients
                }

            # Display results if already calculated
            if 'results' in st.session_state:
                results = st.session_state['results']
                st.write(f"Prevalent Population: {results['prevalent_population']} million")
                st.write(f"Symptomatic Population: {results['symptomatic_population']} million")
                st.write(f"Diagnosed Population: {results['diagnosed_population']} million")
                st.write(f"Potential Patients: {results['potential_patients']} million")
                st.write(f"Drug-treated Patients: {results['drug_treated_patients']} million")
                    
            st.subheader('Hypertension First-line and Combination Treatment')
            
            # Check if 'results' are in the session state and 'drug_treated_patients' is calculated and greater than 0
            if 'results' in st.session_state and st.session_state['results'].get('drug_treated_patients', 0) > 0:
                drug_treated_patients = st.session_state['results']['drug_treated_patients']

                # Input fields for treatment percentages, ensuring values are maintained across sessions
                thiazide_pct = st.number_input("Patients Treated with Thiazide/Thiazide Like Diuretic (%)", 
                                               min_value=0.0, max_value=100.0, 
                                               value=st.session_state.get('thiazide_pct', 0.0))
                acei_arb_pct = st.number_input("Patients Treated with an ACEi/ARB (%)", 
                                               min_value=0.0, max_value=100.0, 
                                               value=st.session_state.get('acei_arb_pct', 0.0))
                ccb_pct = st.number_input("Patients Treated with a Long-Acting CCB (%)", 
                                          min_value=0.0, max_value=100.0, 
                                          value=st.session_state.get('ccb_pct', 0.0))
                combo_pct = st.number_input("Patients Treated with Combination Therapy (%)", 
                                            min_value=0.0, max_value=100.0, 
                                            value=st.session_state.get('combo_pct', 0.0))

                # Store updated values immediately in session state
                st.session_state['thiazide_pct'] = thiazide_pct
                st.session_state['acei_arb_pct'] = acei_arb_pct
                st.session_state['ccb_pct'] = ccb_pct
                st.session_state['combo_pct'] = combo_pct

                total_percentage = thiazide_pct + acei_arb_pct + ccb_pct + combo_pct

                if total_percentage != 100:
                    st.error('Total percentage must equal exactly 100%. Please adjust the values.')
                else:
                    if st.button("Calculate Treatment Distribution"):
                        # Perform the calculations
                        patients_thiazide = (thiazide_pct / 100) * drug_treated_patients * 1000
                        patients_acei_arb = (acei_arb_pct / 100) * drug_treated_patients * 1000
                        patients_ccb = (ccb_pct / 100) * drug_treated_patients * 1000
                        patients_combo = (combo_pct / 100) * drug_treated_patients * 1000

                        # Store calculated values and results text in session state
                        st.session_state['results_text'] = [
                            f"Number of Patients taking Thiazide/Thiazide Diuretics: {patients_thiazide:.2f} thousand",
                            f"Number of Patients taking ACEi/ARB: {patients_acei_arb:.2f} thousand",
                            f"Number of Patients taking Long-Acting CCB: {patients_ccb:.2f} thousand",
                            f"Number of Patients taking Combination Therapy: {patients_combo:.2f} thousand"
                        ]
                        
            else:
                st.warning('Please calculate "Drug-treated Patients" in the "Patient-flow Forecast" module before proceeding.')

            # Display results text if already calculated and stored
            if 'results_text' in st.session_state:
                for text in st.session_state['results_text']:
                    st.write(text)
                    
            # Heading for the new module
            st.subheader("Non-Insulin Depended Diabetes Mellitus Treatment")
            
            # Check if drug-treated patients are calculated
            if 'results' not in st.session_state or 'drug_treated_patients' not in st.session_state['results']:
                st.error("Please calculate 'Drug-treated Patients' in the 'Patient-flow Forecast' module before proceeding.")
            else:
                # Input fields for treatment percentages, explicitly stored in session state
                monotherapy_percentage = st.number_input("Monotherapy with Metformin (%)", min_value=0.0, max_value=100.0, value=st.session_state.get('monotherapy_percentage', 0.0), step=0.1)
                dual_therapy_percentage = st.number_input("Dual Therapy with Metformin and Other (%)", min_value=0.0, max_value=100.0, value=st.session_state.get('dual_therapy_percentage', 0.0), step=0.1)
                triple_therapy_percentage = st.number_input("Triple Therapy with Metformin and Other (%)", min_value=0.0, max_value=100.0, value=st.session_state.get('triple_therapy_percentage', 0.0), step=0.1)
                combo_injectable_percentage = st.number_input("Combination Injectable Therapy with Metformin (%)", min_value=0.0, max_value=100.0, value=st.session_state.get('combo_injectable_percentage', 0.0), step=0.1)

                # Store inputs in session state immediately after input
                st.session_state.monotherapy_percentage = monotherapy_percentage
                st.session_state.dual_therapy_percentage = dual_therapy_percentage
                st.session_state.triple_therapy_percentage = triple_therapy_percentage
                st.session_state.combo_injectable_percentage = combo_injectable_percentage

                # Calculate the total percentage
                total_percentage = (
                    monotherapy_percentage + 
                    dual_therapy_percentage + 
                    triple_therapy_percentage + 
                    combo_injectable_percentage
                )

                if total_percentage != 100:
                    st.error("The total percentage must exactly equal 100%. Please adjust the inputs.")
                else:
                    calculate_patients()
                    st.success(f"Total therapy distribution is exactly {total_percentage}%. Calculations updated.")
                    st.write(f"Number of Patients on Monotherapy (in thousands): {st.session_state['patients_on_monotherapy']:.2f}k")
                    st.write(f"Number of Patients on Dual Therapy (in thousands): {st.session_state['patients_on_dual_therapy']:.2f}k")
                    st.write(f"Number of Patients on Triple Therapy (in thousands): {st.session_state['patients_on_triple_therapy']:.2f}k")
                    st.write(f"Number of Patients on Combination Injectable Therapy (in thousands): {st.session_state['patients_on_combo_injectable_therapy']:.2f}k")
        
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
            
            # Summary of Categories for Distribution
            def summarize_categories_by_principal(mcaz_register):
                st.subheader("Summary of Categories for Distribution by Principal")

                # Check for necessary columns
                required_columns = ['Principal Name', 'Categories for Distribution', 'Date Registered']
                if not all(col in mcaz_register.columns for col in required_columns):
                    st.error("Uploaded data does not contain the required columns.")
                    return

                # Preprocess data
                data = mcaz_register.dropna(subset=required_columns)
                data['Year'] = pd.to_datetime(data['Date Registered'], errors='coerce').dt.year

                # Principal selection
                principal_names = ['All'] + sorted(data['Principal Name'].unique())
                selected_principal = st.selectbox('Select Principal Name', principal_names)

                # Filter data
                if selected_principal != 'All':
                    filtered_data = data[data['Principal Name'] == selected_principal]
                else:
                    filtered_data = data

                # Initial summary
                total_product_count = filtered_data.shape[0]
                category_counts = filtered_data['Categories for Distribution'].value_counts().reset_index(name='Count')
                category_counts['% Total'] = (category_counts['Count'] / total_product_count) * 100
                category_counts.columns = ['Category', 'Count', '% Total']

                # Display initial summary
                if not category_counts.empty:
                    st.write(f"Initial Summary for {selected_principal}:")
                    st.dataframe(category_counts.style.format({'% Total': "{:.2f}%"}))
                    st.markdown(f"**Total Product Count:** {total_product_count}")

                # Detailed yearly summary
                st.write(f"Yearly Summary for {selected_principal}:")

                # Group and calculate counts and percentages
                grouped = filtered_data.groupby(['Categories for Distribution', 'Year']).size().reset_index(name='Count')
                total_counts_by_year = filtered_data.groupby(['Year', 'Categories for Distribution']).size().groupby(level=0).sum().reset_index(name='TotalYearCount')

                # Merge for percentages
                summary = pd.merge(grouped, total_counts_by_year, on='Year')
                summary['% Total'] = (summary['Count'] / summary['TotalYearCount']) * 100

                # Pivot for yearly summary with specific formatting
                pivot_df = summary.pivot_table(index='Categories for Distribution', columns='Year', values=['Count', '% Total'], aggfunc='first')

                # Create multi-level columns for each year with "Total Count" and "% For the Year"
                pivot_df.columns = pivot_df.columns.map('{0[0]} {0[1]}'.format)
                pivot_df = pivot_df.sort_index(axis=1, level=1)
                
                # Extract years from column names, convert to float first to ensure correct handling, and then convert to int to remove decimals
                years = np.unique([int(float(col.split(' ')[-1])) for col in pivot_df.columns])

                # Rearrange columns to have "Count" and "% Total" next to each other for each year
                new_order = []
                for year in sorted(years):  # years are already integers, no need for further conversion
                    year_columns = [col for col in pivot_df.columns if str(year) in col]
                    sorted_columns = sorted(year_columns, key=lambda x: x.split()[0], reverse=True)
                    new_order.extend(sorted_columns)

                # Reorder the DataFrame columns according to the new order
                pivot_df = pivot_df[new_order]

                # Format percentages to two decimal places
                for col in pivot_df.columns:
                    if "% Total" in col:
                        pivot_df[col] = pivot_df[col].map("{:.2f}%".format)

                # Display the formatted pivot table
                if not pivot_df.empty:
                    st.dataframe(pivot_df)
                else:
                    st.write("No yearly data available.")
        
            summarize_categories_by_principal(mcaz_register)
        
        # Drugs with No Patents and NO Competition Analysis
        elif choice == 'Drugs with no Competition':
            st.subheader('FDA Drugs with No Patents and No Competition')
            # Implement FDA No Patents analysis

            # Medicine type selection
            medicine_type = st.radio("Select Medicine Type", ["Human Medicine", "Veterinary Medicine"])
                                    
            # Load MCAZ Register data from session state or initialize if not present
            mcaz_register = st.session_state.get('mcaz_register', pd.DataFrame())

            if medicine_type == "Human Medicine":
                uploaded_file = st.file_uploader("Upload your Drugs with No Patents No Competition file", type=['csv'])

                if uploaded_file is not None:
                    # Load data into session state
                    st.session_state['fda_data'] = load_data_fda(uploaded_file)
                    fda_data = st.session_state['fda_data']

                    if not fda_data.empty and not mcaz_register.empty:
                        # Filter out products that are in the MCAZ Register
                        filtered_fda_data = filter_fda_data(fda_data, mcaz_register)
                        st.session_state['filtered_fda_data'] = filtered_fda_data  # Store filtered data in session state

                        # Add "None" option and sort filter options
                        dosage_form_options = ['None'] + sorted(filtered_fda_data['DOSAGE FORM'].dropna().unique().tolist())
                        selected_dosage_form = st.selectbox("Select Dosage Form", dosage_form_options)

                        type_options = ['None'] + sorted(filtered_fda_data['TYPE'].dropna().unique().tolist())
                        selected_type = st.selectbox("Select Type", type_options)

                        # Apply filters if selections are not "None"
                        if selected_dosage_form != "None":
                            st.session_state['filtered_fda_data'] = st.session_state['filtered_fda_data'][st.session_state['filtered_fda_data']['DOSAGE FORM'] == selected_dosage_form]
                        if selected_type != "None":
                            st.session_state['filtered_fda_data'] = st.session_state['filtered_fda_data'][st.session_state['filtered_fda_data']['TYPE'] == selected_type]

                        # Display the filtered dataframe
                        st.write("Filtered FDA Data (Excluding MCAZ Registered Products):")
                        st.dataframe(st.session_state['filtered_fda_data'])

                        # Count and display the number of drugs
                        drug_count = len(st.session_state['filtered_fda_data'])
                        st.write(f"Total Number of Unique Drugs: {drug_count}")

                        # Convert the complete DataFrame to CSV
                        csv_data = convert_df_to_csv(st.session_state['filtered_fda_data'])
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

        # Top Phamra Companies Word wide Sales
        elif choice == 'Top Pharma Companies Sales':
            st.subheader('Top Pharma Companies World Sales')
            
            # Initialize session state for DataFrame if not already present
            if 'df' not in st.session_state:
                st.session_state.df = pd.DataFrame()

            # Upload functionality
            uploaded_file = st.file_uploader("Upload your sales data CSV file", type=["csv"])
            if uploaded_file is not None:
                # Load data into session state only if a new file is uploaded
                st.session_state.df = load_data_sales(uploaded_file)

            # Check if the DataFrame is not empty
            if not st.session_state.df.empty:
                st.subheader('Filter Options')

                # Dynamic lists for filter options
                company_list = ['All'] + sorted(st.session_state.df['Company Name'].unique().tolist())
                product_list = ['All'] + sorted(st.session_state.df['Product Name'].unique().tolist())
                ingredient_list = ['All'] + sorted(st.session_state.df['Active Ingredient'].fillna('Unknown').unique().tolist())
                indication_list = ['All'] + sorted(st.session_state.df['Main Therapeutic Indication'].fillna('Unknown').unique().tolist())
                classification_list = ['All'] + sorted(st.session_state.df['Product Classification'].fillna('Unknown').unique().tolist())

                # User filter selections
                company_name = st.selectbox('Company Name', company_list)
                product_name = st.selectbox('Product Name', product_list)
                active_ingredient = st.selectbox('Active Ingredient', ingredient_list)
                therapeutic_indication = st.selectbox('Main Therapeutic Indication', indication_list)
                product_classification = st.selectbox('Product Classification', classification_list)

                # Sorting options
                sort_column = st.selectbox('Sort by', ['2023 Revenue in Millions USD', '2022 Revenue in Millions USD'], index=0)
                sort_order = st.selectbox('Sort order', ['Ascending', 'Descending'], index=1)
                is_ascending = sort_order == 'Ascending'

                # Apply filters to a local copy of the DataFrame
                filtered_df = st.session_state.df.copy()
                if company_name != 'All':
                    filtered_df = filtered_df[filtered_df['Company Name'] == company_name]
                if product_name != 'All':
                    filtered_df = filtered_df[filtered_df['Product Name'] == product_name]
                if active_ingredient != 'All':
                    filtered_df = filtered_df[filtered_df['Active Ingredient'] == active_ingredient]
                if therapeutic_indication != 'All':
                    filtered_df = filtered_df[filtered_df['Main Therapeutic Indication'] == therapeutic_indication]
                if product_classification != 'All':
                    filtered_df = filtered_df[filtered_df['Product Classification'] == product_classification]

                # Sort and display the filtered DataFrame
                if not filtered_df.empty:
                    filtered_df = filtered_df.sort_values(by=sort_column, ascending=is_ascending)
                    st.write(filtered_df)
                else:
                    st.write("No data to display after filtering.")
                    
                # Download button for filtered data
                if not filtered_df.empty:
                    csv_data = convert_df_to_csv(filtered_df)
                    file_name = f"filtered_data_{company_name}.csv"
                    st.download_button(
                        label="Download data as CSV",
                        data=csv_data,
                        file_name=file_name,
                        mime='text/csv',
                    )

            else:
                st.write("Please upload a sales data CSV file to get started.")
                
        # FDA Drug Establishment Sites
        elif choice == 'FDA Drug Establishment Sites':
            st.subheader('FDA Drug Establishment Sites')
            
            # File uploader for the Establishment and Country Codes file
            establishment_file = st.file_uploader("Choose an Establishment CSV file", type="csv", key="establishment")
            country_codes_file = st.file_uploader("Choose a Country Codes CSV file", type="csv", key="country_codes")
            
            if establishment_file and country_codes_file:
                df = process_uploaded_file(establishment_file)
                if df is None:
                    st.error("Processing of establishment file failed.")
                    st.stop()

                country_codes_df = process_country_code_file(country_codes_file)
                if country_codes_df is None:
                    st.error("Processing of country codes file failed.")
                    st.stop()

                # Check if 'COUNTRY_CODE' is available before merge
                if 'COUNTRY_CODE' not in df.columns:
                    st.error("Failed to ensure 'COUNTRY_CODE' in DataFrame.")
                    st.stop()

                merged_df = df.merge(country_codes_df, left_on='COUNTRY_CODE', right_on='Alpha-3 code', how='left')
                merged_df.fillna('Unknown', inplace=True)
                st.session_state['merged_data'] = merged_df

            if 'merged_data' in st.session_state:
                firm_name_options = ["All"] + sorted(st.session_state['merged_data']['FIRM_NAME'].dropna().unique().tolist())
                country_options = ["All"] + sorted(st.session_state['merged_data']['Country'].dropna().unique().tolist())
                operations_options = ["All"] + sorted(st.session_state['merged_data']['OPERATIONS'].dropna().unique().tolist())
                registrant_name_options = ["All"] + sorted(st.session_state['merged_data']['REGISTRANT_NAME'].dropna().unique().tolist())

                firm_name = st.selectbox("Firm Name", firm_name_options)
                country = st.selectbox("Country", country_options)
                operations = st.selectbox("Operations", operations_options)
                registrant_name = st.selectbox("Registrant Name", registrant_name_options)

                filtered_df = filter_dataframe_establishments(st.session_state['merged_data'], firm_name, country, operations, registrant_name)
                filtered_df['FIRM_NAME'] = filtered_df['FIRM_NAME'].apply(lambda x: f'<a href="https://www.google.com/search?q={x}" target="_blank">{x}</a>')
                filtered_df['ESTABLISHMENT_CONTACT_EMAIL'] = filtered_df['ESTABLISHMENT_CONTACT_EMAIL'].apply(lambda x: f'<a href="mailto:{x}">{x}</a>')
                filtered_df['REGISTRANT_CONTACT_EMAIL'] = filtered_df['REGISTRANT_CONTACT_EMAIL'].apply(lambda x: f'<a href="mailto:{x}">{x}</a>')

                # Implement a simple paginator for the filtered data
                page_number = st.number_input('Page number', min_value=1, max_value=(len(filtered_df) // 10 + 1), value=1)
                page_size = 10  # items per page
                start_index = (page_number - 1) * page_size
                end_index = start_index + page_size

                # Display filtered data
                st.write(filtered_df[start_index:end_index].to_html(escape=False, index=False), unsafe_allow_html=True)
                firm_count = len(filtered_df)
                st.write(f"Total Number of Unique Firms: {firm_count}")

                # Download button for the filtered dataframe
                csv = filtered_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download filtered data as CSV",
                    data=csv,
                    file_name='filtered_fda_sites.csv',
                    mime='text/csv',
                )

        # FDA NME & New Biologic Approvals
        if choice == 'FDA NME & New Biologic Approvals':
            st.subheader('FDA NME & New Biologic Approvals')

            uploaded_file = st.file_uploader("Choose an NME & New Biologics file")
            if uploaded_file is not None:
                # Process and store the uploaded data only if a new file is provided
                df_filtered = load_data_nme(uploaded_file)
                # Reset filters if a new file is uploaded
                st.session_state['nme_biologics_data'] = df_filtered
                st.session_state['nme_biologics_filters'] = {}
            elif 'nme_biologics_data' in st.session_state:
                # Use previously loaded data
                df_filtered = st.session_state['nme_biologics_data']
            else:
                st.warning("Please upload a file to begin.")
                st.stop()

            # Initialize or retrieve filter settings from session state
            filter_settings = st.session_state.get('nme_biologics_filters', {})

            # Define UI for all filters and update filter_settings based on user input
            # Approval Year Range
            if 'Approval Year' in df_filtered:
                year_options = range(int(df_filtered['Approval Year'].min()), int(df_filtered['Approval Year'].max()) + 1)
                start_year, end_year = st.select_slider(
                    'Select Approval Year Range:',
                    options=list(year_options),
                    value=filter_settings.get('year_range', (min(year_options), max(year_options)))
                )
                filter_settings['year_range'] = (start_year, end_year)

            # NDA/BLA
            nda_bla_options = ['All'] + sorted(df_filtered['NDA/BLA'].unique().tolist())
            nda_bla_selection = st.selectbox('NDA/BLA', options=nda_bla_options, index=0)
            filter_settings['nda_bla_selection'] = nda_bla_selection

            # Active Ingredient/Moiety
            active_ingredient_options = ['All'] + sorted(df_filtered['Active Ingredient/Moiety'].unique().tolist())
            active_ingredient_selection = st.selectbox('Active Ingredient/Moiety', options=active_ingredient_options, index=0)
            filter_settings['active_ingredient_selection'] = active_ingredient_selection

            # Additional Filters
            review_designation_options = ['All', 'Priority', 'Standard']
            review_designation_selection = st.selectbox('Review Designation', options=review_designation_options, index=0)
            filter_settings['review_designation_selection'] = review_designation_selection

            orphan_drug_option = st.checkbox('Orphan Drug Designation', value='Orphan Drug Designation' in filter_settings)
            filter_settings['orphan_drug_option'] = orphan_drug_option

            accelerated_approval_option = st.checkbox('Accelerated Approval', value='Accelerated Approval' in filter_settings)
            filter_settings['accelerated_approval_option'] = accelerated_approval_option

            breakthrough_therapy_option = st.checkbox('Breakthrough Therapy Designation', value='Breakthrough Therapy Designation' in filter_settings)
            filter_settings['breakthrough_therapy_option'] = breakthrough_therapy_option

            fast_track_option = st.checkbox('Fast Track Designation', value='Fast Track Designation' in filter_settings)
            filter_settings['fast_track_option'] = fast_track_option

            qualified_infectious_option = st.checkbox('Qualified Infectious Disease Product', value='Qualified Infectious Disease Product' in filter_settings)
            filter_settings['qualified_infectious_option'] = qualified_infectious_option

            # Apply filters based on user selection
            df_filtered = apply_all_filters(df_filtered, filter_settings)

            # Update session state with the latest filter settings
            st.session_state['nme_biologics_filters'] = filter_settings

            # Display the filtered dataframe
            st.dataframe(df_filtered)
            st.write(f"Filtered data count: {len(df_filtered)}")

            # Download button for the filtered dataframe
            csv = df_filtered.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download filtered data as CSV",
                data=csv,
                file_name='filtered_fda_nmes_biologics.csv',
                mime='text/csv',
            )
    
                
        # Assuming 'choice' variable is determined by some user interaction upstream in your code
        if choice == 'EMA FDA Health Canada Approvals 2023':
            st.subheader('EMA FDA Health Canada Approvals 2023')
                        
            uploaded_file = st.file_uploader("Choose a EMA FDA Health Canada 2023 Approvals CSV file", type="csv")

            if uploaded_file is not None:
                try:
                    # Directly read the uploaded file
                    data = pd.read_csv(uploaded_file, encoding='ISO-8859-1')
                    # Store the processed data in session_state
                    st.session_state[data_key] = data
                except Exception as e:
                    st.error(f'Failed to process the uploaded file: {e}')
                    return
            elif data_key in st.session_state:
                # Use the previously uploaded and processed data
                data = st.session_state[data_key]
            else:
                st.warning("Please upload a file to proceed.")
                return
            
            # Provide an option to re-upload and clear the existing data
            if st.button('Clear data'):
                if data_key in st.session_state:
                    del st.session_state[data_key]
                st.experimental_rerun()

            # Initialize or retrieve filter states from session state
            filter_defaults = {
                'drug_name': 'All', 'company_name': 'All', 'active_ingredient': 'All', 'therapeutic_area': 'All',
                'product_type': 'All', 'regulatory_authority': 'All', 'application_type': 'All', 'drug_type': 'All'
            }
            for filter_key, default_value in filter_defaults.items():
                if filter_key not in st.session_state:
                    st.session_state[filter_key] = default_value

            # Create filter selectors
            st.session_state['drug_name'] = st.selectbox('Drug Name', ['All'] + sorted(data['Drug Name'].unique().tolist()), index=0)
            st.session_state['company_name'] = st.selectbox('Company Name', ['All'] + sorted(data['Company Name'].unique().tolist()), index=0)
            st.session_state['active_ingredient'] = st.selectbox('Active Ingredient', ['All'] + sorted(data['Active Ingredient'].unique().tolist()), index=0)
            st.session_state['therapeutic_area'] = st.selectbox('Therapeutic Area', ['All'] + sorted(data['Therapeutic Area'].unique().tolist()), index=0)
            st.session_state['product_type'] = st.selectbox('Product Type', ['All'] + sorted(data['Product Type'].unique().tolist()), index=0)
            st.session_state['regulatory_authority'] = st.selectbox('Regulatory Authority', ['All'] + sorted(data['Regulatory Authority'].unique().tolist()), index=0)
            st.session_state['application_type'] = st.selectbox('Application Type', ['All'] + sorted(data['Application Type'].unique().tolist()), index=0)
            st.session_state['drug_type'] = st.selectbox('Drug Type', ['All'] + sorted(data['Drug Type'].unique().tolist()), index=0)

            # Apply filters
            filtered_data = data
            if st.session_state['drug_name'] != 'All':
                filtered_data = filtered_data[filtered_data['Drug Name'] == st.session_state['drug_name']]
            if st.session_state['company_name'] != 'All':
                filtered_data = filtered_data[filtered_data['Company Name'] == st.session_state['company_name']]
            if st.session_state['active_ingredient'] != 'All':
                filtered_data = filtered_data[filtered_data['Active Ingredient'] == st.session_state['active_ingredient']]
            if st.session_state['therapeutic_area'] != 'All':
                filtered_data = filtered_data[filtered_data['Therapeutic Area'] == st.session_state['therapeutic_area']]
            if st.session_state['product_type'] != 'All':
                filtered_data = filtered_data[filtered_data['Product Type'] == st.session_state['product_type']]
            if st.session_state['regulatory_authority'] != 'All':
                filtered_data = filtered_data[filtered_data['Regulatory Authority'] == st.session_state['regulatory_authority']]
            if st.session_state['application_type'] != 'All':
                filtered_data = filtered_data[filtered_data['Application Type'] == st.session_state['application_type']]
            if st.session_state['drug_type'] != 'All':
                filtered_data = filtered_data[filtered_data['Drug Type'] == st.session_state['drug_type']]

            # Drop specified columns, if they exist, and display the filtered dataset
            columns_to_remove = ['Product Status Link', 'Estimated Sales (mm USD) Link']
            filtered_data = filtered_data.drop(columns=columns_to_remove, errors='ignore')

            st.write(filtered_data)

            # Display the count of the filtered dataframe
            st.write(f'Count of filtered results: {len(filtered_data)}')

            # Button to save the filtered data as CSV
            csv = filtered_data.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download filtered data as CSV",
                data=csv,
                file_name='filtered_fda_ema_healthcanada.csv',
                mime='text/csv',
            )
            
        elif choice == 'FDA Filed DMFs':
            st.subheader('FDA Filed DMFs')
            
            uploaded_file = st.file_uploader("Upload your DMF file", type=['csv'])

            required_columns = ['STATUS', 'TYPE', 'SUBMIT DATE', 'HOLDER', 'SUBJECT']

            if uploaded_file is not None:
                if st.session_state.get('uploaded_file_name') != uploaded_file.name:
                    data = load_data_dmf(uploaded_file)
                    valid, missing_cols = check_required_columns_dmf(data, required_columns)
                    if not valid:
                        st.error(f"Missing columns in the uploaded file: {', '.join(missing_cols)}. Please upload a file with all required columns.")
                        st.stop()
                    st.session_state['data'] = data
                    st.session_state['uploaded_file_name'] = uploaded_file.name

            if st.session_state.get('data') is not None:
                # Check if 'SUBMIT DATE' column exists before setting min_date and max_date
                if 'SUBMIT DATE' in st.session_state['data'].columns:
                    st.session_state['data']['SUBMIT DATE'] = pd.to_datetime(st.session_state['data']['SUBMIT DATE'])
                    min_date = st.session_state['data']['SUBMIT DATE'].min()
                    max_date = st.session_state['data']['SUBMIT DATE'].max()
                else:
                    st.error("The 'SUBMIT DATE' column is missing from the uploaded file.")
                    st.stop()

                # Filters
                status = st.selectbox('Status', ['All'] + sorted(st.session_state['data']['STATUS'].unique().tolist()), index=0)
                type_filter = st.selectbox('Type', ['All'] + sorted(st.session_state['data']['TYPE'].unique().tolist()), index=0)
                date_from = st.date_input("From Date", min_date, min_value=min_date, max_value=max_date)
                date_to = st.date_input("To Date", max_date, min_value=min_date, max_value=max_date)
                holder = st.selectbox('Holder', ['All'] + sorted(st.session_state['data']['HOLDER'].unique().tolist()), index=0)
                holder_sort = st.selectbox('Sort Holder', ["None", "Ascending", "Descending"])
                subject = st.multiselect('Subject', ['All'] + sorted(st.session_state['data']['SUBJECT'].unique().tolist()), default=['All'])
                subject_sort = st.selectbox('Sort Subject', ["None", "Ascending", "Descending"])

                filtered_data = filter_data(st.session_state['data'], status, type_filter, date_from, date_to, holder, subject, holder_sort, subject_sort)

                # Add Google search column for Holder
                filtered_data['Google Search'] = filtered_data['HOLDER'].apply(lambda x: f'<a href="https://www.google.com/search?q={x}" target="_blank">Search</a>')

                # Pagination
                if 'page' not in st.session_state:
                    st.session_state.page = 0

                items_per_page = 100
                total_pages = (len(filtered_data) - 1) // items_per_page + 1

                start_index = st.session_state.page * items_per_page
                end_index = min(start_index + items_per_page, len(filtered_data))

                st.write(filtered_data.iloc[start_index:end_index].to_html(escape=False), unsafe_allow_html=True)
                st.write(f"Showing records {start_index + 1} to {end_index} of {len(filtered_data)}")

                col1, col2, col3 = st.columns([1, 1, 1])

                if col1.button("Previous") and st.session_state.page > 0:
                    st.session_state.page -= 1

                if col3.button("Next") and st.session_state.page < total_pages - 1:
                    st.session_state.page += 1

                if col2.button("Reset"):
                    st.session_state.page = 0

                if st.button("Save to CSV"):
                    csv = filtered_data.to_csv(index=False)
                    st.download_button(label="Download CSV", data=csv, file_name='filtered_data_dmfs.csv', mime='text/csv')

         
        # Assuming 'choice' variable is determined by some user interaction upstream in your code
        elif choice == 'Drugs@FDA Analysis':
            
            # Simplified session state management
            if choice:
                st.session_state['selected_analysis'] = choice

            # Conditional execution based on session state
            if 'selected_analysis' in st.session_state:
                if st.session_state['selected_analysis'] == "Drugs@FDA Analysis":
                    perform_drugs_fda_analysis()
                    
            # Add a subheader for the new section
            st.subheader("FDA Portfolio Maturity Analysis")
            
            # Initializing session state for data persistence
            if 'data' not in st.session_state:
                st.session_state['data'] = None
            
            # File uploader
            uploaded_file = st.file_uploader("Choose a file")
            if uploaded_file is not None:
                st.session_state['data'] = load_data_maturity(uploaded_file)
                
                # Display and filter data if loaded
                if st.session_state['data'] is not None:
                    merged_df = st.session_state['data']

                # Ensure 'SubmissionStatusDate' is in datetime format
                merged_df['SubmissionStatusDate'] = pd.to_datetime(merged_df['SubmissionStatusDate'])

                # Filter for NDA type
                nda_df = merged_df[merged_df['ApplType'] == 'NDA']

                # Determine the Patent Expiry Date
                def get_patent_expiry_date(df, active_ingredient, submission_date):
                    relevant_dates = df[(df['ActiveIngredient'] == active_ingredient) & 
                                        (df['ApplType'] == 'ANDA') & 
                                        (df['SubmissionStatus'] == 'AP')]['SubmissionStatusDate']

                    if not relevant_dates.empty:
                        return relevant_dates.min() - pd.Timedelta(days=1)
                    else:
                        return pd.NaT

                # Apply the function to each row in nda_df
                nda_df['Patent Expiry Date'] = nda_df.apply(lambda row: get_patent_expiry_date(merged_df, row['ActiveIngredient'], row['SubmissionStatusDate']), axis=1)

                # Ensure 'Patent Expiry Date' is in datetime format
                nda_df['Patent Expiry Date'] = pd.to_datetime(nda_df['Patent Expiry Date'])

                # Calculate Age Since Patent Expiry
                today = datetime.today()
                nda_df['Age Since Patent Expiry'] = nda_df['Patent Expiry Date'].apply(lambda x: (today - x).days / 365 if pd.notna(x) else None)

                # Add Status column based on Age Since Patent Expiry
                def determine_status(row):
                    age = row['Age Since Patent Expiry']
                    expiry_date = row['Patent Expiry Date']
                    if pd.isna(expiry_date) or (age is not None and age <= 4) or (merged_df['ApplType'] == 'ANDA').empty and (merged_df['SubmissionStatus']=='AP'): 
                        return "Third Generation Generics"
                    elif age is not None and 4 < age <= 10:
                        return "Second Generation Generics"
                    elif age is not None and age > 10:
                        return "First Generation Generics"
                    return None

                nda_df['Status'] = nda_df.apply(determine_status, axis=1)

                # Filter options for ActiveIngredient, sorted in ascending order
                active_ingredient_filter_options = ['All'] + sorted(nda_df['ActiveIngredient'].unique())
                selected_active_ingredient = st.selectbox("Filter by Active Ingredient", active_ingredient_filter_options)

                # Apply the ActiveIngredient filter
                if selected_active_ingredient != 'All':
                    nda_df = nda_df[nda_df['ActiveIngredient'] == selected_active_ingredient]

                # Filter options for Status, sorted in ascending order
                status_filter_options = ['All'] + sorted(nda_df['Status'].dropna().unique())
                selected_status = st.selectbox("Filter by Status", status_filter_options)

                # Apply the Status filter
                if selected_status != 'All':
                    nda_df = nda_df[nda_df['Status'] == selected_status]

                # Select required columns and include all products with the same ActiveIngredient
                result_df = nda_df[['DrugName', 'ActiveIngredient', 'Form', 'Strength', 'SponsorName', 'Patent Expiry Date', 'Age Since Patent Expiry', 'Status']]

                # Remove duplicates
                result_df = result_df.drop_duplicates()
                st.session_state['result_df'] = result_df

                # Display the final dataframe
                st.dataframe(result_df)
                # Display the count of the filtered dataframe
                st.write(f'Count of filtered results: {len(result_df)}')

                # Button to save the filtered data as CSV
                csv = result_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download filtered data as CSV",
                    data=csv,
                    file_name='filtered_result_df.csv',
                    mime='text/csv',
                )
            else:
                st.write("Please upload a Drugs@FDA file to analyze")
        
        # Choice Healthcare Practitioners
        elif choice == 'Healthcare Practitioners':
            st.subheader("Healthcare Practitioners")
            
            # Initialize session state if not already initialized
            if 'healthcare_data' not in st.session_state:
                st.session_state['healthcare_data'] = None

            # File upload
            uploaded_file = st.file_uploader("Upload your CSV file", type="csv")

            if uploaded_file is not None:
                # Load and process data
                df = load_and_process_data(uploaded_file)

                # Save to session state
                st.session_state['healthcare_data'] = df

            # If there is data in session state, proceed
            if st.session_state['healthcare_data'] is not None:
                df = st.session_state['healthcare_data']

                # Convert necessary columns to strings to avoid type errors
                df['Specialty'] = df['Specialty'].astype(str)
                df['Town'] = df['Town'].astype(str)
                df['Gender'] = df['Gender'].astype(str)

                # Filters
                specialty_filter = st.selectbox("Select Specialty", options=["All"] + sorted(df['Specialty'].unique().tolist()))
                town_filter = st.selectbox("Select Town", options=["All"] + sorted(df['Town'].unique().tolist(), reverse=True))
                gender_filter = st.selectbox("Select Gender", options=["All"] + sorted(df['Gender'].unique().tolist()))

                # Apply filters
                if specialty_filter != "All":
                    df = df[df['Specialty'] == specialty_filter]
                if town_filter != "All":
                    df = df[df['Town'] == town_filter]
                if gender_filter != "All":
                    df = df[df['Gender'] == gender_filter]

                # Display filtered dataframe
                st.dataframe(df)

                # Display the count of the filtered dataframe
                st.write(f'Count of filtered results: {len(df)}')

                # Option to download filtered data
                csv = df.to_csv(index=False)
                st.download_button(
                    label="Download filtered data as CSV",
                    data=csv,
                    file_name='filtered_healthcare_practitioners.csv',
                    mime='text/csv',
                )
        
    else:
        st.warning('Please upload MCAZ Register CSV file.')
        
def main():
    # Logo and header
    st.image("logo.png", width=200)
    st.markdown("<h1 style='font-size:30px;'>Pharmaceutical Products Analysis Application</h1>", unsafe_allow_html=True)
    
    # User name and password input
    user_name_guess = st.text_input('Enter your user name').strip()
    password_guess = st.text_input('What is the Password?', type="password").strip()

    # Check if user name and password are entered and incorrect
    if user_name_guess and password_guess:
        if user_name_guess != st.secrets["user_name"] or password_guess != st.secrets["password"]:
            st.error("Incorrect user name or password. Please try again.")
            st.stop()

    # Check if user name and password are correct
    if user_name_guess == st.secrets["user_name"] and password_guess == st.secrets["password"]:
        try:
            # Parse the expiration date
            expiration_date = datetime.strptime(st.secrets["expiration_date"], "%d-%m-%Y")
        except Exception as e:
            st.error(f"Error parsing expiration date: {e}")
            st.stop()
            return

        if datetime.now() > expiration_date:
            st.error("Product license has expired. Please contact the administrator.")
            st.stop()
        else:
            st.success("User name and password are correct and license has not expired")

        # Display main application content if the user is logged in and the password is not expired
        display_main_application_content()

if __name__ == "__main__":
    main()


