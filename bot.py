import os
import re
import logging
import paramiko
import psycopg2
from telegram.ext import Updater, CommandHandler, Filters, ConversationHandler, CallbackContext, MessageHandler
from telegram import Update
from functools import partial
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.DEBUG, filename='logfile.txt', encoding="utf-8", filemode='w', 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logging.debug('Получение токена бота')
load_dotenv()
TOKEN = os.getenv('TOKEN')
logging.debug('Токен получен: '+ TOKEN[:5] + '...' + TOKEN[-5:])

# --------------------------------- Получение информации из базы данных ---------------------------------

def connectAndRunQuery(query):
    connection = psycopg2.connect(user=os.getenv('DB_USER'),
                              password=os.getenv('DB_PASSWORD'),
                              host=os.getenv('DB_HOST'),
                              port=os.getenv('DB_PORT'), 
                              database=os.getenv('DB_DATABASE'))
    cursor = connection.cursor()
    cursor.execute(query)
    connection.commit()
    return connection, cursor

def runQueryWithReturn(query):
    data = ''
    try:
        connection, cursor = connectAndRunQuery(query)
        data = cursor.fetchall()
        if len(data) == 0:
            data = 'Пустой результат'
    except (Exception, psycopg2.Error) as error:
        logging.debug("Ошибка при работе с PostgreSQL", error)
        data = "Ошибка при работе с PostgreSQL"
    finally:
        if connection is not None:
            cursor.close()
            connection.close()
            logging.debug("Соединение с PostgreSQL закрыто")
    return data

def runQueryNoOutput(query):
    data = ''
    try:
        connection, cursor = connectAndRunQuery(query)
        data = 'Успех!'
    except (Exception, psycopg2.Error) as error:
        logging.debug("Ошибка при работе с PostgreSQL", error)
        data = "Ошибка при работе с PostgreSQL, запрос не выполнен!"
    finally:
        if connection is not None:
            cursor.close()
            connection.close()
            logging.debug("Соединение с PostgreSQL закрыто")
    return data

def getPhonesCommand(update: Update, context):
    logging.debug('Сбор номеров начался')
    data = runQueryWithReturn("select * from phones;")
    res = ''
    for tup in data:
        line = ''
        for item in tup:
            line += str(item) + ' '
        res += line + '\n'
    for x in range(0, len(data), 4096):
        update.message.reply_text(res)
    logging.debug('Сбор номеров закончился')

def getEmailsCommand(update: Update, context):
    logging.debug('Сбор email-адресов начался')
    data = runQueryWithReturn("select * from email;")
    res = ''
    for tup in data:
        line = ''
        for item in tup:
            line += str(item) + ' '
        res += line + '\n'
    for x in range(0, len(data), 4096):
        update.message.reply_text(res)
    logging.debug('Сбор email-адресов закончился')

def getReplLogsCommand(update: Update, context):
    logging.debug('Сбор логов о репликации начался')
    data = runQueryWithReturn('SELECT pg_read_file(pg_current_logfile());')
    data = str(data).replace('\\n', '\n').replace('\\t', '\t')[2:-1]
    res = ''
    for line in data.splitlines():
        if 'repl' in line:
            res += line + '\n'
    for x in range(0, len(res), 4096):
        update.message.reply_text(res[x:x+4096])
    logging.debug('Сбор логов о репликации закончился')

# --------------------------------- Поиск телефонов и адресов ---------------------------------

ADD_PHONE_NUMBER = range(1)
ADD_EMAIL = range(1)

# Поиск номеров телефонов
def findPhoneNumberCommand(update: Update, context):
    logging.debug('Получена команда поиска номеров')
    update.message.reply_text('Введите текст для поиска телефонных номеров: ')
    return 'findPhoneNumber'

def findPhoneNumber (update: Update, context: CallbackContext):
    logging.debug('Поиск номеров начался')
    user_input = update.message.text
    phoneNumRegex = re.compile(r'(?:\+7|8)(?: \(\d{3}\) \d{3}-\d{2}-\d{2}|\d{10}|\(\d{3}\)\d{7}| \d{3} \d{3} \d{2} \d{2}| \(\d{3}\) \d{3} \d{2} \d{2}|-\d{3}-\d{3}-\d{2}-\d{2}|\(\d{3}\)\d{3}-\d{2}-\d{2}|\(\d{3}\)\d{3} \d{2} \d{2})')
    phoneNumberList = phoneNumRegex.findall(user_input)
    if not phoneNumberList:
        update.message.reply_text('Телефонные номера не найдены')
        return
    phoneNumbers = ''
    for i in range(len(phoneNumberList)):
        phoneNumbers += f'{i+1}. {phoneNumberList[i]}\n' 
    update.message.reply_text(phoneNumbers)
    context.user_data['pnList'] = phoneNumberList
    update.message.reply_text('Введите \'Да\' для записи номеров в базу данных')
    logging.debug('Поиск номеров закончился')
    return ADD_PHONE_NUMBER

