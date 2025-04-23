from flask import Flask, request, render_template, session
import openai
import fitz  # PyMuPDF
import os
from dotenv import load_dotenv

from langchain_openai import AzureChatOpenAI

load_dotenv()

# Load environment variables from.env
model_name = "gpt-4o"
api_key = os.getenv("OPENAI_API_KEY")
endpoint = os.getenv("ENDPOINT")
api_version = os.getenv("OPENAI_API_VERSION")

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Generate a random secret key for session management

# Set your OpenAI API key
openai.api_key = api_key

@app.route('/')
def upload_form():
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return "No file part"
    
    file = request.files['file']
    
    if file.filename == '':
        return "No selected file"
    
    if file and file.filename.endswith('.pdf'):
        try:
            # Read the PDF file and extract text
            pdf_document = fitz.open(stream=file.read(), filetype="pdf")
            content = ""
            for page in pdf_document:
                content += page.get_text()
            pdf_document.close()
            
            session['document_content'] = content  # Store content in session
            return render_template('chat.html')  # Redirect to chat page
        except Exception as e:
            return f"An error occurred while processing the PDF: {str(e)}"
    
    return "Invalid file type. Please upload a .pdf file."

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.form['message']
    document_content = session.get('document_content', '')

    # Prepare the prompt for the model
    prompt = f"The following is the content of the document:\n\n{document_content}\n\n:User    {user_message}\nAssistant:"

    # Call OpenAI API to get a response
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    assistant_response = response['choices'][0]['message']['content']
    return assistant_response

if __name__ == '__main__':
    app.run(debug=True)