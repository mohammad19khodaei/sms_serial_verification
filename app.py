from flask import Flask, request, jsonify
from pandas import read_excel
import requests
import config

app = Flask(__name__)


@app.route('/v1/process', methods=['POST'])
def process():
    """ call this method when we receive sms from customers

    Returns:
        [json] -- [confirmation]
    """
    data = request.form
    sender = data.get('from')
    message = data.get('message')
    send_sms(sender, message)
    return jsonify({'message': 'your sms message processed'}), 200


def send_sms(sender, message):
    """send sms using arvan fake sms server

    Arguments:
        sender {[string]} -- [sender of sms]
        message {[string]} -- [text of sms]
    """
    data = {
        'from': sender,
        'message': 'i love you ' + message,
        'token': config.API_KEY
    }

    response = requests.post(config.SMS_SERVER, data=data)
    print(response.text)


def import_excel_to_db(file_path):
    """import excel to sqlite

    Arguments:
        file_path {string} -- [excel path]
    """
    data_frame = read_excel(
        file_path, sheet_name=0)  # sheet 0 contains valid codes
    for i, (row, ref, desc, start, end, date) in data_frame.iterrows():
        print(row, ref, desc, start, end, date)

    # sheet 1 contains failed codes
    data_frame = read_excel(file_path, sheet_name=1)
    for i, (failed_serial_row) in data_frame.iterrows():
        failed_serial = failed_serial_row[0]
        print(failed_serial)


def check_sms():
    pass


if __name__ == '__main__':
    app.run('0.0.0.0', '5000', debug=True)
