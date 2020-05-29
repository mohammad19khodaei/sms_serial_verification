import MySQLdb
import re
import os
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


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in config.ALLOWED_EXTENSIONS
    )


@app.route("/", methods=["GET"])
@login_required
def home():
    return render_template("index.html")


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
    import_excel_to_db(filepath)
    os.remove(filepath)
    flash("excel file uploaded successfully", "success")
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
        [json] -- [confirmation]
    """
    data = request.form
    sender = data.get("from")
    message = normalize_string(data.get("message"))

    response = check_serial(message)

    send_sms(sender, response)
    return jsonify({"message": "your sms message processed"}), 200


def send_sms(receiver, message):
    """send sms using arvan fake sms server

    Arguments:
        sender {[string]} -- [receiver of sms]
        message {[string]} -- [text of sms]
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
    """import excel to sqlite

    Arguments:
        file_path {string} -- [excel path]
    """

    create_tables()

    connection = MySQLdb.connect(
        host=config.MYSQL_HOST,
        db=config.MYSQL_DATABASE,
        user=config.MYSQL_USERNAME,
        passwd=config.MYSQL_PASSWORD,
    )
    cursor = connection.cursor()

    # sheet 0 contains valid codes
    data_frame = read_excel(file_path, sheet_name=0)

    for i, (row, ref, desc, start_serial, end_serial, date) in data_frame.iterrows():
        start_serial = normalize_string(start_serial)
        end_serial = normalize_string(end_serial)
        query = "INSERT INTO serials(reference, description, start_serial, end_serial, date) VALUES (%s, %s, %s, %s, %s)"
        cursor.execute(query, (ref, desc, start_serial, end_serial, date))
    # commit valid serials to serials table
    connection.commit()

    # sheet 1 contains failed codes
    data_frame = read_excel(file_path, sheet_name=1)
    for i, (failed_serial,) in data_frame.iterrows():
        failed_serial = normalize_string(failed_serial)
        query = "INSERT INTO invalids VALUES (%s)"
        cursor.execute(query, (failed_serial,))
    # commit failed serials to invalids table
    connection.commit()

    # commit queries to database and close connection
    connection.close()


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

    connection.close()


def check_serial(serial):
    """ check input serial that receive from sms

    Arguments:
        serial {string} -- input serial

    Returns:
        [string] -- check result
    """

    connection = MySQLdb.connect(
        host=config.MYSQL_HOST,
        db=config.MYSQL_DATABASE,
        user=config.MYSQL_USERNAME,
        passwd=config.MYSQL_PASSWORD,
    )
    cursor = connection.cursor()

    query = "SELECT * FROM invalids WHERE failed_serial = %s;"
    cursor.execute(query, (serial,))

    if len(cursor.fetchall()) > 0:
        return "your serial is invalid"

    query = "SELECT * FROM serials WHERE start_serial <= %s AND end_serial >= %s"
    cursor.execute(query, (serial, serial))

    if len(cursor.fetchall()) == 1:
        return "your serial is valid"

    return "can not find your serial inside our db"


if __name__ == "__main__":
    app.run("0.0.0.0", "5000", debug=True)
