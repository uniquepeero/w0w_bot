import telebot
from telebot import types
from telebot import util
import configparser
import logging
from os import path
import requests
import json


log = logging.getLogger(__name__)
log.setLevel(logging.INFO)
fh = logging.FileHandler("logs.log", 'w', encoding="utf-8",)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
log.addHandler(fh)



chats = {}

if path.isfile('config.ini'):
	config = configparser.ConfigParser()
	config.read('config.ini')
	BOT_KEY = config['API']['bot']
	KTR_HEADER = {'Api-Key': config['Keitaro']['APIKEY']}
	KTR_URL = config['Keitaro']['URL']
else:
	log.critical('Config file not found')

bot = telebot.TeleBot(BOT_KEY)


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
	log.debug(f'Command handler got: {message.text}')
	bot.send_message(message.from_user.id, "Привет ✌\n\nНа данный момент я умею предоставлять список плохих площадок, крео и т.п.\n\n"
	                      "Пришли мне последовательно ID кампании и параметр группировки \nНапример:\n\n111 sub_id_3\n224 external_id\n454 creative_id\n323 source")


@bot.message_handler(content_types=['text'])
def get_first_message(message):
	if not message.text.isdigit():
		bot.reply_to(message, 'Не-не-не, давай ID кампании 🙈')
	else:
		chats[message.chat.id] = {
			'campid': message.text,
			'group': None,
			'interval': None
		}
		msg = bot.reply_to(message, 'По какому параметру группировать?')
		bot.register_next_step_handler(msg, process_group)


def process_group(message):
	chats[message.chat.id]['group'] = message.text.lower()
	markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
	markup.add('Сегодня', 'Вчера', 'Текущая неделя', 'Последние 7 дней', 'Последние 30 дней', 'Текущий месяц', 'За год', 'Текущий год', 'За всё время')
	msg = bot.reply_to(message, 'И за какой период', reply_markup=markup)
	bot.register_next_step_handler(msg, process_interval)


def process_interval(message):
	chatid = message.chat.id
	try:
		chats[chatid]['interval'] = {
			'Сегодня': 'today',
			'Вчера': 'yesterday',
			'Текущая неделя': 'first_day_of_this_week',
			'Последние 7 дней': '7_days_ago',
			'Последние 30 дней': '1_month_ago',
			'Этот месяц': 'first_day_of_this_month',
			'За год': '1_year_ago',
			'Текущий год': 'first_day_of_this_year',
			'За всё время': 'all_time'
		}[message.text]
	except KeyError:
		msg = bot.reply_to(message, 'Выбери из предложенных вариантов')
		bot.register_next_step_handler(msg, process_interval)
		return
	log.debug(f'{chatid} : {chats[chatid]}')
	res_msg = check_camp(chats[chatid], message)
	if res_msg and len(res_msg) <= 3000 and res_msg != 'Пустой отчет 🙈':
		bot.send_message(chatid, res_msg)
		markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
		markup.add('Не выводить', 'С новой строчки', 'Через запятую', 'Через запятую с пробелом')
		msg = bot.send_message(chatid, f'В каком формате вывести {chats[chatid]["group"]}?', reply_markup=markup)
		bot.register_next_step_handler(msg, format_output)
	elif res_msg and len(res_msg) > 3000 and res_msg != 'Пустой отчет 🙈':
		markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
		markup.add('Да', 'Нет')
		msg = bot.send_message(chatid, f'Ответ содержит {len(res_msg)} символов.\n\nОтправить?', reply_markup=markup)
		chats[chatid]['message'] = res_msg
		bot.register_next_step_handler(msg, long_message)
	elif res_msg == 'Пустой отчет 🙈': bot.send_message(chatid, res_msg)


def long_message(message):
	answ = message.text
	chatid = message.chat.id
	if answ == 'Да':
		splitted_text = util.split_string(chats[message.chat.id]['message'], 3000)
		for text in splitted_text: bot.send_message(message.chat.id, text)
		markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
		markup.add('Не выводить', 'С новой строчки', 'Через запятую', 'Через запятую с пробелом')
		msg = bot.send_message(chatid, f'В каком формате вывести {chats[chatid]["group"]}?', reply_markup=markup)
		bot.register_next_step_handler(msg, format_output)
	elif answ == 'Нет':
		bot.send_message(message.chat.id, 'Отправка отменена')
		del chats[message.chat.id]
	else:
		msg = bot.reply_to(message, 'Выбери из предложенных вариантов')
		bot.register_next_step_handler(msg, long_message)


