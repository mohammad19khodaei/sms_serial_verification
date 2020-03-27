from flask import Flask
app = Flask(__name__)


@app.route('/')
def hello_world():
    return "hello flask"


@app.route('v1/getsms')
def get_sms():
    pass


def send_sms():
    pass


def check_sms():
    pass