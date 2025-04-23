# DocumentGenerator

## Folder structure
- `app/` - Folder with Streamlit app, ready to be used 
- `experiments/` - Jupyter notebooks for experiments with pptx, docx, Document Intelligence and OpenAI libraries, in order to work with this notebooks you will need to install the `requirements-exp.txt` file
- `output/` - output files from experiments
- `prompts/` - Folder to store useful prompts for the system, for now is not being used
- `sample_data/` - Sample input documents for presentation creation
- scripts/` - Python test scripts

## How to use the App
Clone the repository
```
git clone https://github.com/ey-org/documentgenerator.git
```

Enter working directory
```
cd documentgenerator/
```

Create a `.env` file in this location with the following environment variables
```
AZURE_OPENAI_ENDPOINT=""
AZURE_OPENAI_API_KEY=""
```
(optional) if you want to play around with Document Intelligence library include the `DOCUMENTINTELLIGENCE_ENDPOINT` and `DOCUMENTINTELLIGENCE_API_KEY` in the file, for now their are not in use in the App.

Create virtual environment called `venv`
```
python -m venv venv
```

Activate virtual env
```
source venv/bin/activate
```

Install requirements
```
pip install requirements.txt
```
(optional) if you want to play around with the `experiments/` folder run
```
pip install requirements-exp.txt
```

Navigate to the `app/` directory
```
cd app/
```

Run the app in your terminal
```
streamlit run setup.py
```
Stop the app in your terminal
```
Ctrl + C
```

