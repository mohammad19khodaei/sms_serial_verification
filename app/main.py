import MySQLdb
import re
import os
import click
from datetime import datetime
from flask import (
    Flask,
    request,
    jsonify,
    Response,
    redirect,
    url_for,
    abort,
    flash,
    get_flashed_messages,
    render_template,
)
from flask.cli import with_appcontext
from flask_login import (
    LoginManager,
    UserMixin,
    login_required,
    login_user,
    logout_user,
    current_user,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pandas import read_excel
from werkzeug.utils import secure_filename
import requests
import config

MAX_FLASH = 100

app = Flask(__name__)

app.config["SECRET_KEY"] = config.SECRET_KEY
app.config["UPLOAD_FOLDER"] = config.UPLOAD_DIRECTORY

# flask login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# flask limiter
limiter = Limiter(app, key_func=get_remote_address)


class User(UserMixin):  # silly user model
    def __init__(self, id):
        self.id = id
        self.name = "jadi"


@click.command(name="create-tables")
@with_appcontext
def create_tables():
    """ create serials and invalids table
    """
    connection = MySQLdb.connect(
        host=config.MYSQL_HOST,
        db=config.MYSQL_DATABASE,
        user=config.MYSQL_USERNAME,
        passwd=config.MYSQL_PASSWORD,
    )
    cursor = connection.cursor()
    cursor.execute("DROP TABLE IF EXISTS serials;")
    cursor.execute(
        """CREATE TABLE serials (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            reference VARCHAR(200),
            description VARCHAR(30),
            start_serial VARCHAR(30),
            end_serial VARCHAR(200),
            date DATETIME
        );"""
    )

    cursor.execute("DROP TABLE IF EXISTS invalids")
    cursor.execute(
        """CREATE TABLE invalids (
            failed_serial VARCHAR(30)
        );"""
    )

    cursor.execute("DROP TABLE IF EXISTS processed_sms")
    cursor.execute(
        """CREATE TABLE processed_sms (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            sender VARCHAR(200),
            message VARCHAR(200),
            response VARCHAR(200),
            received_at DATETIME,
            status ENUM('success', 'failure', 'not-found')
        );"""
    )

    connection.close()
    print("Tables Created Successfully")


app.cli.add_command(create_tables)


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in config.ALLOWED_EXTENSIONS
    )


@app.route("/", methods=["GET"])
@login_required
def home():
    connection, cursor = get_connection()
    query = "SELECT * FROM processed_sms ORDER BY received_at DESC LIMIT 1000"
    cursor.execute(query)
    smss = []
    for sms in cursor.fetchall():
        id, sender, message, response, received_at, status = sms
        smss.append(
            {
                "sender": sender,
                "message": message,
                "response": response,
                "received_at": received_at,
                "status": status,
            }
        )
    query = "SELECT count(*) FROM processed_sms WHERE status = 'success'"
    success_count = cursor.execute(query)

    query = "SELECT count(*) FROM processed_sms WHERE status = 'failure'"
    failure_count = cursor.execute(query)

    query = "SELECT count(*) FROM processed_sms WHERE status = 'not-found'"
    notfound_count = cursor.execute(query)

    connection.close()

    data = {
        "smss": smss,
        "success_count": success_count,
        "failure_count": failure_count,
        "notfound_count": notfound_count,
    }

    return render_template("index.html", data=data)


@app.route("/upload", methods=["POST"])
def upload_excel():
    """ handle excel file upload
    """
    # check if the post request has the file part
    if "file" not in request.files:
        flash("No file part", "danger")
        return redirect(url_for("home"))

    file = request.files["file"]
    # if user does not select file, browser also
    # submit an empty part without filename
    if file.filename == "":
        flash("No selected file", "danger")
        return redirect(url_for("home"))

    if not allowed_file(file.filename):
        flash("Not allowd file", "danger")
        return redirect(url_for("home"))

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)
    serial_count, invalid_count = import_excel_to_db(filepath)
    os.remove(filepath)
    flash(
        f"imported {serial_count} rows of serials and {invalid_count} rows of invalids",
        "success",
    )
    return redirect(url_for("home"))


@app.route("/login", methods=["GET"])
def login():
    if current_user.is_authenticated:
        flash("you are already logged in", "warning")
        return redirect(url_for("home"))
    return render_template("login.html")


@app.route("/login", methods=["POST"])
@limiter.limit("10 per minute")
def attemp():
    """ check input username and password
    """
    username = request.form.get("username")
    password = request.form.get("password")
    remember = True if request.form.get("remember") else False
    if username == config.USERNAME and password == config.PASSWORD:
        user = User(1)
        login_user(user, remember=remember)
        return redirect("/")
    else:
        flash("Username or Password is incorrect", "danger")
        return redirect(url_for("login"))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@login_manager.user_loader
def load_user(userid):
    return User(userid)


@app.route("/v1/ok")
def health_check():
    return jsonify({"message": "ok"}), 200


@app.route(f"/v1/{config.CALL_BACK_TOKEN}/process", methods=["POST"])
def process():
    """ call this method when we receive sms from customers

    Returns:
        json -- confirmation
    """
    data = request.form
    sender = data.get("from")
    message = data.get("message")

    response, status = check_serial(message)

    save_sms_to_database(sender, message, response, status)

    send_sms(sender, response)
    return jsonify({"message": "your sms message processed"}), 200


