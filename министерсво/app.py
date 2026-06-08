import os
from functools import wraps
from flask import Flask, render_template, request, redirect, current_app
import requests
import hmac
import db


from dotenv import load_dotenv
load_dotenv()


API_TOKEN = os.environ.get('API_TOKEN', 'dev-secret')

def require_token(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        h = request.headers.get('Authorization', '')
        token = h[7:] if h.startswith('Bearer ') else ''
        if not token:
            return '', 401                               
        if not hmac.compare_digest(token, API_TOKEN):    
            return '', 403                          
        return func(*args, **kwargs)
    return wrapper




"""
ministry/
├── app.py            # Flask-сервер: маршруты + запуск
├── db.py             # работа с SQLite
├── resurs.db         # файл БД SQLite
├── templates/
│                   └── index.html    # страница: форма запроса + таблицы данных
├── requirements.txt  # flask, requests
└── .env              # URL банка, порт
"""

app = Flask(__name__)
BANK_URL = os.environ.get('BANK_URL', 'http://localhost:5000')

db.init_db()



@app.route('/')
def index():
    return render_template('index.html', credits=db.get_all_credits(), payment_updates=db.get_all_payment_updates())



# Сематически в базе данных ни одно поле не должно быть NULL. В данном примере разбирать это избыточно - в реальном примере в таком случае должно падать, возвращая 500.
def parse_amount(value): 
    s = str(value).replace('\xa0', '').replace(' ', '').strip()  # \xa0 - неразрывный пробел
    return int(s)  

def parse_percent(value): 
    s = str(value).replace('%', '').replace(' ', '').replace(',', '.').strip()
    return float(s)  

def parse_decimal(value): 
    s = str(value).replace(' ', '').replace(',', '.').strip()
    return float(s)  


def parse_credit_to_db(data): 
    result = dict(data)
    result['contract_summ']           = parse_amount(result['contract_summ'])
    result['disbursed_loan_amount']   = parse_amount(result['disbursed_loan_amount'])
    result['credit_balance']          = parse_amount(result['credit_balance'])
    result['paid_percent_amount']     = parse_amount(result['paid_percent_amount'])
    result['loan_interest_rate']      = parse_percent(result['loan_interest_rate'])
    result['credit_provision_amount'] = parse_decimal(result['credit_provision_amount']) 
    result['bank_mfo'] = str(result['bank_mfo'])  
    result['tin'] = str(result['tin'])  
    result['loan_pnfl'] = str(result['loan_pnfl']) 
    return result

 
@app.post('/request-credit')
def request_credit():
    pnfl = request.form.get('pnfl', '').strip()
    credit_id = request.form.get('credit_id', '').strip()
    if not pnfl or not credit_id:
        return 'pnfl и credit_id обязательны', 400

    try:
        result = requests.post(f'{BANK_URL}/api/v1/credit-info', json={'pnfl': pnfl, 'credit_id': credit_id}, headers={'Authorization': f'Bearer {API_TOKEN}'}, timeout=10)
    except requests.RequestException:
        current_app.logger.exception('Банк недоступен, credit_id=%s', credit_id)
        return 'Банк недоступен', 502
    if result.status_code == 200:
        try:
            db.save_credit(parse_credit_to_db(result.json()))
        except (ValueError, KeyError):                       
            current_app.logger.exception('Некорректный ответ банка, credit_id=%s', credit_id)
            return 'Некорректный ответ банка', 502
        return redirect('/')
    elif result.status_code == 204:
        return 'Кредит в банке не найден', 404
    else:
        current_app.logger.warning('Банк вернул %s, credit_id=%s', result.status_code, credit_id)
        return f'Банк вернул {result.status_code}', 502

 
@app.post('/api/v1/credit-info-update')
@require_token
def credit_info_update():
    data = request.get_json(silent=True)
    if data is None:
        return '', 400

    try:
        credit_id = int(data['credit_id'])
        paid_amount = parse_amount(data.get('paid_amount'))
        credit_balance = parse_amount(data.get('credit_balance'))
        paid_percent = parse_amount(data.get('paid_percent_amount'))  
        loan_paid_date = data.get('loan_paid_date')
    except (KeyError, TypeError, ValueError):
        return '', 400
 
    if db.get_credit_by_id(credit_id) is None:
        return '', 204

    db.apply_payment_update(
        credit_id=credit_id,
        paid_amount=paid_amount,
        credit_balance=credit_balance,
        paid_percent_amount=paid_percent,
        loan_paid_date=loan_paid_date,
    )
    return '', 200


if __name__ == '__main__':
    app.run(port=int(os.environ.get('PORT', 5001)))
