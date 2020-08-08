from queue import Queue
from threading import Thread
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.proxy import Proxy, ProxyType
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException, TimeoutException, ElementNotInteractableException
from selenium.webdriver.common.action_chains import ActionChains
import pymysql
import dotenv
import os
from log import log
from itertools import product
import time
from datetime import datetime
import requests
import shutil

dotenv.load_dotenv()
db_server = os.getenv("DB_SERVER")
db_username = os.getenv("DB_USERNAME")
db_password = os.getenv("DB_PASSWORD")
db_database = os.getenv("DB_DATABASE")
db_port = os.getenv("DB_PORT")


class FileNotFound(Exception):
	''' Raised when a file required for the program to operate is missing. '''


class NoDataLoaded(Exception):
	''' Raised when the file is empty. '''


def connect_db():
	try:
		db = pymysql.connect(db_server, db_username, db_password, db_database, int(db_port))
		log("s", "DB Connection Success!")
		return db
	except Exception as e:
		raise(e)

def initDriver():
	
	options = Options()
	# proxies_list = read_from_txt("proxies.txt")
	""" Proxy Support """
	# prox = Proxy()
	# proxy = random.choice(proxies_list)
	# prox.proxy_type = ProxyType.MANUAL
	# prox.http_proxy = proxy
	# prox.ssl_proxy = proxy
	# capabilities = webdriver.DesiredCapabilities.CHROME
	# prox.add_to_capabilities(capabilities)

	options.add_experimental_option("excludeSwitches", ["enable-automation"])  # Hide info bar
	options.add_experimental_option('useAutomationExtension', False)  # Disable dev mode
	options.add_experimental_option('excludeSwitches', ['enable-logging'])
	options.add_argument('--lang=en')

	# options.add_argument('--headless')
	# driver = webdriver.Chrome(chrome_options=options, desired_capabilities=capabilities)
	driver = webdriver.Chrome(options=options)

	return driver

def gmp_scraper(taskQueue):
	db = connect_db()
	driver = initDriver()

	while not taskQueue.empty():
		task_id, address = taskQueue.get()
		log('i', 'Start task:{}'.format(task_id))
		is_updated = getUpdatedState(db, task_id)
		if is_updated:
			log("i","Already {}".format(task_id))
			taskQueue.task_done()
			continue

		keyword = "+".join(address.split())
		url ='https://www.google.com/maps/search/{}?hl=en'.format(keyword)
		
		driver.get(url)
		driver.implicitly_wait(10)

		try:
			scene = WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".section-hero-header-image-hero.widget-pane-fading.widget-pane-fade-in.section-hero-header-image-hero-clickable")))
			action = ActionChains(driver)
			action.click(scene).perform()
		except Exception as e:
			try:
				result = driver.find_element_by_css_selector("div.section-result")
				action = ActionChains(driver)
				action.click(result).perform()
				log('w', str(repr(e)))
			except Exception as ex:
				log('w', str(repr(ex)))
				taskQueue.task_done()
				continue

		time.sleep(3)
		url = str(driver.current_url)
		is_success = 0
		try:
			latitude = url.split("/@")[1].split(',')[0]
			longitude = url.split("/@")[1].split(',')[1].split(',')[0]
			is_success = 1
			update_task(db, is_success, longitude, latitude, address)
		except:
			log('f', "Can not parsing location from URL: {}".format(url))
			latitude = ""
			longitude = ""

		print(task_id, keyword, latitude, longitude)
		taskQueue.task_done()

	driver.quit()
	return True


def update_task(db, is_success, longitude, latitude, keyword):
	try:
		cursor = db.cursor()
		sql = "UPDATE users_address SET is_success=%s, la=%s, lo=%s WHERE address=%s"

		cursor.execute(sql, (is_success, latitude, longitude, keyword))
		db.commit()
		cursor.close()
	except Exception as e:
		print(repr(e))


def getUpdatedState(db, task_id):

	cursor = db.cursor()
	sql = "SELECT is_success from users_address WHERE id=%s"

	cursor.execute(sql, (task_id, ))
	result = cursor.fetchone()[0]
	cursor.close()
	return 	result


def get_scraper_tasks():
	db = connect_db()
	cursor = db.cursor()
	sql = """
			SELECT id, address FROM users_address WHERE is_success=0 ORDER BY id DESC;;
		"""
	cursor.execute(sql)
	result = cursor.fetchall()
	cursor.close()
	db.close()
	return result



def print_log(task_id, error_message):
	monitor_time = datetime.now().strftime('%m-%d-%Y %H:%M:%S')
	dir = "logs/"
	if not os.path.exists(dir):
		os.makedirs(dir)

	with open("logs/logs.log", 'a+') as f:
		f.write("[{}] \t TaskID:{} due to [{}]\n".format(monitor_time, task_id, error_message))

def test(queue):
	print(queue.get())


if __name__ == "__main__":
	task_list = get_scraper_tasks()
	log('i', "Total tasks: {}".format(len(task_list)))

	numThreads = 10
	taskQueue = Queue()

	for item in task_list:
		taskQueue.put(item)
	
	for i in range(numThreads):
		worker = Thread(target=gmp_scraper, daemon=True, args=(taskQueue, ))
		worker.start()
	
	taskQueue.join()


