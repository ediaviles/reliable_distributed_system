import socket
import json
import time
import os, sys, argparse
import threading
import datetime

utils_path = os.path.join(os.path.dirname(__file__), '..')
sys.path.append(utils_path)
import utils
from CustomLog import *

parser = argparse.ArgumentParser(prog='18-749 LFD')
parser.add_argument("-n", "--lfd-id",
                    choices=range(1, 3+1),
                    type=int, required=True)

CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'config.json')

class LFD():
    def __init__(self, id):
        self.ip = ''
        self.port = utils.lfds[id].port
        self.count = 0
        self.id = id
        self.server_connected = False
        self.serverOnline = False
        self.name = f"LFD{id}"
        self.lastHeartBeatTime = None
        self.lfd_registered = False

        self.min_time = None
        self.max_time = None
        self.total_time = 0
        self.response_count = 0
        self.last_db_write = None

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.settimeout(10)
        self.sock.bind((self.ip, self.port))
        self.sock.listen(socket.SOMAXCONN)

        #when LFD boots up continue attempting to register lfd with gfd
        while(not self.lfd_registered):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as gfd_sock:
                    gfd_sock.connect((utils.gfd.ip, utils.gfd.port))
                    gfd_sock.settimeout(10)
                    #TODO: Format Message correctly
                    #TODO: Check what the response was and work with that to ensure that LFD is indeed registered
                    request = utils.Message(source=self, destination=f"GFD", message_num=self.count, message_type="request", state=f"register LFD{self.id}")
                    logger.send(f"Sending {request}")
                    gfd_sock.send(str(request).encode("ascii"))
                    response = gfd_sock.recv(1024)
                    self.lfd_registered = True #might not be useful now
            except Exception:
                logger.error(Exception.__str__)
                logger.error("Could not connect to GFD")
                #TODO: What should we do if we can't communicate with GFD?
                # time.sleep(1)
        
    def __repr__(self):
        return f"LFD{self.id}"

    def monitor_server(self):
        self.count += 1
        try:
            frequency = json.load(open(CONFIG_FILE_PATH, 'r')).get('LFD_FREQ')
        except:
            frequency = 10
        if (self.lastHeartBeatTime == None or 
            utils.now() - self.lastHeartBeatTime >= datetime.timedelta(seconds=frequency)):
            self.lastHeartBeatTime = utils.now()
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.connect(("127.0.0.1", utils.servers[self.id].port.lfd_port))
                    sock.settimeout(1)
                    checkpoint = utils.now()
                    request = utils.Message(source=self, destination=f"S{self.id}", message_num=self.count, message_type="request", state=checkpoint)
                    logger.send(f"Sending {request}")
                    sock.send(str(request).encode("ascii"))
                    response = sock.recv(1024)
            except Exception:
                response = None

            if not response:
                logger.error(f"Connection terminated. Heartbeat timed out.")
                self.serverOnline = False
            else:
                logger.heartbeat(f"Received {response.decode('ascii')}")
                self.serverOnline = True

    def handleGFDRequest(self):
        try:
            gfd_connection, addr = self.sock.accept()
        except Exception:
            gfd_connection = None
        if gfd_connection is not None:
            data = gfd_connection.recv(4096)
            data = data.decode("ascii")
            message = utils.Message(ascii_string=data)
            if message.destination == self.name:
                if message.source.startswith("GFD"):
                    logger.receive(f"Received {data}")
                    logger.heartbeat(f"Received heartbeat message from GFD")
                    end = utils.now()
                    new_time = end - datetime.datetime.strptime(message.message_state, '%Y-%m-%d %H:%M:%S.%f')
                    new_time = new_time.seconds + new_time.microseconds * 10**-6
                    self.update_time_values(new_time)
                    response = utils.Message(source=self, destination="GFD", message_num=message.message_num, message_type="reply", state=self.serverOnline)
                    logger.send(f"Sending {response}")
                    gfd_connection.send(str(response).encode("ascii"))

    def reset_values(self):
        self.max_time, self.min_time = None, None

    def update_time_values(self, new_time):
        if self.min_time != None and self.max_time != None:
            self.min_time, self.max_time = min(self.min_time, new_time), max(self.max_time, new_time)
        else:
            self.min_time, self.max_time = new_time, new_time
        self.total_time += new_time
        self.response_count += 1


    def write_to_db(self):
        if self.last_db_write == None or utils.now() - self.last_db_write >= datetime.timedelta(seconds=10):
            collection_gfd_to_lfd = utils.db["gfd-lfd"]
            component_id = self.id
            count = self.response_count if self.response_count > 0 else 1
            data = {
                "performance" : [self.max_time, self.min_time, self.total_time / count]
            }
            utils.check_and_update_collection_data(collection_gfd_to_lfd, component_id, data)
            self.last_db_write = utils.now()
            self.reset_values()


def main(args):
    lfd = LFD(id=args.lfd_id)
    while (True):
        lfd.monitor_server()
        lfd.handleGFDRequest()
        lfd.write_to_db()

if __name__ == '__main__':
    args = parser.parse_args()
    main(args)
