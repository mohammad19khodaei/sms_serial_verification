from flask import Flask, request, jsonify, Response, redirect, url_for, abort
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user
from pandas import read_excel
import requests
import config
import sqlite3
import re

app = Flask(__name__)

app.config['SECRET_KEY'] = config.SECRET_KEY

# flask login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


class User(UserMixin):  # silly user model

    def __init__(self, id):
        self.id = id


@app.route('/')
@login_required
def home():
    return Response("Hello World!")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == config.USERNAME and password == config.PASSWORD:
            user = User(1)
            login_user(user)
            return redirect('/')
        else:
            return abort(401)
    else:
        return Response('''
        <form action="" method="post">
            <p><input type=text name=username>
            <p><input type=password name=password>
            <p><input type=submit value=Login>
        </form>
        ''')


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.errorhandler(401)
def page_not_found(error):
    return Response('<p>Login failed</p>')


@login_manager.user_loader
def load_user(userid):
    return User(userid)


@app.route('/v1/ok')
def health_check():
    return jsonify({'message': 'ok'}), 200


@app.route('/v1/process', methods=['POST'])
def process():
    """ call this method when we receive sms from customers

    Returns:
        [json] -- [confirmation]
    """
    data = request.form
    sender = data.get('from')
    message = normalize_string(data.get('message'))

    response = check_serial(message)

    send_sms(sender, response)
    return jsonify({'message': 'your sms message processed'}), 200


def send_sms(receiver, message):
    """send sms using arvan fake sms server

    Arguments:
        sender {[string]} -- [receiver of sms]
        message {[string]} -- [text of sms]
    """
    data = {
        'to': receiver,
        'message': message,
        'token': config.API_KEY
    }

    response = requests.post(config.SMS_SERVER, data=data)
    print(response.text)


def normalize_string(data, fixed_size=30):
    """ convert persian digit to enlgish one and make all letter capital
        and remove any alphanumeric character

    Arguments:
        data {string} -- input string

    Returns:
        [string] -- [normalized string]
    """
    persian_numerals = '۱۲۳۴۵۶۷۸۹۰'
    arabic_numerals = '١٢٣٤٥٦٧٨٩٠'
    english_numerals = '1234567890'
    for index in range(len(persian_numerals)):
        # replace english digits with persian and arabic digits
        data = data.replace(persian_numerals[index], english_numerals[index])
        data = data.replace(arabic_numerals[index], english_numerals[index])

    data = data.upper()
    # remove any none alphanumeric character
    data = re.sub(r'\W+', '', data)

    # find all alpha and digits chars
    all_alpha = ''
    all_digit = ''
    for char in data:
        if char.isalpha():
            all_alpha += char
        elif char.isdigit():
            all_digit += char

    # add enough zero between alpha and digit characters
    number_of_zero = fixed_size - len(all_alpha) - len(all_digit)
    return all_alpha + ('0' * number_of_zero) + all_digit


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

    for i, (row, ref, desc, start_serial, end_serial, date) in data_frame.iterrows():
        start_serial = normalize_string(start_serial)
        end_serial = normalize_string(end_serial)
        query = f'''INSERT INTO serials("reference", "description", "start_serial", "end_serial", "date")
        VALUES("{ref}", "{desc}", "{start_serial}", "{end_serial}", "{date}")'''
        cursor.execute(query)
    # commit valid serials to serials table
    connection.commit()

    # sheet 1 contains failed codes
    data_frame = read_excel(file_path, sheet_name=1)
    for i, (failed_serial, ) in data_frame.iterrows():
        failed_serial = normalize_string(failed_serial)
        query = f'INSERT INTO invalids VALUES ("{failed_serial}")'
        cursor.execute(query)
    # commit failed serials to invalids table
    connection.commit()

    # commit queries to database and close connection
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


def check_serial(serial):
    """ check input serial that receive from sms

    Arguments:
        serial {string} -- input serial

    Returns:
        [string] -- check result
    """
    if len(serial) != 6:
        return 'can not find your serial inside our db'

    connection = sqlite3.connect(config.DATABASE_FILE_PATH)
    cursor = connection.cursor()

    query = f'SELECT * FROM invalids WHERE failed_serial = "{serial}";'
    cursor.execute(query)

    if len(cursor.fetchall()) == 1:
        return 'your serial is invalid'

    query = f'SELECT * FROM serials WHERE start_serial < "{serial}" AND end_serial > "{serial}"'
    cursor.execute(query)

    if len(cursor.fetchall()) == 1:
        return 'your serial is valid'

    return 'can not find your serial inside our db'


if __name__ == '__main__':
    import_excel_to_db('../data.xlsx')
    app.run('0.0.0.0', '5000', debug=True)