def addPhoneNumber(update: Update, context: CallbackContext):
    logging.debug('Добавление телефонов в базу данных началось')
    user_input = update.message.text
    if (user_input == 'Да'):
        phoneNumberList = context.user_data['pnList']

        command = 'insert into phones (number) values '
        for i in range(len(phoneNumberList)):
            command += "('" + phoneNumberList[i] + "'), "
        command = command[:-2] + ';'

        data = runQueryNoOutput(command)
        update.message.reply_text('Результат - ' + data)
    else:
        update.message.reply_text('Номера НЕ записаны в базу данных')

    logging.debug('Добавление телефонов в базу данных закончилось')
    return ConversationHandler.END

# Поиск электронной почты
def findEmailCommand(update: Update, context):
    logging.debug('Получена команда поиска почты')
    update.message.reply_text('Введите текст для поиска электронной почты: ')
    return 'findEmail'

def findEmail (update: Update, context: CallbackContext):
    logging.debug('Поиск почты начался')
    user_input = update.message.text
    emailRegex = re.compile(r'[\w]+[\w\-\.]+[a-zA-z0-9]+@(?:[\w-]+\.)+[\w-]+')
    emailList = emailRegex.findall(user_input)
    if not emailList:
        update.message.reply_text('Электронная почта не найдена')
        return
    email = ''
    for i in range(len(emailList)):
        email += f'{i+1}. {emailList[i]}\n' 
    update.message.reply_text(email)
    context.user_data['eList'] = emailList
    update.message.reply_text('Введите \'Да\' для записи адресов в базу данных')
    logging.debug('Поиск почты закончился')
    return ADD_EMAIL

def addEmail(update: Update, context: CallbackContext):
    logging.debug('Добавление адресов в базу данных началось')
    user_input = update.message.text
    if (user_input == 'Да'):
        emailList = context.user_data['eList']

        command = 'insert into email (address) values '
        for i in range(len(emailList)):
            command += "('" + emailList[i] + "'), "
        command = command[:-2] + ';'

        data = runQueryNoOutput(command)
        update.message.reply_text('Результат - ' + data)
    else:
        update.message.reply_text('Адресоа НЕ записаны в базу данных')

    logging.debug('Добавление адресов в базу данных закончилось')
    return ConversationHandler.END

# --------------------------------- Проверка сложности пароля ---------------------------------

def verifyPasswordCommand(update: Update, context):
    logging.debug('Получена команда проверки сложности пароля')
    update.message.reply_text('Введите пароль: ')
    return 'verifyPassword'

def verifyPassword (update: Update, context):
    logging.debug('Проверка сложности пароля началась')
    user_input = update.message.text
    passRegex = re.compile(r'^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%^&*()]).{8,}$')
    passStrong = passRegex.findall(user_input)

    if not passStrong:
        update.message.reply_text('Пароль простой')
    else:
        update.message.reply_text('Пароль сложный')

    logging.debug('Проверка сложности пароля закончилась')
    return ConversationHandler.END

# --------------------------------- Мониторинг удалённой системы линукс ---------------------------------

rm_host = os.getenv('RM_HOST')
rm_port = os.getenv('RM_PORT')
rm_username = os.getenv('RM_USER')
rm_password = os.getenv('RM_PASSWORD')
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

def getAptListOnRmHost(update: Update, context: CallbackContext):
    logging.debug('Выполнение команды \"apt list\" на удалённом хосте началось')
    client.connect(hostname=rm_host, username=rm_username, password=rm_password, port=rm_port)
    if len(context.args) > 0:
        stdin, stdout, stderr = client.exec_command('apt list --installed | grep \"' + context.args[0] + '\"')
    else:
        stdin, stdout, stderr = client.exec_command('apt list --installed')
        update.message.reply_text('Для получения информации о конкретных пакетах введите \"/get_apt_list ИМЯ_ПАКЕТА\"')
    data = stdout.read() + stderr.read()
    client.close()
    data = str(data).replace('\\n', '\n').replace('\\t', '\t')[2:-1]
    for x in range(0, len(data), 4096):
        update.message.reply_text(data[x:x+4096])
    if len(context.args) == 0:
        update.message.reply_text('Для получения информации о конкретных пакетах введите \"/get_apt_list ИМЯ_ПАКЕТА\"')
    logging.debug('Выполнение команды \"apt list\" на удалённом хосте завершено')
    return data

