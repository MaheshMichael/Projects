import os
import json
from openai import AzureOpenAI

from dotenv import load_dotenv
load_dotenv(override=True)

summary_system_prompt = """ 
You will be provided with tax-related content to generate a structured PowerPoint presentation.  

### **Instructions:**  
- Extract key information from the provided content.  
- Summarize and organize the information into structured slides.  
- Ensure concise, well-formatted text using proper grammar.  
- Maintain a **consistent JSON format** as specified below.  

### **Output Format:**  
Your response should contain **ONLY** a JSON object in the exact format below:  

```json
{
    "slides": [
        {
            "slide_type": "First_slide",
            "title": "<<Presentation Title in two words>>",
            "subtitle": "<<Presentation Subtitle>>"
        },
        {
            "slide_type": "Second_slide",
            "title": "<<Section Title>>"
        },
        {
            "slide_type": "Third_slide",
            "title": "<<Section Title>>",
            "content": "<<Summarized content within 500 words>>"
        },
        {
            "slide_type": "Fourth_slide",
            "title": "<<Section Title>>"
        },
        {
            "slide_type": "Fifth_slide",
            "title": "<<Section Title>>",
            "content": "<<Summarized content within 450 words>>"
        },
        {
            "slide_type": "Sixth_slide",
            "title": "<<Section Title>>",
            "content": {
                "placeholder_1": [
                    "<<Bullet Point 1 (400 characters)>>",
                    "<<Bullet Point 2 (400 characters)>>"
                ],
                "placeholder_2": [
                    "<<Bullet Point 1 (400 characters)>>",
                    "<<Bullet Point 2 (400 characters)>>",
                ]
            }
        },
        {
            "slide_type": "Seventh_slide",
            "title": "<<Section Title>>",
            "content": [
                "<<Bullet Point 1 (600 characters)>>",
                "<<Bullet Point 2 (600 characters)>>",
                "<<Bullet Point 3 (500 characters)>>",
                "<<Bullet Point 4 (500 characters)>>",
                "<<Bullet Point 5 (600 characters)>>"
            ]
        },
        {
            "slide_type": "Eighth_slide",
            "title": "<<Section Title>>",
            "content": [
                "<<Bullet Point 1 (600 characters)>>",
                "<<Bullet Point 2 (600 characters)>>",
            ]
        }
    ]
}

"""

def get_presentation_content(document_text):
    client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version="2024-08-01-preview",
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    )
    
    summary_response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": summary_system_prompt,
            },
            {
                "role": "user",
                "content": f"This is the document: {document_text}",
            },
        ],
    )

    json_str = summary_response.choices[0].message.content
    json_str = json_str.replace("```json", "").replace("```", "")
    summary_dict = json.loads(json_str)
    
    return summary_dict

if __name__ == "__main__":
    document_text = "This is a document text"
    summary_dict = get_presentation_content(document_text)
    print(summary_dict)
    # create_pptx(summary_dict)