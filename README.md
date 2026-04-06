# Task Forge Agent
Personal Productivity Assistant, lightweighted application designed to help users manage tasks, reminders, and quick actions efficiently without relying on cloud services.  

## ⚙️ Installation & Setup

1. Clone this repository:
git clone https://github.com/AlfaX213/TaskForgeAgent.git
cd TaskForgeAgent

2. Download Python 3.11 (if you don't have it installed, 3.11 being the recommended version, if installed already, skip to step 3.)

3. Install dependencies:
pip install -r requirements.txt

4. Set up OpenRouter API
- Create an account at https://openrouter.ai/
- Generate your API key
- Set it as an environment variable:

## Windows (PowerShell):
$env:OPENROUTER_API_KEY="your_api_key_here"

## Mac/Linux:
export OPENROUTER_API_KEY="your_api_key_here"

4. Run the application (HAS TO OPEN CMD ON THE SAME FOLDER LOCATION AS WHERE THE FILE IS EXTRACTED):

streamlit run app.py

## 📄 License
This project is licensed under the MIT License.
