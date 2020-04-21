from flask import Flask, request, jsonify
app = Flask(__name__)


@app.route('/v1/process', methods=['POST'])
def process():
    data = request.form
    sender = data.get('from')
    message = data.get('message')
    print(f'message: {message} form {sender}')
    return jsonify({'message': 'your sms is processing...'}), 200


def send_sms():
    pass


def check_sms():
    pass


if __name__ == '__main__':
    app.run('0.0.0.0', '5000', debug=True)
