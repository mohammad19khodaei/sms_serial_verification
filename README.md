# sms_verification

## How to run
1. Install python3, pip3, virtualenv, MySQL in your system.
2. Clone the project `https://github.com/mohammad19khodaei/sms_serial_verification.git && cd sms_serial_verification`
3. in the app folder, rename the `config.py.sample` to `config.py` and do proper changes.
4. db configs are in config.py. Create the db and grant all access to the specified user with specified password.
5. Create a virtualenv named venv using `python -m venv venv`
6. Connect to virtualenv using `source venv/bin/activate`
7. From the project folder, install packages using `pip install -r requirements.txt`
8. Specify flask app environment `export FLASK_APP=app/main.py`
9. Create tables by this command: `flask create-tables`
10. Now environment is ready. Run it by `python app/main.py`
