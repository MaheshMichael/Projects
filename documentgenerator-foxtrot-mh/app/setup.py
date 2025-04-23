import streamlit as st
from docx import Document
import io
import os
import base64
from llm import get_presentation_content
from pptx_utils import create_pptx

# Set Streamlit page config
st.set_page_config(page_title="Document to Presentation", page_icon="📝", layout="wide")

# Function to load the logo in base64
def get_base64_logo(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

# Logo path and encoding
logo_path = os.path.abspath('pptx_templates/EY2.png')
logo_base64 = get_base64_logo(logo_path)

pptx_template_path = 'pptx_templates/EYtemplate-simple.pptx'

# Theme options
theme_options = {
    "Dark": {"bg_color": "#1E1E1E", "text_color": "#FFD700", "highlight_color": "#FFA500", "upload_bg": "#292929"},
    "White": {"bg_color": "#FFFFFF", "text_color": "#000000", "highlight_color": "#808080", "upload_bg": "#F3F3F3"},
}

# Template selection
selected_theme = st.radio("Choose Your Theme", ["Dark", "White"], horizontal=True)
theme = theme_options[selected_theme]

# Apply custom theme CSS
st.markdown(
    f"""
    <style>
        .stApp {{ background-color: {theme["bg_color"]} !important; color: {theme["text_color"]} !important; }}
        [data-testid="stSidebar"] {{ background-color: {theme["bg_color"]} !important; }}
        .upload-box {{ background-color: {theme["upload_bg"]}; padding: 15px; border-radius: 8px; text-align: center;
                       border: 2px solid {theme["highlight_color"]}; }}
        .title-text {{ color: {theme["text_color"]}; text-align: center; }}
        .info-box {{ background-color: {theme["bg_color"]}; padding: 10px; border-radius: 8px; 
                     border: 1px solid {theme["highlight_color"]}; }}
        .logo-container {{ position: absolute; top: 10px; left: 10px; }}
        .stButton>button, .stDownloadButton>button {{ background-color: {theme["highlight_color"]} !important;
                                                       color: {theme["bg_color"]} !important; border-radius: 8px;
                                                       font-weight: bold; border: none; }}
    </style>
    <div class="logo-container">
        <img src="data:image/png;base64,{logo_base64}" width="300" style="margin-top: -90px;">
    </div>
    """,
    unsafe_allow_html=True
)

# Welcome message
st.markdown(
    f"""
    <div style="text-align: center;">
        <h2 style='color: {theme["highlight_color"]}; font-size: 50px; margin: 0;'>Welcome to Smart Slides!</h2>
        <p style='font-size: 22px; color: {theme["text_color"]}; margin-top: 8px;'>Transform your Word documents into stunning PowerPoint presentations</p>
    </div>
    """,
    unsafe_allow_html=True
)

# File upload section
st.markdown(f"<h4 style='color: {theme['highlight_color']};'>Upload Your Document</h4>", unsafe_allow_html=True)
st.markdown(
    f"""
    <div class="upload-box">
        <p style='color: {theme["text_color"]}; font-size: 16px;'>Start by uploading a .docx file</p>
    </div>
    """,
    unsafe_allow_html=True
)
uploaded_file = st.file_uploader("", type=["docx"], label_visibility="collapsed")

# Function to process the document
def load_word(file):
    try:
        file_stream = io.BytesIO(file.read())
        doc = Document(file_stream)  
        text = "\n".join([para.text for para in doc.paragraphs]) 
        return text if text.strip() else "Empty document."
    except Exception as e:
        return f"Error reading file: {e}"

# Function to generate presentation
def generate_presentation(content, template_path):
    summary_dict = get_presentation_content(content)
    pptx_stream = create_pptx(summary_dict, template_path)
    return summary_dict, pptx_stream

# Process uploaded file
if uploaded_file:
    st.success(f"File uploaded: {uploaded_file.name}")

    with st.spinner("Processing your document..."):
        content = load_word(uploaded_file)

    st.success("Document processed successfully!")

    # Generate AI Summary and PowerPoint
    with st.spinner("Generating AI summary..."):
        summary_dict, pptx_stream = generate_presentation(content, pptx_template_path)
    
    st.json(summary_dict)

    st.success("PowerPoint created successfully!")
    # Extract filename without extension
    doc_filename = os.path.splitext(uploaded_file.name)[0]
    pptx_filename = f"{doc_filename}.pptx"

    # Display LLM-generated summary
    st.markdown(f"<h4 style='color: {theme['highlight_color']};'>Generated Summary</h4>", unsafe_allow_html=True)

    # Download button for PowerPoint
    st.download_button(
        label="⬇ Download PowerPoint",
        data=pptx_stream,
        file_name=pptx_filename,
        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )

# Final notification
st.markdown(
    f"<p style='text-align: center; font-size: 14px; color: {theme['text_color']};'>Ready to impress with your new PowerPoint? 🚀</p>",
    unsafe_allow_html=True
)