from flask import Flask, request, jsonify
from pandas import read_excel
import requests
import config
import sqlite3

app = Flask(__name__)


@app.route('/v1/process', methods=['POST'])
def process():
    """ call this method when we receive sms from customers

    Returns:
        [json] -- [confirmation]
    """
    data = request.form
    sender = data.get('from')
    message = normalize_string(data.get('message'))
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


def normalize_string(string):
    """ convert persian digit to enlgish one and make all letter capital

    Arguments:
        string {string} -- input string

    Returns:
        [string] -- [normalized string]
    """
    from_string = '۱۲۳۴۵۶۷۸۹۰'
    to_string = '1234567890'
    for index in range(len(from_string)):
        string = string.replace(from_string[index], to_string[index])
    return string.upper()


def import_excel_to_db(file_path):
    """import excel to sqlite

    Arguments:
        file_path {string} -- [excel path]
    """

    create_tables()

    connection = sqlite3.connect(config.DATABASE_FILE_PATH)
    cursor = connection.cursor()

    # sheet 0 contains valid codes
    data_frame = read_excel(file_path, sheet_name=0)

    serial_counter = 0
    for i, (row, ref, desc, start_serial, end_serial, date) in data_frame.iterrows():
        start_serial = normalize_string(start_serial)
        end_serial = normalize_string(end_serial)
        query = f'''INSERT INTO serials("reference", "description", "start_serial", "end_serial", "date")
        VALUES("{ref}", "{desc}", "{start_serial}", "{end_serial}", "{date}")'''
        cursor.execute(query)
        if serial_counter % 2 == 0:
            connection.commit()
            serial_counter += 1
    connection.commit()

    # sheet 1 contains failed codes
    data_frame = read_excel(file_path, sheet_name=1)
    invalid_counter = 0
    for i, (failed_serial, ) in data_frame.iterrows():
        failed_serial = normalize_string(failed_serial)
        query = f'INSERT INTO invalids VALUES ("{failed_serial}")'
        cursor.execute(query)
        if invalid_counter % 2 == 0:
            connection.commit()
            invalid_counter += 1
    connection.commit()

    connection.close()


def create_tables():
    """ create serials and invalids table
    """
    connection = sqlite3.connect(config.DATABASE_FILE_PATH)
    cursor = connection.cursor()
    cursor.execute('DROP TABLE IF EXISTS serials;')
    cursor.execute("""CREATE TABLE IF NOT EXISTS serials (
            id INTEGER PRIMARY KEY,
            reference TEXT,
            description TEXT,
            start_serial TEXT,
            end_serial TEXT,
            date date
        );""")

    cursor.execute('DROP TABLE IF EXISTS invalids')
    cursor.execute("""CREATE TABLE IF NOT EXISTS invalids (
            failed_serial TEXT PRIMARY KEY
        );""")

    connection.close()


def check_sms():
    pass


if __name__ == '__main__':
    import_excel_to_db('../data/data.xlsx')
    #app.run('0.0.0.0', '5000', debug=True)
