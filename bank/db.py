import sqlite3


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

conn = sqlite3.connect('bank.db', check_same_thread=False)

conn.row_factory = sqlite3.Row
conn.execute('PRAGMA foreign_keys = ON')


#запускается из app.py
def init_db():
    with conn:# по ТЗ - почти все поля STRING, но это касается запросов между клиентом и сервером где и должно лежать форматирование. В БД данные хранится в сематически подходящем формате.
        conn.execute('''
                    CREATE TABLE if not exists credits (
                        credit_id                INTEGER PRIMARY KEY, 
                        loan_pnfl                TEXT NOT NULL,
                        bank_mfo                 TEXT,
                        bank_name                TEXT,
                        loan_person_name         TEXT, 
                        pas_series_number        TEXT,
                        tin                      TEXT,
                        region                   TEXT,
                        district                 TEXT,
                        address                  TEXT,
                        date_of_contract         TEXT,
                        loan_allocated_date      TEXT,
                        contract_end_date        TEXT,
                        contract_number          TEXT,
                        contract_summ            INTEGER,
                        disbursed_loan_amount    INTEGER,
                        loan_interest_rate       REAL,
                        credit_balance           INTEGER,
                        paid_percent_amount      INTEGER,
                        cadastral_number         TEXT,
                        type_of_supply           TEXT,
                        credit_provision_amount  REAL,
                        tin_of_company           TEXT,
                        name_of_company          TEXT,
                        type_of_credit           TEXT
                    );
                    '''
                    )
        conn.execute('''
                    CREATE TABLE if not exists payments (
                        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                        credit_id            INTEGER NOT NULL,
                        paid_amount          INTEGER,
                        credit_balance       INTEGER,   -- остаток ПОСЛЕ платежа
                        paid_percent_amount  INTEGER,
                        loan_paid_date       TEXT,
                        FOREIGN KEY (credit_id) REFERENCES credits(credit_id)
                    );
                    '''
                    )
        


# в рамках проекта - только для seed.py

def add_credit(credit):
    columns = [
        'credit_id', 'loan_pnfl', 'bank_mfo', 'bank_name', 'loan_person_name',
        'pas_series_number', 'tin', 'region', 'district',
        'address', 'date_of_contract', 'loan_allocated_date', 'contract_end_date',
        'contract_number', 'contract_summ', 'disbursed_loan_amount',
        'loan_interest_rate', 'credit_balance', 'paid_percent_amount',
        'cadastral_number', 'type_of_supply', 'credit_provision_amount',
        'tin_of_company', 'name_of_company', 'type_of_credit'
    ]
    cols = ', '.join(columns)
    placeholders = ', '.join('?' for _ in columns)
    values = [credit.get(c) for c in columns]
    with conn:
        conn.execute(
            f'INSERT OR REPLACE INTO credits ({cols}) VALUES ({placeholders})', 
            values
        ) # cols - захардкоженные названия полей, их экранировать не нужно
         
def get_credit_by_pnfl_and_id(pnfl, credit_id): 
    credit = conn.execute('SELECT * FROM credits WHERE loan_pnfl = ? AND credit_id = ?', (pnfl, credit_id)).fetchone()
    return dict(credit) if credit else None

def get_credit_by_id(credit_id):
    credit = conn.execute('SELECT * FROM credits WHERE credit_id = ?', (credit_id,)).fetchone()
    return dict(credit) if credit else None

def get_all_credits():
    credits = conn.execute('SELECT * FROM credits').fetchall()
    return [dict(credit) for credit in credits]
    
def update_balance(credit_id, paid_amount, new_paid_percent, new_balance, paid_date): # вся логика обновления баланса должна быть выше.
    with conn:
        conn.execute('''
                        UPDATE credits
                            SET credit_balance = ?,
                                paid_percent_amount = ?
                            WHERE credit_id = ?
                    ''', (new_balance, new_paid_percent, credit_id))
        conn.execute('''
            INSERT INTO payments(credit_id, paid_amount, credit_balance, paid_percent_amount, loan_paid_date)
            VALUES (?, ?, ?, ?, ?)
        ''', (credit_id, paid_amount, new_balance, new_paid_percent, paid_date))