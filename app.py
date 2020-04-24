from flask import Flask, request, jsonify
import requests
import config
app = Flask(__name__)


@app.route('/v1/process', methods=['POST'])
def process():
    data = request.form
    sender = data.get('from')
    message = data.get('message')
    send_sms(sender, message)
    return jsonify({'message': 'your sms is processing...'}), 200


def send_sms(sender, message):
    data = {
        'from': sender,
        'message': 'i love you ' + message,
        'token': config.token
    }

    response = requests.post('http://arvan/send-sms', data=data)
    print(response.text)


def check_sms():
    pass


if __name__ == '__main__':
    app.run('0.0.0.0', '5000', debug=True)