def format_output(message):
	try:
		answ = message.text
		chat_id = message.chat.id
		if answ == 'Не выводить':
			bot.send_message(chat_id, '👌')
			del chats[message.chat.id]
		elif answ == 'С новой строчки': pretty_send(chat_id, '\n')
		elif answ == 'Через запятую': pretty_send(chat_id, ',')
		elif answ == 'Через запятую с пробелом': pretty_send(chat_id, ', ')
		else:
			msg = bot.reply_to(message, 'Выбери из предложенных вариантов')
			bot.register_next_step_handler(msg, format_output)
	except KeyError:
		log.error(f'Повторное удаление {chat_id}')


def pretty_send(chat_id, delimeter):
	if len(delimeter.join(chats[chat_id]['group_list'])) <= 3000:
		bot.send_message(chat_id, delimeter.join(chats[chat_id]['group_list']))
	else:
		splitted = util.split_string(delimeter.join(chats[chat_id]['group_list']), 3000)
		for text in splitted: bot.send_message(chat_id, text)
	del chats[chat_id]

def ktr_get_columns():
	try:
		res = requests.get(f'{KTR_URL}/admin_api/v1/report/definition', headers=KTR_HEADER)
		if res.status_code == requests.codes.ok:
			log.debug(res.json())
		else:
			log.error(f'Get columns code {res.status_code}')
			return None
	except requests.exceptions.RequestException as e:
		log.error(f'Get columns: {e}')
		return None
	except ValueError as e:
		log.error(f'Get columns Response Text: {res.text} / ({e})')
		return None


def check_camp(params, message):
	chatid = message.chat.id
	user = f'{message.from_user.first_name} {message.from_user.last_name}'
	log.info(f'{user}: {params["campid"]} {params["group"]} {params["interval"]}')
	response_msg = """"""
	data = {
		"range": {
			"interval": params['interval'],
			"timezone": "Europe/Moscow"
		},
		"metrics": [
			"clicks", "campaign_unique_clicks", "conversions", "revenue", "cost", "profit", "sale_revenue",
			"sales", "rejected", "profit_confirmed", "approve", "lp_ctr", "roi", "roi_confirmed", "epc", "cr"
		],
		"grouping": [params['group']],
		"filters": [{"name": "campaign_id", "operator": "EQUALS", "expression": params['campid']},
		            {"name": "roi", "operator": "LESS_THAN", "expression": "0"}],
		"sort": [{"name": "cost", "order": "desc"}],
	}
	try:
		res = requests.post(f'{KTR_URL}/admin_api/v1/report/build', headers=KTR_HEADER, data=json.dumps(data))
		if res.status_code == requests.codes.ok:
			response = res.json()
			if len(response['rows']) > 0:
				chats[chatid]['group_list'] = []
				for row in response['rows']:
					response_msg += f"{row[params['group']]}\tCost {float(row['cost']):.1f}\tROI {float(row['roi']):.1f}\n"
					chats[chatid]['group_list'].append(row[params['group']])
				return response_msg
			else:
				return 'Пустой отчет 🙈'
		else:
			log.error(f'{user} Build Error: {res.status_code}')
			bot.send_message(chatid, f"Код ответа {res.status_code}\n{res.text}\nПопробуй снова")
			return None
	except requests.exceptions.RequestException as e:
		log.error(f'{user} BuildReport: {e}')
		bot.send_message(chatid, f"Ошибка сети {e}\nПопробуй снова")
	except ValueError as e:
		log.error(f'{user} BuildReport Response Text: {res.text} / ({e})')
		bot.send_message(chatid, f"Ошибка: {res.text}\n{e}\n\nПопробуй снова")
		return None


if __name__ == '__main__':
	try:
		log.info('Started')
		bot.polling()
	except KeyboardInterrupt:
		pass
	except Exception as e:
		log.error(e)
	finally:
		log.info('Closed')