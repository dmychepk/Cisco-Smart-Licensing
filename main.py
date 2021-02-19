from flask import Flask, render_template, request, Response
import time
from netmiko import ConnectHandler
from concurrent.futures import ThreadPoolExecutor
import requests
import logging
from datetime import datetime
import difflib
from itertools import repeat
import copy

class ConnectionParameters:
    def __init__(self, username, password):
        self.ip = None
        self.username = username
        self.password = password
        self.secret = password
        self.device_type = 'cisco_ios'
        self.keepalive = 10

class CiscoIOSDevice:
    def __init__(self, ip, connection_parameters):
        self.ip = ip
        self.connection_parameters = copy.deepcopy(connection_parameters)
        self.connection_parameters.ip = self.ip
        self.hostname = None
        self.registered = False
        self.dlc = False
        self.__session = None
        self.dlc_supported = False
        self.http_client_source = None

    def connect(self):
        try:
            self.__session = ConnectHandler(**self.connection_parameters.__dict__)
            self.__session.enable()
            if not self.hostname:
                self.hostname = self.__session.find_prompt().replace('#', '')
            logging.info(f'{self.hostname} :: {self.ip} :: Connected :: {datetime.now()}')
            return self.__session
        except Exception as e:
            logging.error(f'{self.ip} :: {e} :: {datetime.now()}')

    def disconnect(self):
        self.__session.disconnect()
        logging.info(f'{self.hostname} :: {self.ip} :: Disconnected :: {datetime.now()}')
        self.__session = None

    def show_run(self):
        return self.__session.send_command('show run').splitlines()

    def check_status(self):
        status = []
        for line in self.__session.send_command('show license status').splitlines():
            if 'Status:' in line:
                status.append(line.strip()[8:])
        status.pop(0)
        registration_status = status[0]
        if registration_status == 'REGISTERED':
            logging.info(f'{self.hostname} :: {self.ip} :: Device is registered :: {datetime.now()}')
            self.registered = True
        if len(status) == 3:
            self.dlc_supported = True
            dlc_status = status[2]
            if dlc_status != 'Not started':
                logging.info(f'{self.hostname} :: {self.ip} :: DLC started :: {datetime.now()}')
                self.dlc = True

    def register(self, token):
        pre_check = self.show_run()
        self.__session.send_config_from_file(config_file='smart_license_config.txt')
        if self.http_client_source:
            self.__session.send_config(f'ip http client source-interface {self.http_client_source}')
        logging.info(f'{self.hostname} :: {self.ip} :: Configuration for Smart License is done :: {datetime.now()}')
        post_check = self.show_run()
        with open(f'{self.hostname}.html', 'w') as diff_file:
            diff = difflib.HtmlDiff()
            diff_file.write(diff.make_file(pre_check, post_check))
        self.__session.save_config()
        logging.info(f'{self.hostname} :: {self.ip} :: Configuration is saved :: {datetime.now()}')
        self.__session.send_command(f'license smart register idtoken {token}')
        logging.info(f'{self.hostname} :: {self.ip} :: Smart License registration has started :: {datetime.now()}')

    def wait_for_registration(self, seconds):
        for i in range(int(seconds) + 1):
            time.sleep(1)
            if i % 10 == 0:
                self.check_status()
                if self.registered:
                    logging.info(
                        f'{self.hostname} :: {self.ip} :: Devices has been registered :: {datetime.now()}')
                    break
        if not self.registered:
            for line in self.__session.send_command('show license status').splitlines():
                if line.strip().startswith('Failure reason:'):
                    registration_error = line.strip()[16:]
                    logging.warning(
                f'{self.hostname} :: {self.ip} :: {registration_error} :: {datetime.now()}')

    def run_dlc(self):
        self.__session.send_command('license smart conversion start')
        logging.info(f'{self.hostname} :: {self.ip} :: DLC Started :: {datetime.now()}')

    def ping(self, ip):
        ping_result = self.__session.send_command(f'ping {ip}')
        return True if '!' in ping_result else False

    def http_client_source_interface(self, ip):
        interfaces = self.__session.send_command('show ip int br').splitlines()
        next(interfaces)
        for interface in interfaces:
            result = self.__session.send_command(f'ping {ip} source {interface}')
            if '!' in result:
                self.http_client_source = interface
                return interface


app = Flask(__name__)


@app.route("/", methods = ["POST", "GET"])
def home():
    if request.method == "POST":
        # Getting data from WEB form
        username = request.form["username"]
        password = request.form["password"]
        cssm_ip = request.form["cssm_ip"]
        token = request.form["token"]
        devices = request.form["devices"]
        connection_parameters = ConnectionParameters(username, password)
        my_devices = []
        for device in devices.split():
            my_devices.append(CiscoIOSDevice(device, connection_parameters))
        return Response(generate(my_devices, token, cssm_ip), mimetype='text')
    else:
        with open("smart_license_config.txt") as f:
            content = f.read()
            return render_template("index.html", configuration_file=content)


def generate(my_devices, token, cssm_ip):
    with ThreadPoolExecutor(max_workers=25) as executor:
        result = executor.map(smart_license_registration, my_devices, repeat(token), repeat(cssm_ip))
        for outcome in result:
            yield outcome


def smart_license_registration(device, token, cssm_ip):
    if device.connect():
        device.check_status()
        if not device.registered:
            if not device.ping(cssm_ip):
                device.http_client_source_interface(cssm_ip)
            device.register(token)
            device.wait_for_registration(seconds=120)
        if device.registered:
            if device.dlc_supported:
                if not device.dlc:
                    device.run_dcl()
        else:
            return f'{device.hostname} - FAILED to register\n'
        device.disconnect()
        return f'{device.hostname} - OK\n'
    else:
        return f'{device.ip} - FAILED to CONNECT\n' # tested


if __name__ == '__main__':
    logging.basicConfig(filename='smart_license.log', format = '%(threadName)s: %(levelname)s: %(message)s', level=logging.INFO)

    app.run()