def execCommandOnRmHost(update: Update, context, command):
    logging.debug('Выполнение команды \"' + str(command) + '\" на удалённом хосте началось')
    client.connect(hostname=rm_host, username=rm_username, password=rm_password, port=rm_port)
    stdin, stdout, stderr = client.exec_command(command)
    data = stdout.read() + stderr.read()
    client.close()
    data = str(data).replace('\\n', '\n').replace('\\t', '\t')[2:-1]
    for x in range(0, len(data), 4096):
        update.message.reply_text(data[x:x+4096])
    logging.debug('Выполнение команды \"' + str(command) + '\" на удалённом хосте завершено')
    return data

# --------------------------------- main ---------------------------------

def main():
    logging.debug('Запуск бота')
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Проверка сложности пароля
    convHandlerValidatePass = ConversationHandler(
        entry_points=[CommandHandler('verify_password', verifyPasswordCommand)],
        states={
            'verifyPassword': [MessageHandler(Filters.text & ~Filters.command, verifyPassword)],
        },
        fallbacks=[]
    )
    dp.add_handler(convHandlerValidatePass)

    # Поиск электронной почты
    convHandlerFindEmail = ConversationHandler(
        entry_points=[CommandHandler('find_email', findEmailCommand)],
        states={
            'findEmail': [MessageHandler(Filters.text & ~Filters.command, findEmail)],
            ADD_EMAIL: [MessageHandler(Filters.text & ~Filters.command, addEmail)],
        },
        fallbacks=[]
    )
    dp.add_handler(convHandlerFindEmail)

    # Поиск номеров телефонов
    convHandlerFindPhoneNumber = ConversationHandler(
        entry_points=[CommandHandler('find_phone_number', findPhoneNumberCommand)],
        states={
            'findPhoneNumber': [MessageHandler(Filters.text & ~Filters.command, findPhoneNumber)],
            ADD_PHONE_NUMBER: [MessageHandler(Filters.text & ~Filters.command, addPhoneNumber)],
        },
        fallbacks=[]
    )
    dp.add_handler(convHandlerFindPhoneNumber)

    # Мониторинг Linux-системы
    dp.add_handler(CommandHandler('get_release', partial(execCommandOnRmHost, command='cat /etc/os-release')))
    dp.add_handler(CommandHandler('get_uname', partial(execCommandOnRmHost, command='uname -p && uname -n && uname -v')))
    dp.add_handler(CommandHandler('get_uptime', partial(execCommandOnRmHost, command='uptime')))
    dp.add_handler(CommandHandler('get_df', partial(execCommandOnRmHost, command='df -h')))
    dp.add_handler(CommandHandler('get_free', partial(execCommandOnRmHost, command='free -h')))
    dp.add_handler(CommandHandler('get_mpstat', partial(execCommandOnRmHost, command='mpstat')))
    dp.add_handler(CommandHandler('get_w', partial(execCommandOnRmHost, command='w')))
    dp.add_handler(CommandHandler('get_auths', partial(execCommandOnRmHost, command='last | grep -v "reboot" | head -n10')))
    dp.add_handler(CommandHandler('get_critical', partial(execCommandOnRmHost, command='journalctl -p 2 -r -n5')))
    dp.add_handler(CommandHandler('get_ps', partial(execCommandOnRmHost, command='ps -e')))
    dp.add_handler(CommandHandler('get_ss', partial(execCommandOnRmHost, command='ss')))
    dp.add_handler(CommandHandler('get_services', partial(execCommandOnRmHost, command='service --status-all | grep \'\\[ + \\]\'')))
    dp.add_handler(CommandHandler('get_apt_list', getAptListOnRmHost))

    # Работа с БД
    dp.add_handler(CommandHandler('get_repl_logs', getReplLogsCommand))
    dp.add_handler(CommandHandler('get_emails', getEmailsCommand))
    dp.add_handler(CommandHandler('get_phone_numbers', getPhonesCommand))

    updater.start_polling()
    updater.idle()
    logging.debug('Остановка бота')

if __name__ == '__main__':
    main()