@app.errorhandler(404)
def page_not_found(e):
    """404 page

    Args:
        e (object): error

    """
    return render_template("404.html"), 404


@app.route("/check_one_serial", methods=["POST"])
def check_one_serial():
    """check one serial that come from GUI
    """
    serial = request.form.get("serial")
    if not serial:
        flash("Please enter a serial", "warning")
        return redirect(url_for("home"))

    message = check_serial(serial)[0]
    flash(message, "info")
    return redirect(url_for("home"))


def get_connection():
    """get connection to mysql

    Returns:
        object: mysql connection
    """
    connection = MySQLdb.connect(
        host=config.MYSQL_HOST,
        db=config.MYSQL_DATABASE,
        user=config.MYSQL_USERNAME,
        passwd=config.MYSQL_PASSWORD,
    )
    cursor = connection.cursor()

    return connection, cursor


def save_sms_to_database(sender, message, response, status):
    """save input sms to database

    Arguments:
        sender {string} -- sender of sms
        message {string} -- message from sender
        response {string} -- response to sender
    """
    connection, cursor = get_connection()

    query = "INSERT INTO processed_sms (sender, message, response, received_at, status) VALUES (%s, %s, %s, %s, %s)"
    cursor.execute(query, (sender, message, response, datetime.now(), status))

    connection.commit()
    connection.close()


def send_sms(receiver, message):
    """send sms using arvan fake sms server

    Arguments:
        sender {string} -- receiver of sms
        message {string} -- text of sms
    """
    data = {"to": receiver, "message": message, "token": config.API_KEY}
    print(data)  # TODO uncomment below code

    # response = requests.post(config.SMS_SERVER, data=data)
    # print(response.text)


def normalize_string(data, fixed_size=30):
    """ convert persian digit to enlgish one and make all letter capital
        and remove any alphanumeric character

    Arguments:
        data {string} -- input string

    Returns:
        [string] -- [normalized string]
    """
    persian_numerals = "۱۲۳۴۵۶۷۸۹۰"
    arabic_numerals = "١٢٣٤٥٦٧٨٩٠"
    english_numerals = "1234567890"
    for index in range(len(persian_numerals)):
        # replace english digits with persian and arabic digits
        data = data.replace(persian_numerals[index], english_numerals[index])
        data = data.replace(arabic_numerals[index], english_numerals[index])

    data = data.upper()
    # remove any none alphanumeric character
    data = re.sub(r"\W+", "", data)

    # find all alpha and digits chars
    all_alpha = ""
    all_digit = ""
    for char in data:
        if char.isalpha():
            all_alpha += char
        elif char.isdigit():
            all_digit += char

    # add enough zero between alpha and digit characters
    number_of_zero = fixed_size - len(all_alpha) - len(all_digit)
    return all_alpha + ("0" * number_of_zero) + all_digit


def import_excel_to_db(file_path):
    """ import excel to database

    Args:
        file_path (string): file path of excel file

    Returns:
        integer: serial count and failure count
    """
    total_flashes = 0

    connection, cursor = get_connection()

    # remove every thing from serials and invalids table
    cursor.execute("DELETE FROM serials WHERE 1")
    cursor.execute("DELETE FROM invalids WHERE 1")

    serial_counter = 0
    line_number = 1
    data_frame = read_excel(file_path, sheet_name=0)  # sheet 0 contains valid serials
    for _, (row, ref, desc, start_serial, end_serial, date) in data_frame.iterrows():
        line_number += 1
        try:
            start_serial = normalize_string(start_serial)
            end_serial = normalize_string(end_serial)
            query = "INSERT INTO serials(reference, description, start_serial, end_serial, date) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(query, (ref, desc, start_serial, end_serial, date))
            serial_counter += 1
            connection.commit()
        except Exception as e:
            total_flashes += 1
            if total_flashes < MAX_FLASH:
                flash(
                    f"Error inserting line {line_number} from serials sheet SERIALS, {e}",
                    "danger",
                )

    invalid_counter = 0
    line_number = 1
    # sheet 1 contains failed serials
    data_frame = read_excel(file_path, sheet_name=1)
    for _, (failed_serial,) in data_frame.iterrows():
        try:
            failed_serial = normalize_string(failed_serial)
            query = "INSERT INTO invalids VALUES (%s)"
            cursor.execute(query, (failed_serial,))
            invalid_counter += 1
            connection.commit()
        except Exception as e:
            total_flashes += 1
            if total_flashes < MAX_FLASH:
                flash(
                    f"Error inserting line {line_number} from serials sheet SERIALS, {e}",
                    "danger",
                )

    connection.close()

    return serial_counter, invalid_counter


def check_serial(serial):
    """ check input serial that receive from sms

    Arguments:
        serial {string} -- input serial

    Returns:
        [string] -- check result
    """

    serial = normalize_string(serial)

    connection, cursor = get_connection()

    query = "SELECT * FROM invalids WHERE failed_serial = %s;"
    cursor.execute(query, (serial,))

    if len(cursor.fetchall()) > 0:
        connection.close()
        return "your serial is invalid", "failure"

    query = "SELECT * FROM serials WHERE start_serial <= %s AND end_serial >= %s"
    result = cursor.execute(query, (serial, serial))

    if result == 1:
        connection.close()
        return "your serial is valid", "success"

    connection.close()
    return "can not find your serial inside our db", "not-found"


if __name__ == "__main__":
    app.run("0.0.0.0", "5000", debug=True)
