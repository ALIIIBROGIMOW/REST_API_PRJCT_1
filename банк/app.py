import os
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, current_app
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
bank/
├── app.py            # Flask-сервер: маршруты + запуск
├── db.py             # работа с SQLite
├── bank.db           # файл БД SQLite
├── seed.py           # заливка тестовых кредитов в БД
├── templates/
│                     └── index.html    # страница: список кредитов + кнопка "отправить платёж"
├── requirements.txt  # flask, requests
└── .env              # URL министерства, порт       

"""

app = Flask(__name__)
RESURS_URL = os.environ.get('RESURS_URL', 'http://localhost:5001')

db.init_db()          # создать таблицы при старте

 



# jsonify необязателен для dict и list, но лучше задавать явно.
 

@app.route('/')
def index():
    return render_template('index.html', credits=db.get_all_credits())




@app.post('/pay')
def pay():    
    try:
        credit_id = int(request.form['credit_id'])
        principal_amount = int(request.form.get('principal_amount', 0))
        percent_amount = int(request.form.get('percent_amount', 0))
    except ValueError:
        return 'Суммы и credit_id должны быть числами', 400
    except KeyError:
        return 'credit_id должен быть корректным числом', 400
    
    
    paid_amount = principal_amount + percent_amount

    if principal_amount < 0 or percent_amount < 0:
        return 'Некорректная сумма платежа', 400


    credit = db.get_credit_by_id(credit_id)      
    if credit is None:
        return 'Кредит не найден', 404 # pay это не API а часть заглушки-интерфейса. Тут можно/нужно возвращать тело для дебага. Если так подумать - тут пытаться ловить что-то вообще не критично.

    if principal_amount > credit['credit_balance']:
        return 'Некорректная сумма платежа', 400
    new_balance = credit['credit_balance'] - principal_amount
    new_paid_percent = credit['paid_percent_amount'] + percent_amount
    paid_date = datetime.now().strftime('%Y-%m-%d')   # время не нужно

    db.update_balance(
        credit_id=credit_id,
        paid_amount=paid_amount,
        new_paid_percent=new_paid_percent,
        new_balance=new_balance,
        paid_date=paid_date,
    )
    
    credit_id = str(credit_id)
    
    notify_resurs(credit_id, paid_amount, new_balance, new_paid_percent, paid_date)

    return redirect('/')

def notify_resurs(credit_id, paid_amount, credit_balance, paid_percent_amount, loan_paid_date): 
    payload = {
        'credit_id': credit_id,
        'paid_amount': str(paid_amount),
        'credit_balance': str(credit_balance),
        'paid_percent_amount': str(paid_percent_amount),
        'loan_paid_date': loan_paid_date,
    }
    try:# Тут логгируем - в реальном приложении нужно повторить попытки или пробросить наверх. 
        result = requests.post(f'{RESURS_URL}/api/v1/credit-info-update', json=payload, headers={'Authorization': f'Bearer {API_TOKEN}'}, timeout=10)
    except requests.RequestException:
        current_app.logger.exception('Министерство недоступно, credit_id=%s', credit_id)
        return                                              

    if result.status_code == 200:
        return
    if result.status_code == 204:
        current_app.logger.warning('Министерство не знает кредит, рассинхрон, credit_id=%s', credit_id)
        return
    current_app.logger.error('Министерство вернуло %s, credit_id=%s', result.status_code, credit_id)
    
     

     

def format_amount(value):
    return f"{value:,}".replace(",", " ")

def format_percent(value):
    return f"{value} %"


def parse_this_credit_out_of_db(data):  
    result = dict(data)
    # Сематически в базе данных ни одно поле не должно быть NULL. В данном примере разбирать это избыточно - в реальном примере в таком случае должно падать, возвращая 500.
    result['tin'] =  int(result['tin'])
    result['loan_pnfl'] =  int(result['loan_pnfl'])
    result['bank_mfo'] =  int(result['bank_mfo'])
    result['contract_summ'] = format_amount(result['contract_summ'])    
    result['disbursed_loan_amount'] = format_amount(result['disbursed_loan_amount'])
    result['loan_interest_rate'] = format_percent(result['loan_interest_rate'])
    result['credit_balance'] = format_amount(result['credit_balance'])
    result['paid_percent_amount'] = format_amount(result['paid_percent_amount'])    
    result['credit_provision_amount'] = str(result['credit_provision_amount'])
    result['credit_id'] = str(result['credit_id'])
    # Какая же странная логика типизации. Вопрос к ТЗ... Конкретно при int("01037") → 1037 из тестовых данных bank_mfo теряет ведущий ноль, что ЯВНО ошибка ТЗ.
    #ещё там не percent а precent... Сделаю percent.
    # ещё там объявляют date = YYYY-MM-DD а потом говорят  28.12.2022    
    return result

# Согласно ТЗ, все строки кроме contract_end_date, loan_allocated_date, tin, loan_pnfl и bank_mfo это UTF-8 string с необчным форматом для цифр. contract_end_date и loan_allocated_date - date YYYY-MM-DD (что в JSON тоже строка ), остальное - int.
@app.post('/api/v1/credit-info')
@require_token
def credit_info():
    data = request.get_json(silent=True)
    if data is None:
        return '', 400
    pnfl = data.get('pnfl')
    
    credit_id = data.get('credit_id')
    
    try:
        credit_id = int(credit_id) if credit_id is not None else None
    except (TypeError, ValueError):
        return '', 400
    
    if pnfl is None or credit_id is None:
        return '', 400
    
    credits = db.get_credit_by_pnfl_and_id(pnfl, credit_id) 
    if credits is None:
        return '', 204 
    # Сематически в базе данных ни одно поле не должно быть NULL. В данном примере разбирать это избыточно - в реальном примере в таком случае должно падать, возвращая 500.

    payload = parse_this_credit_out_of_db(credits)

    return jsonify(payload), 200

# По ТЗ главное возвращать коды - тело может быть пустым, кроме 999 : нестандартные ошибки нужно объяснять.

if __name__ == '__main__':
    app.run(port=int(os.environ.get('PORT', 5000)))