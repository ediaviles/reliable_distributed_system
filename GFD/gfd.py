import socket
import json
import time
import os, sys
import datetime

utils_path = os.path.join(os.path.dirname(__file__), '..')
sys.path.append(utils_path)
import utils
from CustomLog import *

CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'config.json')


class GFD():
    def __init__(self):
        self.ip = utils.gfd.ip
        self.port = utils.gfd.port
        self.heartbeat_count = 0
        self.server_count = 0
        self.server_membership = set()
        self.LFD_count = 0
        self.LFD_membership = set()
        self.lastHeartBeatTime = None
        self.lastDbWrite = None
        self.min_time = None
        self.max_time = None
        self.response_time = 0
        self.response_count = 0

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.settimeout(2)
        self.sock.bind((self.ip, self.port))
        self.sock.listen(socket.SOMAXCONN)
        logger.debug(f'GFD is now listening on port {self.port}!')
        logger.debug("GFD registering with RM...")
        self.register_with_RM()

    def register_with_RM(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(20)
                sock.connect((utils.rm.ip, utils.rm.port))
                start = utils.now()
                request = utils.Message(source="GFD", destination="RM", message_num=0, message_type="register", state=start)
                logger.send(f"Sending {request}")
                sock.send(str(request).encode("ascii"))
                response = sock.recv(1024)
        except Exception:
            response = None

        if not response:
            logger.error("Connection to RM timed out.")
        else:
            received_message = response.decode('ascii')
            logger.heartbeat(f"Received {received_message}")
            received_headers = utils.Message(ascii_string = received_message)
            if(not received_headers.message_state):
                logger.critical("Error registering GFD with RM!!!")
            else:
                logger.debug("Successfully registered with RM!")
            

    def __repr__(self):
        return f"GFD: {self.server_count} members: {[x for x in list(self.server_membership)]}"

    def monitor_LFD_servers(self):
        self.heartbeat_count += 1
        try:
            frequency = json.load(open(CONFIG_FILE_PATH, 'r')).get('GFD_FREQ')
        except Exception:
            frequency = 10
        if (self.lastHeartBeatTime == None or 
            utils.now() - self.lastHeartBeatTime >= datetime.timedelta(seconds=frequency)):
            self.lastHeartBeatTime = utils.now()
            update_LFD_members = set()
            for member in self.LFD_membership:
                update_LFD_members.add(member)
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                        sock.settimeout(20)
                        sock.connect((utils.lfds[int(member[3:])].ip, utils.lfds[int(member[3:])].port))
                        start = utils.now()
                        request = utils.Message(source="GFD", destination=member, message_num=self.heartbeat_count, message_type="request", state=start)
                        logger.send(f"Sending {request}")
                        start = utils.now().microsecond
                        sock.send(str(request).encode("ascii"))
                        response = sock.recv(1024)
                except Exception:
                    response = None
                if not response:
                    logger.error(f"Connection terminated. Heartbeat to {member} timed out.")
                    #TODO: What about the server membership?
                    update_LFD_members.remove(member)
                    if(f"S{member[3:]}" in self.server_membership): self.server_membership.remove(f"S{member[3:]}")
                else:
                    received_message = response.decode('ascii')
                    logger.heartbeat(f"Received {received_message}")
                    received_headers = utils.Message(ascii_string = received_message)
                
                    if(received_headers.message_state == "False"):
                        if(f"S{member[3:]}" in self.server_membership): 
                            self.server_membership.remove(f"S{member[3:]}")
                            self.update_RM(f"Remove S{member[3:]}")
                    else:
                        if(f"S{member[3:]}" not in self.server_membership): 
                            self.server_membership.add(f"S{member[3:]}")
                            self.update_RM(f"Add S{member[3:]}")
                    

            self.LFD_membership = update_LFD_members
            self.LFD_count = len(self.LFD_membership)
            self.server_count = len(self.server_membership)
            logger.info(self)

    def add_LFD_member(self):
        try:
            client, addr = self.sock.accept()
        except Exception:
            client = None
        
        if client is not None:
            data = client.recv(4096).decode("ascii")
            logger.receive(f"Received {data}")
            message = utils.Message(ascii_string=data)
            
            if message.destination == "GFD" and message.source.startswith("LFD"):
                if(message.message_state.startswith("register LFD")):
                    logger.heartbeat(f"Received connection request from {message.source}")
                    response = utils.Message(source="GFD", destination=message.source, message_num=message.message_num, message_type="reply", state=False)
                    if(message.source not in self.LFD_membership):
                        response = utils.Message(source="GFD", destination=message.source, message_num=message.message_num, message_type="reply", state=True)
                        self.LFD_membership.add(message.source)
                        self.LFD_count = len(self.LFD_membership)
                    logger.send(f"Sending {response}")
                    client.send(str(response).encode("ascii"))
            else:
                logger.error(f"Unintended Recipient. GFD cannot connect with {message.source}")

    def update_RM(self, action):
        if(not action.startswith("Add") and not action.startswith("Remove")): 
            logger.error(f"{action} not valid. Please check again.")
            return
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(20)
                sock.connect((utils.rm.ip, utils.rm.port))
                start = utils.now()
                request = utils.Message(source="GFD", destination="RM", message_num=0, message_type=action, state=start)
                logger.send(f"Sending {request}")
                sock.send(str(request).encode("ascii"))
                response = sock.recv(1024)
        except Exception:
            response = None

        if not response:
            logger.error(f"Connection to RM timed out. Check RM logs at {utils.now()} for more details")
        else:
            received_message = response.decode('ascii')
            logger.heartbeat(f"Received {received_message}")
            received_headers = utils.Message(ascii_string = received_message)
            if(not received_headers.message_state):
                if(action.startswith("Add")):
                    logger.error("Server already registered with RM!!!")
                elif(action.startswith("Remove")):
                    logger.error("Server NOT registered with RM!!!")
            else:
                logger.debug("Successfully updated RM!")

    def write_to_db(self):
        if self.lastDbWrite == None or utils.now() - self.lastDbWrite >= datetime.timedelta(seconds=5) :
            collection = utils.db["lfd-gfd"]
            gfd_id = 1
            count = self.responseCount if self.responseCount > 0 else 1
            data = {
                "performance" : [self.maxResponseTime, self.minResponseTime, self.avgResponseTime / count],
            }

            utils.check_and_update_collection_data(collection, gfd_id, data)
            self.lastDbWrite = utils.now()

    def perform_heartbeat_check(self):
        while(True):
            #handle heartbeat checks and membership adds
            self.add_LFD_member()
            self.monitor_LFD_servers()

def main():
    #TODO: Check if GFD is up before LFD?
    #TODO: As soon as system bootup, create GFD to ensure GFD up before LFD can connect
    gfd = GFD()
    gfd.perform_heartbeat_check()

if __name__ == '__main__':
    main()
